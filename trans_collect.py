#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YouTube Transcript Collector (ko → en → 번역)
─────────────────────────────────────────────
· CSV: game_api_data.csv (영상ID 컬럼 필수)
· TXT: transcript_api/{video_id}.txt
· LOG: transcript_failed.csv
"""

import os, time, random, pandas as pd
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript, NotTranslatable
)

# ───── 경로 설정 ─────
CSV_PATH        = "game_api_data.csv"
TRANSCRIPT_DIR  = "transcript_api"
FAILED_LOG_PATH = "transcript_failed.csv"
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

df          = pd.read_csv(CSV_PATH)
video_ids   = df["영상ID"].dropna().unique()
done_ids    = {f[:-4] for f in os.listdir(TRANSCRIPT_DIR) if f.endswith(".txt")}
targets     = [vid for vid in video_ids if vid not in done_ids]

print(f"🎯 전체 {len(video_ids)}개 중 {len(targets)}개 자막 미수집\n")

fail_log    = []

# ───── 자막 우선 수집 함수 (ko → en → 번역) ─────
def fetch_best_transcript(video_id: str):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # ① 한국어 자막 직접 fetch
        for tr in transcript_list:
            if tr.language_code.startswith("ko"):
                try:
                    return tr.fetch(), "ko"
                except:
                    continue

        # ② 영어 자막 직접 fetch
        for tr in transcript_list:
            if tr.language_code.startswith("en"):
                try:
                    return tr.fetch(), "en"
                except:
                    continue

        # ③ 번역 가능한 자막 → ko 또는 en 번역
        for tr in transcript_list:
            if tr.is_translatable:
                for lang in ["ko", "en"]:
                    if any(l["language_code"] == lang for l in tr.translation_languages):
                        try:
                            return tr.translate(lang).fetch(), f"{lang}_translated"
                        except:
                            continue
    except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript):
        return None, "video_unavailable"
    except Exception as e:
        return None, f"list_error: {e}"
    
    return None, "no_transcript"

# ───── 자막 저장 함수 ─────
def save_txt(video_id: str, snippets):
    text = "\n".join(s.text.strip() for s in snippets if s.text.strip())
    path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

# ───── 수집 루프 시작 ─────
max_backoff = 120
backoff     = 1
i           = 0

while i < len(targets):
    vid = targets[i]
    seq = f"[{i+1}/{len(targets)}]"
    try:
        snippets, source = fetch_best_transcript(vid)

        if snippets:
            save_txt(vid, snippets)
            print(f"{seq} ✔ {vid} 자막 저장 완료 ({source})")
        else:
            print(f"{seq} ⚠️ {vid} 자막 없음 또는 실패 ({source})")
            fail_log.append((vid, source))

        backoff = 1
        time.sleep(random.uniform(0.25, 0.65))
        i += 1

    except Exception as e:
        if "429" in str(e):
            print(f"🚨 429 Too Many Requests → {backoff}s 대기")
            time.sleep(backoff + random.uniform(0, 1))
            backoff = min(backoff * 2, max_backoff)
        else:
            print(f"{seq} ❗ {vid} 예외: {e}")
            fail_log.append((vid, f"unexpected_error: {e}"))
            i += 1

# ───── 실패 로그 저장 ─────
if fail_log:
    pd.DataFrame(fail_log, columns=["video_id", "reason"])\
      .to_csv(FAILED_LOG_PATH, index=False, encoding="utf-8-sig")
    print(f"\n📄 실패 {len(fail_log)}건 → {FAILED_LOG_PATH}")
else:
    print("\n✅ 모든 자막 수집 완료")
