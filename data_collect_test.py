#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YT-Game-Crawler (1-run, quota≈10k)
· 7-day windows, search page≤4, playlist 2 page
· 4 min-2 h, 카테20/24/22, 한글 포함 filter
"""

from googleapiclient.discovery import build
import isodate, pandas as pd, os, re, time, random
from datetime import datetime, timedelta
from dateutil import parser as dtp

# ────────── USER CONFIG ──────────
API_KEY = "AIzaSyDVf8rC1igdzaSKwNRU0ruMISDOdJ4b2DM"                         # 각 회차마다 바꿔서 실행
RUN_START = "2024-03-25"                         # 창 시작일 (7일 포함)
WINDOW_DAYS = 7
CSV_NAME = "game_api_data_master.csv"
TXT_DIR  = "transcript_api"; os.makedirs(TXT_DIR, exist_ok=True)

QUERY_SET = {
    "롤": ["리그오브레전드"],
    "서든": ["서든어택"],
    "FC온라인": ["FC온라인"],
    "배틀그라운드": ["배틀그라운드"],
    "발로란트": ["발로란트"],
}

OFFICIAL_PL = {  # uploads playlistId 직접 사용 (look-up 비용 0)
    "롤": ["UUzAypSoOFKCZUts3ULtVT_g", "UUSyMLwhB8uWPpYuRv3pSqyg"],
    "발로란트": ["UU1W0yCAwviG9V0_t40b0TxQ"],
}

MIN_SEC, MAX_SEC = 240, 7200
CAT_OK = {"20","24","22"}
MAX_PAGES_PER_SEARCH = 4
MAX_PLAYLIST_PAGES   = 2
TARGET_QUOTA = 9_600

COST = {"search.list":100,"videos.list":1,"playlistItems.list":1}
quota = 0
kor_re = re.compile(r"[가-힣]")
today  = datetime.today().strftime("%Y-%m-%d")

# ────────── helpers ──────────
def bump(u):
    global quota
    quota += u
    if quota >= TARGET_QUOTA:
        raise RuntimeError("quota limit")

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def hms(sec): h,m = divmod(sec,3600); m,s=divmod(m,60); return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# thin wrappers
def s_list(yt, **kw): r=yt.search().list(**kw).execute(); bump(100); return r
def v_list(yt, ids):  r=yt.videos().list(part="snippet,contentDetails,statistics",id=",".join(ids)).execute(); bump(len(ids)); return r.get("items",[])
def pl_items(yt, pid, tok=None): r=yt.playlistItems().list(part="contentDetails",playlistId=pid,maxResults=50,pageToken=tok).execute(); bump(1); return r

def valid(v):
    sn, cd = v["snippet"], v["contentDetails"]
    if sn.get("categoryId") not in CAT_OK: return False
    if not kor_re.search(sn.get("title","")+sn.get("description","")): return False
    sec=int(isodate.parse_duration(cd["duration"]).total_seconds())
    if not (MIN_SEC <= sec <= MAX_SEC): return False
    v["sec"]=sec; return True

# ────────── main run ──────────
def main():
    yt = build("youtube","v3",developerKey=API_KEY)

    # 7-day window
    start_dt = dtp.parse(RUN_START)
    after = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    before = (start_dt + timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    exist = set(pd.read_csv(CSV_NAME)["영상ID"]) if os.path.exists(CSV_NAME) else set()
    rows  = []

    try:
        # A. search.list
        for game, kws in QUERY_SET.items():
            for kw in kws:
                nxt, pg = None, 0
                while pg < MAX_PAGES_PER_SEARCH:
                    rsp=s_list(yt,part="id",q=kw,type="video",order="date",
                               publishedAfter=after,publishedBefore=before,
                               maxResults=50,pageToken=nxt)
                    ids=[i["id"]["videoId"] for i in rsp.get("items",[])
                         if i["id"]["videoId"] not in exist]
                    if not ids: break
                    vids=[v for v in v_list(yt, ids) if valid(v)]
                    if vids:
                        rows.extend(build_rows(vids, game))
                    exist.update(ids)
                    nxt=rsp.get("nextPageToken"); pg+=1
                    if not nxt: break
                    time.sleep(0.4)

        # B. playlist uploads
        for game, pls in OFFICIAL_PL.items():
            for pid in pls:
                nxt, pg = None, 0
                while pg<MAX_PLAYLIST_PAGES:
                    pl=pl_items(yt, pid, nxt)
                    ids=[it["contentDetails"]["videoId"] for it in pl.get("items",[])
                         if it["contentDetails"]["videoId"] not in exist]
                    if ids:
                        vids=[v for v in v_list(yt, ids) if valid(v)]
                        rows.extend(build_rows(vids, game))
                        exist.update(ids)
                    nxt=pl.get("nextPageToken"); pg+=1
                    if not nxt: break
                    time.sleep(0.3)

    except RuntimeError:
        log("quota reached – stopping run")
    finally:
        if rows:
            df_new=pd.DataFrame(rows)
            if os.path.exists(CSV_NAME):
                all_df=pd.concat([pd.read_csv(CSV_NAME),df_new]).drop_duplicates("영상ID", keep="last")
            else: all_df=df_new
            all_df.to_csv(CSV_NAME,index=False,encoding="utf-8-sig")
            log(f"💾 새 {len(df_new)} / 총 {len(all_df)} 저장")
        log(f"📊 quota 사용 {quota:,} / 10 000 unit")

def build_rows(vids, game):
    buf=[]
    for v in vids:
        sn,cd,st=v["snippet"],v["contentDetails"],v.get("statistics",{})
        buf.append({
            "수집일자": today, "게임명": game, "영상ID": v["id"],
            "영상제목": sn.get("title"), "게시일": sn.get("publishedAt"),
            "채널ID": sn.get("channelId"), "카테고리ID": sn.get("categoryId"),
            "duration": cd.get("duration"), "영상길이(초)": v["sec"], "영상길이(표시)": hms(v["sec"]),
            "viewCount": int(st.get("viewCount",0)), "likeCount": int(st.get("likeCount",0)),
            "commentCount": int(st.get("commentCount",0)),
        })
    return buf

if __name__ == "__main__":
    main()
