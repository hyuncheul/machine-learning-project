# ───────────── 라이브러리 ─────────────
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from dateutil import rrule, parser as dtp
import isodate, pandas as pd, os, time, random, re
from datetime import datetime, timedelta

# ───────────── 설정값 ─────────────
API_KEY   = "YOUR_API_KEY"
CSV_NAME  = "game_api_data.csv"
TXT_DIR   = "transcript_api"
os.makedirs(TXT_DIR, exist_ok=True)

GAME_QUERIES = {
    "롤":          "리그오브레전드|롤|league of legends|LOL",
    "서든":        "서든어택|서든",
    "FC온라인":    "FC온라인|피파온라인|피파|EA FC Online",
    "배틀그라운드": "배틀그라운드|배그|PUBG",
    "발로란트":    "발로란트|발로|VALORANT",
}
TOPIC_ID = {
    "롤": "/m/04n3w2r",
    "발로란트": "/g/11hcz1r8jm",
    "배틀그라운드": None,
    "서든": None,
    "FC온라인": None,
}

# 👉 2024-02-01 ~ 02-29  3일 간격
DATE_WINDOWS = [
    (d.strftime("%Y-%m-%dT%H:%M:%SZ"),
     (d + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for d in rrule.rrule(freq=rrule.DAILY, interval=3,
                         dtstart=dtp.parse("2024-02-01"),
                         until=dtp.parse("2024-02-29"))
]

# 길이 제한 (20 분 = 1 200 s  ~  2 h = 7 200 s)
MIN_SEC, MAX_SEC = 1_200, 7_200

# 할당량
COST = {"search.list": 100, "videos.list": 1, "channels.list": 1}
quota, LIMIT = 0, 9_500
kor_regex = re.compile(r"[가-힣]")
today = datetime.today().strftime("%Y-%m-%d")

# ───────────── 헬퍼 ─────────────
def bump(u):  # unit 누적
    global quota
    quota += u
    if quota >= LIMIT:
        raise RuntimeError(f"⏹ quota {quota:,}/10 000 unit 도달 – 중단")

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def existing_ids():
    if os.path.exists(CSV_NAME):
        try:
            return set(pd.read_csv(CSV_NAME)["영상ID"])
        except Exception:
            pass
    return set()

def transcript_save(v_id):
    try:
        lst = YouTubeTranscriptApi.list_transcripts(v_id)
        tr = lst.find_manually_created_transcript(['ko', 'en']) \
             if lst._manually_created_transcripts else \
             lst.find_generated_transcript(['ko', 'en'])
        txt = TextFormatter().format_transcript(tr.fetch())
        with open(f"{TXT_DIR}/{v_id}.txt", "w", encoding="utf-8") as f:
            f.write(txt)
        return tr.language_code
    except Exception:
        return "none"

# ───────────── API 래퍼 ─────────────
def s_list(y, **kw):
    res = y.search().list(**kw).execute()
    bump(COST["search.list"])
    return res

def v_list(y, ids):
    res = y.videos().list(
        part="snippet,contentDetails,statistics,status",
        id=",".join(ids)
    ).execute()
    bump(len(ids))
    return res["items"]

def c_list(y, ids):
    res = y.channels().list(
        part="snippet,statistics,contentDetails",
        id=",".join(ids)
    ).execute()
    bump(len(ids))
    return {i["id"]: i for i in res["items"]}

# ───────────── MAIN ─────────────
def main():
    if not API_KEY or API_KEY.startswith("YOUR_"):
        log("API_KEY를 입력하세요"); return
    yt = build("youtube", "v3", developerKey=API_KEY)

    exist_ids = existing_ids()
    rows = []

    try:
        for game, q in GAME_QUERIES.items():
            t_id = TOPIC_ID.get(game)
            for after, before in DATE_WINDOWS:
                log(f"[{game}] {after[:10]} ~ {before[:10]} 검색")
                next_tok = None
                while True:
                    resp = s_list(
                        yt,
                        part="id",
                        q=q,
                        type="video",
                        videoDuration="long",    # ★ Shorts & medium 차단
                        videoCategoryId="20",
                        topicId=t_id,
                        regionCode="KR",
                        relevanceLanguage="ko",
                        order="date",
                        publishedAfter=after,
                        publishedBefore=before,
                        maxResults=50,
                        pageToken=next_tok,
                        fields="nextPageToken,items/id/videoId",
                    )
                    ids = [i["id"]["videoId"] for i in resp["items"]
                           if i["id"]["videoId"] not in exist_ids]
                    if not ids:
                        break

                    details = v_list(yt, ids)

                    # -------- 2차 필터: 한글 포함 + 길이 20 min~2 h -------------
                    filtered = []
                    for d in details:
                        txt = (d["snippet"].get("title", "") +
                               d["snippet"].get("description", ""))
                        if not kor_regex.search(txt):
                            continue
                        seconds = isodate.parse_duration(
                            d["contentDetails"]["duration"]).total_seconds()
                        if MIN_SEC <= seconds <= MAX_SEC:
                            filtered.append(d)
                    if not filtered:
                        next_tok = resp.get("nextPageToken")
                        if not next_tok:
                            break
                        continue

                    # -------- 채널 통계 --------
                    ch_ids = list({d["snippet"]["channelId"] for d in filtered})
                    ch_map = {}
                    for j in range(0, len(ch_ids), 50):
                        ch_map.update(c_list(yt, ch_ids[j:j+50]))

                    # -------- 레코드 저장 --------
                    for v in filtered:
                        sn, cd, st = v["snippet"], v["contentDetails"], v.get("statistics", {})
                        ch = ch_map.get(sn["channelId"], {})
                        rows.append({
                            "수집일자": today,
                            "게임명": game,
                            "영상ID": v["id"],
                            "영상제목": sn.get("title"),
                            "영상설명": sn.get("description"),
                            "게시일": sn.get("publishedAt"),
                            "채널ID": sn.get("channelId"),
                            "채널명": sn.get("channelTitle"),
                            "태그": ", ".join(sn.get("tags", [])),
                            "카테고리ID": sn.get("categoryId"),
                            "썸네일URL": sn.get("thumbnails", {}).get("high", {}).get("url"),
                            "defaultLanguage": sn.get("defaultLanguage"),
                            **{k: cd.get(k) for k in ("duration", "dimension", "definition",
                                                     "caption", "licensedContent")},
                            "privacyStatus": v["status"].get("privacyStatus"),
                            "madeForKids": v["status"].get("madeForKids"),
                            "viewCount": int(st.get("viewCount", 0)),
                            "likeCount": int(st.get("likeCount", 0)),
                            "commentCount": int(st.get("commentCount", 0)),
                            "구독자수": int(ch.get("statistics", {}).get("subscriberCount", 0)),
                            "채널총조회수": int(ch.get("statistics", {}).get("viewCount", 0)),
                            "채널업로드영상수": int(ch.get("statistics", {}).get("videoCount", 0)),
                            "채널개설일": ch.get("snippet", {}).get("publishedAt"),
                            "자막유형": transcript_save(v["id"]),
                        })
                    exist_ids.update(ids)
                    log(f"  +{len(filtered)}편  (quota {quota:,})")

                    next_tok = resp.get("nextPageToken")
                    if not next_tok:
                        break
                    time.sleep(random.uniform(0.8, 1.3))

    except RuntimeError as e:
        log(str(e))
    except Exception as e:
        log(f"❌ 예외 발생: {e}")
    finally:
        if rows:
            new_df = pd.DataFrame(rows)
            if os.path.exists(CSV_NAME):
                df_all = pd.concat([pd.read_csv(CSV_NAME), new_df]) \
                          .drop_duplicates("영상ID")
            else:
                df_all = new_df
            df_all.to_csv(CSV_NAME, index=False, encoding="utf-8-sig")
            log(f"💾 저장 완료: 새 {len(new_df)} / 총 {len(df_all)}")
        log(f"📊 최종 quota 사용량: {quota:,} unit")

if __name__ == "__main__":
    main()
