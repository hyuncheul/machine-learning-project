import os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import numpy as np

# 📂 자막 불러오기
captions_folder = 'captions'
texts = []
video_ids = []

for file in os.listdir(captions_folder):
    if file.endswith('.txt'):
        with open(os.path.join(captions_folder, file), encoding='utf-8') as f:
            texts.append(f.read())
            video_ids.append(file.replace('.txt', ''))

# 📊 TF-IDF 벡터화
vectorizer = TfidfVectorizer(max_features=3000, stop_words='english')
X = vectorizer.fit_transform(texts)

# 🔗 KMeans 클러스터링
n_clusters = 3
kmeans = KMeans(n_clusters=n_clusters, random_state=42)
labels = kmeans.fit_predict(X)

# 📁 메타데이터 조회수 불러오기
df_meta = pd.read_csv('youtube_game_videos.csv')  # 영상 ID + 조회수 있어야 함
df_meta['영상 ID'] = df_meta['영상 ID'].astype(str)
df_meta['조회수'] = pd.to_numeric(df_meta['조회수'], errors='coerce')

# 📋 군집 결과 정리
df = pd.DataFrame({'영상 ID': video_ids, '군집 번호': labels})
df = df.merge(df_meta[['영상 ID', '조회수']], on='영상 ID', how='left')

# 📌 군집별 키워드 추출 + 군집명 지정
terms = vectorizer.get_feature_names_out()
cluster_keywords = []
for i in range(n_clusters):
    center = kmeans.cluster_centers_[i]
    top_terms = np.argsort(center)[-5:]
    keywords = [terms[idx] for idx in reversed(top_terms)]
    cluster_keywords.append(', '.join(keywords))

# 🧮 군집별 평균 조회수
df_grouped = df.groupby('군집 번호')['조회수'].agg(['count', 'mean', 'sum']).reset_index()
df_grouped['주요 키워드'] = cluster_keywords
df_grouped['군집명'] = df_grouped['주요 키워드'] + '\n(Avg: ' + df_grouped['mean'].round().astype(str) + ')'

# 📊 파이차트: 인기 콘텐츠 유형별 분포
plt.figure(figsize=(7, 7))
plt.pie(df_grouped['count'], labels=df_grouped['군집명'], autopct='%1.1f%%', startangle=140)
plt.title('자막 기반 콘텐츠 유형 분포 (조회수 기반)')
plt.axis('equal')
plt.tight_layout()
plt.show()

# 📤 결과 저장
df.to_csv('caption_cluster_result.csv', index=False, encoding='utf-8-sig')
df_grouped.to_csv('caption_cluster_summary.csv', index=False, encoding='utf-8-sig')