from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from dateutil import rrule, parser as dtp
import pandas as pd, os, time, random, sys, re
from datetime import datetime, timedelta

# ─────────── 설정 ──────────── #
API_KEY = ""            # ⚠️ 입력
CSV_NAME, TXT_DIR = "game_api_data.csv", "transcript_api"
os.makedirs(TXT_DIR, exist_ok=True)

# OR 키워드
GAME_QUERIES = {
    "롤":          "리그오브레전드|롤|league of legends|LOL",
    "서든":        "서든어택|서든",
    "FC온라인":    "FC온라인|피파온라인|피파|EA FC Online",
    "배틀그라운드": "배틀그라운드|배그|PUBG",
    "발로란트":    "발로란트|발로|VALORANT"
}
TOPIC_ID = {
    "롤": "/m/04n3w2r",          # League of Legends
    "발로란트": "/g/11hcz1r8jm",  # VALORANT (KG ID)
    "배틀그라운드": None,        # PUBG
    "서든": None,               # Sudden Attack
    "FC온라인": None            # EA Sports FC Online
}
# 3 일 간격 윈도우 생성
DATE_WINDOWS = [(d.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 (d + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                for d in rrule.rrule(freq=rrule.DAILY, interval=3,
                                    dtstart=dtp.parse("2024-01-01"),
                                    until=dtp.parse("2024-01-31"))]

COST = {"search.list":100, "videos.list":1, "channels.list":1}
quota, LIMIT = 0, 9_500
today = datetime.today().strftime("%Y-%m-%d")
kor_regex = re.compile(r"[가-힣]")   # 한글 여부 체크

# ────────── 보조 함수 ────────── #
def bump(u:int):
    global quota; quota += u
    if quota >= LIMIT: raise RuntimeError(f"⏹ quota {quota:,}/10 000")

def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

def existing_ids():
    if os.path.exists(CSV_NAME):
        try: return set(pd.read_csv(CSV_NAME)["영상ID"])
        except: return set()
    return set()

def save(df_new):
    if df_new.empty: return
    if os.path.exists(CSV_NAME):
        df = pd.concat([pd.read_csv(CSV_NAME), df_new]).drop_duplicates("영상ID")
    else: df = df_new
    df.to_csv(CSV_NAME, index=False, encoding="utf-8-sig")
    log(f"💾 저장: 새 {len(df_new)} / 총 {len(df)}")

def transcript_save(v_id):
    try:
        lst = YouTubeTranscriptApi.list_transcripts(v_id)
        tr = lst.find_manually_created_transcript(['ko','en']) \
             if lst._manually_created_transcripts else \
             lst.find_generated_transcript(['ko','en'])
        txt = TextFormatter().format_transcript(tr.fetch())
        with open(f"{TXT_DIR}/{v_id}.txt","w",encoding="utf-8") as f: f.write(txt)
        return tr.language_code
    except: return "none"

# ────────── API 래퍼 ────────── #
def s_list(y, **kw):
    r = y.search().list(**kw).execute(); bump(COST["search.list"]); return r
def v_list(y, ids):
    r = y.videos().list(part="snippet,contentDetails,statistics,status",
                        id=",".join(ids)).execute()
    bump(len(ids)); return r["items"]
def c_list(y, ids):
    r = y.channels().list(part="snippet,statistics,contentDetails",
                          id=",".join(ids)).execute()
    bump(len(ids)); return {i["id"]:i for i in r["items"]}

# ────────── MAIN ────────── #
def main():
    if not API_KEY or API_KEY.startswith("YOUR_"):
        log("API_KEY 먼저 입력"); return
    yt = build("youtube","v3",developerKey=API_KEY)
    exist = existing_ids(); rows=[]
    try:
        for game, q in GAME_QUERIES.items():
            t_id = TOPIC_ID.get(game)
            for af, bf in DATE_WINDOWS:
                log(f"[{game}] {af[:10]}~{bf[:10]} 검색")
                nxt=None
                while True:
                    rsp=s_list(yt, part="id", q=q, type="video",
                               videoCategoryId="20", topicId=t_id,
                               regionCode="KR", relevanceLanguage="ko",
                               order="date", publishedAfter=af, publishedBefore=bf,
                               maxResults=50, pageToken=nxt,
                               fields="nextPageToken,items/id/videoId")
                    ids=[i["id"]["videoId"] for i in rsp["items"] if i["id"]["videoId"] not in exist]
                    if not ids: break
                    det=v_list(yt, ids)
                    # --- 2차: 한글 포함 필터 ---
                    det=[d for d in det if kor_regex.search(d["snippet"].get("title","")+
                                                            d["snippet"].get("description",""))]
                    if not det: nxt=rsp.get("nextPageToken"); 
                    if not nxt and not det: break
                    ch_ids=list({d["snippet"]["channelId"] for d in det})
                    ch_map={}
                    for j in range(0,len(ch_ids),50): ch_map.update(c_list(yt,ch_ids[j:j+50]))
                    for v in det:
                        sn, cd, st=v["snippet"],v["contentDetails"],v.get("statistics",{})
                        ch=ch_map.get(sn["channelId"],{})
                        rows.append({
                            "수집일자":today,"게임명":game,"영상ID":v["id"],
                            "영상제목":sn.get("title"),"영상설명":sn.get("description"),
                            "게시일":sn.get("publishedAt"),
                            "채널ID":sn.get("channelId"),"채널명":sn.get("channelTitle"),
                            "태그":", ".join(sn.get("tags",[])),"카테고리ID":sn.get("categoryId"),
                            "썸네일URL":sn.get("thumbnails",{}).get("high",{}).get("url"),
                            "defaultLanguage":sn.get("defaultLanguage"),
                            **{k:cd.get(k) for k in("duration","dimension","definition",
                                                    "caption","licensedContent")},
                            "privacyStatus":v["status"].get("privacyStatus"),
                            "madeForKids":v["status"].get("madeForKids"),
                            "viewCount":int(st.get("viewCount",0)),
                            "likeCount":int(st.get("likeCount",0)),
                            "commentCount":int(st.get("commentCount",0)),
                            "구독자수":int(ch.get("statistics",{}).get("subscriberCount",0)),
                            "채널총조회수":int(ch.get("statistics",{}).get("viewCount",0)),
                            "채널업로드영상수":int(ch.get("statistics",{}).get("videoCount",0)),
                            "채널개설일":ch.get("snippet",{}).get("publishedAt"),
                            "자막유형":transcript_save(v["id"])
                        })
                    exist.update(ids)
                    log(f"  +{len(det)} (quota {quota:,})")
                    nxt=rsp.get("nextPageToken")
                    if not nxt: break
                    time.sleep(random.uniform(0.8,1.3))
    except RuntimeError as e:
        log(str(e))
    except Exception as e:
        log(f"❌ 예외: {e}")
    finally:
        save(pd.DataFrame(rows))
        log(f"📊 최종 사용량 {quota:,} unit")

if __name__=="__main__":
    main()