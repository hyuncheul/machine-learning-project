#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YouTube Subtitle Topic Clustering with Progress Bars
────────────────────────────────────────────────────
• 입력 : tokenized_docs.csv              (video_id, tokens)
         game_api_data_sum.csv           (영상 메타데이터)
• 출력 : total_game_api_data.csv         (topic_score 추가)
"""

import os, re, ast, random, logging, sys, subprocess

# ──────────────────────────────────────────────────────────────
# 필요 모듈 (wordcloud 자동 설치)
# ──────────────────────────────────────────────────────────────
try:
    from wordcloud import WordCloud
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "wordcloud"])
    from wordcloud import WordCloud

import numpy as np
import pandas as pd
from tqdm import tqdm
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import matplotlib.pyplot as plt
import seaborn as sns

# ──────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────
TOKEN_PATH = "tokenized_docs.csv"
META_PATH  = "game_api_data_sum.csv"   # ← 변경 ①
OUT_PATH   = "total_game_api_data.csv"

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED); random.seed(RANDOM_SEED)

# (불용어·로깅·tqdm 설정은 그대로, 생략 가능)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
tqdm.pandas(bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

STOPWORDS = {...}           # <— 기존 목록 그대로 (생략)

MIN_TOKEN_LEN = 2
NUM_RE = re.compile(r"^\d+$")

# ──────────────────────────────────────────────────────────────
# 1. CSV 읽기 (인코딩 자동 감지)
# ──────────────────────────────────────────────────────────────
def read_csv_auto(path: str, **kwargs) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"❌ encoding auto-detect failed for {path}")

def parse_tokens(raw):
    if isinstance(raw, list):
        return raw
    if pd.isna(raw):
        return []
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return ast.literal_eval(raw)
        except Exception:
            pass
    return re.split(r"\s+", raw)

log.info("Reading CSV files…")
tokens_df = read_csv_auto(TOKEN_PATH)
meta_df   = read_csv_auto(META_PATH)

# 조회수 열(viewCount)을 숫자로 변환
meta_df["viewCount"] = pd.to_numeric(meta_df["viewCount"], errors="coerce")

tokens_df["tokens"] = tokens_df["tokens"].apply(parse_tokens)

df = (
    tokens_df.merge(meta_df, how="left",
                    left_on="video_id", right_on="영상ID")  # 영상ID 컬럼 그대로
            .rename(columns={                           # ← 변경 ②·③
                "게임명": "game",
                "viewCount": "views"                    # 조회수 열 매핑
            })
)

# ──────────────────────────────────────────────────────────────
# 2. 토큰 정제 (그대로)
# ──────────────────────────────────────────────────────────────
def clean_tokens(toks):
    return [t for t in toks
            if len(t) >= MIN_TOKEN_LEN
            and not NUM_RE.match(t)
            and t.lower() not in STOPWORDS]

log.info("Cleaning tokens & removing stopwords…")
df["clean_tokens"] = df["tokens"].progress_apply(clean_tokens)
df = df[df["clean_tokens"].str.len() > 0].reset_index(drop=True)

# ──────────────────────────────────────────────────────────────
# 3. 게임별 TF-IDF → KMeans (그대로)
# ──────────────────────────────────────────────────────────────
def join_tokens(lst): return " ".join(lst)

def best_k(X, mx=10):
    best_k, best_s = 2, -1
    for k in range(2, min(mx, X.shape[0])):
        km = KMeans(k, n_init="auto", random_state=RANDOM_SEED)
        lab = km.fit_predict(X)
        s   = silhouette_score(X, lab) if k > 1 else -1
        if s > best_s:
            best_k, best_s = k, s
    return best_k, best_s

rows, stats = [], []
log.info("Running TF-IDF & KMeans per game…")
for game, gdf in tqdm(df.groupby("game"), desc="Games"):
    docs  = gdf["clean_tokens"].map(join_tokens).tolist()
    views = gdf["views"].fillna(0).to_numpy()
    vids  = gdf["video_id"].tolist()

    vec = TfidfVectorizer(max_df=0.9, min_df=2)
    X   = vec.fit_transform(docs)

    k, sil = best_k(X) if len(docs) >= 50 else (min(5, len(docs)), -1)
    km = KMeans(k, n_init="auto", random_state=RANDOM_SEED)
    labels = km.fit_predict(X)

    terms = np.array(vec.get_feature_names_out())
    for c in range(k):
        mask = labels == c
        stats.append({
            "game": game,
            "cluster_label": c,
            "doc_count": int(mask.sum()),
            "topic_score": round(views[mask].mean() if mask.any() else 0, 2),
            "keywords": ", ".join(terms[km.cluster_centers_[c].argsort()[-10:][::-1]]),
            "silhouette_k": sil
        })
    rows += [{"video_id": vid, "game": game, "cluster_label": int(lbl)}
             for vid, lbl in zip(vids, labels)]

# ──────────────────────────────────────────────────────────────
# 4. 결과 병합 & 저장 (그대로)
# ──────────────────────────────────────────────────────────────
results_df = pd.DataFrame(rows)
stats_df   = pd.DataFrame(stats)

results_df = results_df.merge(
    stats_df[["game", "cluster_label", "topic_score"]],
    on=["game", "cluster_label"], how="left"
)

total_df = meta_df.merge(
    results_df[["video_id", "cluster_label", "topic_score"]],
    left_on="영상ID", right_on="video_id", how="left"
)

total_df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
log.info(f"✅ Output saved → {OUT_PATH}  (shape={total_df.shape})")

# ──────────────────────────────────────────────────────────────
# 5. (옵션) 시각화 함수는 동일
# ──────────────────────────────────────────────────────────────
def visualize():
    ...
