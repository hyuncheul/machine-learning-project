#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
High-Performance Game Collector  v3
──────────────────────────────────
· 멀티 API 키 · 4-120분 · 한글 포함
· 자막 txt 저장 (수동/자동/번역 감지)
· 중복 ID 필터, quota 9 500 unit 제어, 재시도·백오프
"""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─── youtube_transcript_api (버전 호환) ───
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
)

# TooManyRequests: 0.6.x = 최상위, 1.x = _errors 내부, 더 옛날 = 없음
try:
    from youtube_transcript_api import TooManyRequests              # 0.6.x
except ImportError:
    try:
        from youtube_transcript_api._errors import TooManyRequests   # 1.x
    except ImportError:
        class TooManyRequests(Exception):                           # fallback
            """Placeholder for missing TooManyRequests exception"""
            pass

from dateutil import parser as dtp
from datetime import datetime
from collections import defaultdict
import isodate, pandas as pd, os, re, sys, argparse, time, random, json

# ────────── 전역 설정 ────────── #
API_KEYS = {
    "롤":         "AIzaSyDPvRKZPzQXnYdOonKEJ8y7J0Ufc5zMuXA",
    "서든":       "AIzaSyDHk9Fd_6plv_wP3Oie83P-4Wnir3h4eg4",
    "FC온라인":   "AIzaSyCB097p34VBzavqHkripR-AQRfZOYkAO2Y",
    "배틀그라운드":"AIzaSyDRE48qtjqYwxNnypL8nZn62qqcuIW7BZQ",
    "발로란트":   "AIzaSyB8xrapCqROGfnt8hBkBmSncG1rtZu2Wfw"
}

CSV_NAME               = "game_api_data.csv"
TXT_DIR                = "transcript_api"     # ⬅︎ NEW
MIN_SEC, MAX_SEC       = 240, 7200
MAX_CH_SEARCH_PAGES    = 2
MAX_PL_PAGES           = 11
UNIT_LIMIT_PER_DAY     = 9_500

COST = {"search": 100, "channel": 1, "plist": 1, "videos": 1}

TAG_STR = {
    "롤":         "리그오브레전드|롤|league of legends|LOL",
    "서든":       "서든어택|서든",
    "FC온라인":   "FC온라인|피파온라인|피파|EA FC Online",
    "배틀그라운드":"배틀그라운드|배그|PUBG",
    "발로란트":   "발로란트|발로|VALORANT",
}

kor       = re.compile(r"[가-힣]")
safe_int  = lambda x: int(x) if str(x).isdigit() else 0
os.makedirs(TXT_DIR, exist_ok=True)            # ⬅︎ NEW

# ────────── 공통 함수 ────────── #
def log(*m): print("[", datetime.now().strftime("%H:%M:%S"), "]", *m, flush=True)

def hms(sec:int)->str:
    h,m = divmod(sec,3600); m,s = divmod(m,60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

def len_ok(iso):
    s = int(isodate.parse_duration(iso).total_seconds())
    return MIN_SEC <= s <= MAX_SEC, s

# ──────── 자막 저장 (FIX + NEW) ──────── #
def transcript_save(video_id: str) -> str:
    """
    • 가능한 경우 한글(ko) → 영어(en) → 최초 트랜스크립트 순으로 선택
    • txt 저장:  [TXT_DIR]/<video_id>.txt
    • 반환값: 'manual-ko' / 'auto-ko' / 'translate-ko' / 'none' 등
    """
    try:
        list_obj = YouTubeTranscriptApi.list_transcripts(video_id)

        # 우선순위 1) 수동 ko, 2) 자동 ko, 3) 수동 en, 4) 자동 en, 5) 첫 트랜스크립트
        target = (
            list_obj.find_manually_created_transcript(['ko', 'ko-KR']) or
            list_obj.find_generated_transcript(['ko', 'ko-KR'])         or
            list_obj.find_manually_created_transcript(['en'])           or
            list_obj.find_generated_transcript(['en'])
        )
        if target is None:
            target = list_obj._TranscriptsList__transcripts[0]  # 첫 번째 fallback

        # 실제 받기 (한국어 없으면 번역)
        if 'ko' not in target.language_code:
            try:
                target = target.translate('ko')
                t_type = f"translate-{target.language_code}"
            except Exception:
                t_type = f"{'manual' if target.is_manually_created else 'auto'}-{target.language_code}"
        else:
            t_type = f"{'manual' if target.is_manually_created else 'auto'}-ko"

        lines = target.fetch()
        # 시간+텍스트 → 텍스트만
        transcript_text = "\n".join([l['text'] for l in lines]).strip()
        if transcript_text:
            with open(os.path.join(TXT_DIR, f"{video_id}.txt"), "w", encoding="utf-8") as f:
                f.write(transcript_text)
        else:
            t_type = "none"

        return t_type
    except (TranscriptsDisabled, NoTranscriptFound):
        return "disabled"
    except TooManyRequests:
        log("⚠️ Transcript TooManyRequests – sleep 30s")
        time.sleep(30)
        return transcript_save(video_id)  # 재귀 재시도(단순)
    except CouldNotRetrieveTranscript:
        return "error"
    except Exception as e:
        log("⚠️ Transcript error:", e)
        return "error"

# ──────── API 사용량 관리 ──────── #
API_USAGE = defaultdict(int)

def charge(key:str, units:int):
    if API_USAGE[key] + units > UNIT_LIMIT_PER_DAY:
        raise StopIteration(f"quota {API_USAGE[key]}→{API_USAGE[key]+units} unit 초과")
    API_USAGE[key] += units

def exec_request(req, cost, api_key, retries=3):
    delay = 2
    for n in range(retries):
        try:
            charge(api_key, cost)
            return req.execute()
        except HttpError as e:
            if e.resp.status in (500, 503, 429) or (e.resp.status==403 and "quotaExceeded" in str(e)):
                log(f"⚠️ {e.resp.status} 재시도 {n+1}/{retries}")
                time.sleep(delay + random.random())
                delay *= 2
                continue
            raise
    raise RuntimeError("API 재시도 실패")

# ────────── Data API 래퍼 ────────── #
def s_list(y, k, **kw): return exec_request(y.search().list(**kw), COST["search"], k)
def ch_list(y, k, ids):   return exec_request(y.channels().list(
                            part="snippet,statistics,contentDetails,brandingSettings",
                            id=",".join(ids)), COST["channel"]*len(ids), k)
def pl_list(y, k, pid, tok=None): return exec_request(
                            y.playlistItems().list(part="contentDetails", playlistId=pid,
                                                   maxResults=50, pageToken=tok),
                            COST["plist"], k)
def v_list(y, k, ids): return exec_request(
                            y.videos().list(part="snippet,contentDetails,statistics,status",
                                            id=",".join(ids)),
                            COST["videos"]*len(ids), k)

# ────────── 메인 수집 루틴 ────────── #
def collect_game(game, query, api_key, start_date, end_date, exist_ids):
    yt  = build("youtube", "v3", developerKey=api_key)
    today = datetime.now().strftime("%Y-%m-%d")
    START = dtp.parse(start_date).date()
    END   = dtp.parse(end_date).date()
    terms = query.split("|")

    records = []
    try:
        uploads, ch_meta, nxt, pg = set(), {}, None, 0
        while pg < MAX_CH_SEARCH_PAGES:
            res = s_list(yt, api_key, part="id", q=query, type="channel",
                         maxResults=50, pageToken=nxt)
            ids = [c['id']['channelId'] for c in res.get("items", [])]
            if ids:
                meta = ch_list(yt, api_key, ids)
                for ch in meta.get("items", []):
                    kw = (ch["brandingSettings"]["channel"].get("keywords") or "").lower()
                    if any(t in kw for t in terms):
                        pid = ch["contentDetails"]["relatedPlaylists"]["uploads"]
                        uploads.add(pid)
                        ch_meta[pid] = ch
            nxt, pg = res.get("nextPageToken"), pg+1
            if not nxt: break

        for up in uploads:
            vids, nxt, pp = [], None, 0
            while pp < MAX_PL_PAGES:
                pl = pl_list(yt, api_key, up, nxt)
                for it in pl.get("items", []):
                    vid = it["contentDetails"]["videoId"]
                    if vid in exist_ids: continue
                    pub = dtp.isoparse(it["contentDetails"]["videoPublishedAt"]).replace(tzinfo=None).date()
                    if START <= pub <= END:
                        vids.append(vid)
                nxt, pp = pl.get("nextPageToken"), pp+1
                if not nxt: break

            for i in range(0, len(vids), 50):
                metas = v_list(yt, api_key, vids[i:i+50]).get("items", [])
                for v in metas:
                    sn, cd, st = v["snippet"], v["contentDetails"], v.get("statistics", {})
                    ok, sec = len_ok(cd["duration"]);  title = sn.get("title") or ""
                    if not ok: continue
                    txt = (title + (sn.get("description") or "")).lower()
                    if not kor.search(txt) or not any(t in txt for t in terms): continue

                    # ⬅︎ NEW: 자막 저장
                    caption_type = transcript_save(v["id"])

                    ch = ch_meta.get(up, {})
                    records.append({
                        "수집일자": today,
                        "게임명": game,
                        "영상ID": v["id"],
                        "영상제목": title,
                        "영상설명": sn.get("description") or "",
                        "게시일": sn.get("publishedAt"),
                        "채널ID": sn.get("channelId"),
                        "채널명": sn.get("channelTitle"),
                        "태그": ", ".join(sn.get("tags") or []),
                        "카테고리ID": sn.get("categoryId"),
                        "썸네일URL": sn.get("thumbnails", {}).get("high", {}).get("url"),
                        "defaultLanguage": sn.get("defaultLanguage"),
                        "duration": cd.get("duration"),
                        "영상길이(초)": sec,
                        "영상길이(표시)": hms(sec),
                        "dimension": cd.get("dimension"),
                        "definition": cd.get("definition"),
                        "caption": cd.get("caption"),
                        "licensedContent": cd.get("licensedContent"),
                        "privacyStatus": v["status"].get("privacyStatus"),
                        "madeForKids": v["status"].get("madeForKids"),
                        "viewCount": safe_int(st.get("viewCount")),
                        "likeCount": safe_int(st.get("likeCount")),
                        "commentCount": safe_int(st.get("commentCount")),
                        "구독자수": safe_int(ch.get("statistics", {}).get("subscriberCount")),
                        "채널총조회수": safe_int(ch.get("statistics", {}).get("viewCount")),
                        "채널업로드영상수": safe_int(ch.get("statistics", {}).get("videoCount")),
                        "채널개설일": ch.get("snippet", {}).get("publishedAt"),
                        "자막유형": caption_type                      # ⬅︎ NEW
                    })
    except StopIteration as e:
        log(f"▶ {game} 중단 – {e}")

    log(f"== {game} 완료 : {len(records)}편 수집")
    return records

# ────────── 진입점 ────────── #
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="2024-01-01")
    parser.add_argument("--end",   required=True, help="2024-01-31")
    args = parser.parse_args()

    try:
        s_date = dtp.parse(args.start).date()
        e_date = dtp.parse(args.end).date()
        if s_date > e_date:
            parser.error("--start 는 --end 이전이어야 합니다.")
    except Exception:
        parser.error("날짜 형식은 YYYY-MM-DD 이어야 합니다.")

    # 기존 CSV 중복 필터
    exist_ids = set()
    if os.path.exists(CSV_NAME):
        for chunk in pd.read_csv(CSV_NAME, usecols=["영상ID"], dtype=str, chunksize=100_000):
            exist_ids.update(chunk["영상ID"].tolist())
        log(f"중복 필터: {len(exist_ids):,}개 영상ID 로드")

    all_rec = []
    for game, query in TAG_STR.items():
        key = API_KEYS.get(game)
        if not key:
            log(f"API 키 누락 → {game} 건너뜀"); continue
        recs = collect_game(game, query, key, args.start, args.end, exist_ids)
        all_rec.extend(recs); exist_ids.update(r["영상ID"] for r in recs)

    if all_rec:
        pd.DataFrame(all_rec).to_csv(
            CSV_NAME, mode="a",
            header=not os.path.exists(CSV_NAME), index=False,
            encoding="utf-8-sig")
        log(f"💾 {len(all_rec):,} 건 저장 완료")
    log("🌙 전체 실행 종료")

if __name__ == "__main__":
    main()
