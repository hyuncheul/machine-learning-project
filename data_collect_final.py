#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
K-Gaming YouTube Collector  (4 min ~ 2 h Videos · 1-day windows)
────────────────────────────────────────────────────────────────
한국어 영상 + 1일 윈도우 + Shorts(<4m) 제외 + 길이 컬럼(초·hh:mm:ss)
"""

# ───────────── import & 기본 설정 ─────────────
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from dateutil import rrule, parser as dtp
import isodate, pandas as pd, os, time, random, re
from datetime import datetime, timedelta

API_KEY   = "AIzaSyDRE48qtjqYwxNnypL8nZn62qqcuIW7BZQ"           # ← 본인 키 입력
CSV_NAME  = "game_api_data.csv"
TXT_DIR   = "transcript_api"
os.makedirs(TXT_DIR, exist_ok=True)

GAME_QUERIES = {
    "롤":          "롤",
    "서든":        "서든",
    "FC온라인":    "피파",
    "배틀그라운드": "배그",
    "발로란트":    "발로",
}
TOPIC_ID = {
    "롤": "/m/04n3w2r",
    "발로란트": "/g/11hcz1r8jm",
    "배틀그라운드": None,
    "서든": None,
    "FC온라인": None,
}

DATE_WINDOWS = [
    (d.strftime("%Y-%m-%dT%H:%M:%SZ"),
     (d + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for d in rrule.rrule(freq=rrule.DAILY, interval=3,
                         dtstart=dtp.parse("2024-03-01"),
                         until=dtp.parse("2024-03-28"))
]

# ▶ 길이 제한: 4 분(240 s) ~ 2 h(7200 s)
MIN_SEC, MAX_SEC = 240, 7_200

COST = {"search.list":100,"videos.list":1,"channels.list":1}
quota, LIMIT = 0, 9_500
kor_re = re.compile(r"[가-힣]")
today  = datetime.today().strftime("%Y-%m-%d")

# ───────────── helper 함수 ─────────────
def bump(u):
    global quota
    quota += u
    if quota >= LIMIT:
        raise RuntimeError(f"⏹ quota {quota:,}/10 000 unit 초과")

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def existing_ids():
    if os.path.exists(CSV_NAME):
        try: return set(pd.read_csv(CSV_NAME)["영상ID"])
        except: pass
    return set()

def sec_to_hms(sec:int):
    h, rem = divmod(sec, 3600)
    m, s   = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

def transcript_save(vid):
    try:
        lst = YouTubeTranscriptApi.list_transcripts(vid)
        tr  = lst.find_manually_created_transcript(['ko','en']) \
              if lst._manually_created_transcripts else \
              lst.find_generated_transcript(['ko','en'])
        with open(f"{TXT_DIR}/{vid}.txt","w",encoding="utf-8") as f:
            f.write(TextFormatter().format_transcript(tr.fetch()))
        return tr.language_code
    except: return "none"

def s_list(y, **kw):
    res=y.search().list(**kw).execute(); bump(COST["search.list"]); return res
def v_list(y, ids):
    res=y.videos().list(part="snippet,contentDetails,statistics,status",
                        id=",".join(ids)).execute()
    bump(len(ids)); return res["items"]
def c_list(y, ids):
    res=y.channels().list(part="snippet,statistics,contentDetails",
                          id=",".join(ids)).execute()
    bump(len(ids)); return {i["id"]:i for i in res["items"]}

# ───────────── main crawler ─────────────
def main():
    if API_KEY.startswith("YOUR_"):
        log("API_KEY를 입력하세요"); return
    yt = build("youtube","v3",developerKey=API_KEY)

    exist, records = existing_ids(), []
    try:
        for game, query in GAME_QUERIES.items():
            t_id = TOPIC_ID.get(game)
            for frm, to in DATE_WINDOWS:
                log(f"[{game}] {frm[:10]} ~ {to[:10]} 검색")
                nxt = None
                while True:
                    resp = s_list(
                        yt, part="id", q=query, type="video",
                        videoDuration="medium", 
                        #videoDuration="long", 
                        videoCategoryId="20", 
                        topicId=t_id,
                        regionCode="KR", relevanceLanguage="ko",
                        #order="videoCount", 
                        publishedAfter=frm, publishedBefore=to,
                        maxResults=50, pageToken=nxt,
                        fields="nextPageToken,items/id/videoId"
                    )
                    ids=[it["id"]["videoId"] for it in resp["items"] if it["id"]["videoId"] not in exist]
                    if not ids: break
                    det = v_list(yt, ids)

                    # ---- 한글 포함 + 길이 4m~2h 필터 ----
                    valid=[]
                    for d in det:
                        text = d["snippet"].get("title","")+d["snippet"].get("description","")
                        if not kor_re.search(text): continue
                        sec=int(isodate.parse_duration(d["contentDetails"]["duration"]).total_seconds())
                        if MIN_SEC<=sec<=MAX_SEC:
                            d["sec"]=sec
                            valid.append(d)
                    if not valid:
                        nxt = resp.get("nextPageToken"); 
                        if not nxt: break
                        continue

                    # ---- 채널 통계 ----
                    ch_ids = list({d["snippet"]["channelId"] for d in valid})
                    ch_map = {}
                    for j in range(0,len(ch_ids),50):
                        ch_map.update(c_list(yt,ch_ids[j:j+50]))

                    # ---- 레코드 ----
                    for v in valid:
                        sn, cd, st = v["snippet"], v["contentDetails"], v.get("statistics", {})
                        ch = ch_map.get(sn["channelId"], {})
                        sec = v["sec"]
                        records.append({
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
                            "duration": cd.get("duration"),          # ISO-8601
                            "영상길이(초)": sec,
                            "영상길이(표시)": sec_to_hms(sec),
                            "dimension": cd.get("dimension"),
                            "definition": cd.get("definition"),
                            "caption": cd.get("caption"),
                            "licensedContent": cd.get("licensedContent"),
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
                    exist.update(ids)
                    log(f"  +{len(valid)}개 (quota {quota:,})")
                    nxt = resp.get("nextPageToken")
                    if not nxt: break
                    time.sleep(random.uniform(0.8,1.2))
    except RuntimeError as e:
        log(str(e))
    except Exception as e:
        log(f"❌ 예외: {e}")
    finally:
        if records:
            new_df = pd.DataFrame(records)
            if os.path.exists(CSV_NAME):
                all_df = pd.concat([pd.read_csv(CSV_NAME), new_df]) \
                          .drop_duplicates("영상ID")
            else:
                all_df = new_df
            all_df.to_csv(CSV_NAME, index=False, encoding="utf-8-sig")
            log(f"💾 저장: 새 {len(new_df)} / 총 {len(all_df)}")
        log(f"📊 최종 quota {quota:,} unit")

if __name__ == "__main__":
    main()
