#!/usr/bin/env python3
"""
YouTube Subtitle Topic Clustering Pipeline
=========================================
Run example:
    python youtube_topic_clustering.py \
        --meta game_api_data_sum.csv \
        --tokens tokenized_docs.csv \
        --outdir outputs

Fix 2025‑05‑29‑B:
    • Print **20** top terms per cluster instead of 10.
      (line changed: `', '.join(kw)`)

Outputs
-------
• <outdir>/topic_scores.csv          : video_id, cluster_label, topic_score
• <outdir>/total_game_api_data.csv   : original metadata + topic_score
• <outdir>/silhouette_<게임명>.png    : k vs silhouette plots per game
• <outdir>/wc_<게임>_cluster<k>.png   : word‑cloud per cluster
"""
import os, re, ast, argparse, warnings
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import matplotlib.pyplot as plt
from wordcloud import WordCloud

# --------------------------- Stop‑word list ---------------------------
STOPWORDS = set([
    '있다','되다','하다','아니다','없다','보다','말다','돼다','오다','가다','같다','그렇다','좋다','먹다','맞다','이다','나오다','자다','들다','남다','않다','주다','잡다','이렇다','어떻다','죽다','모르다','알다','나다','버리다','가지','많다','받다',
    '이','가','은','는','을','를','에','에서','에게','한테','으로','로','와','과','도','만','이나','이나마','까지','부터','때문에','하지만','그러나','그리고','또한','그래서','그런데','즉','즉시','때문',
    '그','이것','그것','저것','여기','거기','저기','누구','무엇','어디','왜','어떻게',
    '아','어','야','우와','헐','음','응','하하','허허','흠','오','음음','오케이','일단','진짜','그냥','이제','지금','바로','그거','나이스',
    '정말','너무','많이','좀','조금','거의','항상','자주',
    '네','예','그래','맞아','아니','그치','자','요','이요','께서','입니다','죠','하나','우리','한번','음악','새끼','존나'
])

# ----------------------- Helper functions ----------------------------
ENCODINGS = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'iso-8859-1']

def smart_read_csv(path: str, **kwargs) -> pd.DataFrame:
    for enc in ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, **kwargs)

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

RE_HANGUL = re.compile(r'^[가-힣]+$')

def parse_tokens(x):
    if isinstance(x, list):
        return x
    if pd.isna(x):
        return []
    x = str(x).strip()
    try:
        if x.startswith('['):
            return ast.literal_eval(x)
        return x.split()
    except Exception:
        return x.split()

def clean_tokens(x):
    tokens = parse_tokens(x)
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS and RE_HANGUL.match(t)]

def tokens_to_string(tokens_list):
    return ' '.join(tokens_list)

# ----------------------- Core pipeline -------------------------------

def optimise_k(tfidf_matrix, k_min=2, k_max=10):
    best_k, best_score = k_min, -1
    scores = {}
    for k in range(k_min, min(k_max, tfidf_matrix.shape[0]-1)+1):
        km = KMeans(n_clusters=k, n_init='auto', random_state=42)
        labels = km.fit_predict(tfidf_matrix)
        if len(set(labels)) == 1:
            continue
        score = silhouette_score(tfidf_matrix, labels)
        scores[k] = score
        if score > best_score:
            best_k, best_score = k, score
    return best_k, scores

def top_terms(km: KMeans, tfidf: TfidfVectorizer, top_n=20):
    terms = np.array(tfidf.get_feature_names_out())
    return [terms[np.argsort(center)[-top_n:][::-1]].tolist() for center in km.cluster_centers_]

# --------------------------- Main ------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="YouTube subtitle KMeans topic modelling")
    parser.add_argument('--meta', default='game_api_data_sum.csv')
    parser.add_argument('--tokens', default='tokenized_docs.csv')
    parser.add_argument('--outdir', default='outputs')
    args = parser.parse_args()

    outdir = Path(args.outdir)
    ensure_dir(outdir)

    print('📥 Loading data …')
    meta_df  = smart_read_csv(args.meta)
    token_df = smart_read_csv(args.tokens, dtype={'tokens': str})

    required_cols = {'영상ID','게임명','viewCount'}
    if not required_cols.issubset(meta_df.columns):
        raise ValueError(f"Metadata CSV must contain columns {required_cols}")

    token_df['tokens'] = token_df['tokens'].fillna('[]')

    print('🧹 Cleaning tokens …')
    tqdm.pandas(desc='clean')
    token_df['clean_tokens'] = token_df['tokens'].progress_apply(clean_tokens)
    token_df['doc'] = token_df['clean_tokens'].apply(tokens_to_string)

    data = token_df.merge(meta_df[['영상ID','게임명','viewCount']], left_on='video_id', right_on='영상ID', how='inner')
    games = data['게임명'].unique()
    results = []

    for game in games:
        gdf = data[data['게임명'] == game].reset_index(drop=True)
        if len(gdf) < 5:
            warnings.warn(f"Skipping {game} (only {len(gdf)} docs)")
            continue

        print(f"\n🎮 Processing game: {game}  (docs={len(gdf)})")
        tfidf = TfidfVectorizer(tokenizer=str.split, lowercase=False)
        X = tfidf.fit_transform(gdf['doc'])

        best_k, scores = optimise_k(X)
        print(f"   ↳ best k = {best_k} (silhouette={scores.get(best_k,0):.3f})")

        plt.figure()
        plt.plot(list(scores.keys()), list(scores.values()), marker='o')
        plt.title(f"Silhouette vs k – {game}")
        plt.xlabel('k'); plt.ylabel('silhouette')
        plt.savefig(outdir / f"silhouette_{game}.png", bbox_inches='tight')
        plt.close()

        km = KMeans(n_clusters=best_k, n_init='auto', random_state=42)
        labels = km.fit_predict(X)
        gdf['cluster'] = labels

        keywords_per_cluster = top_terms(km, tfidf, top_n=20)
        for cid, kw in enumerate(keywords_per_cluster):
            # ▶▶ 출력 20개 모두 표시
            print(f"   • cluster {cid}: {', '.join(kw)}")
            wc = WordCloud(font_path=None, width=800, height=400, background_color='white')
            wc.generate(' '.join(kw))
            wc.to_file(str(outdir / f"wc_{game}_cluster{cid}.png"))

        cluster_view_mean = gdf.groupby('cluster')['viewCount'].mean().to_dict()
        gdf['topic_score'] = gdf['cluster'].map(cluster_view_mean)
        results.append(gdf[['video_id','cluster','topic_score']])

    if not results:
        print('❗ No results to save – check input data.')
        return

    all_scores = pd.concat(results, ignore_index=True)
    all_scores.to_csv(outdir / 'topic_scores.csv', index=False)
    print(f"✅ Saved topic_scores.csv (rows={len(all_scores)})")

    merged = meta_df.merge(all_scores, left_on='영상ID', right_on='video_id', how='left')
    merged.to_csv(outdir / 'total_game_api_data.csv', index=False)
    print(f"✅ Saved total_game_api_data.csv (rows={len(merged)}) → ready for ML")

if __name__ == '__main__':
    main()
