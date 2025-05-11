import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import isodate

# CSV 불러오기
df = pd.read_csv('youtube_game_videos.csv')

# 영상 길이(문자열) → 초(seconds) 변환
df['영상 길이 (초)'] = pd.to_timedelta(df['영상 길이']).dt.total_seconds()

# 제목 길이 계산
df['제목 길이'] = df['제목'].astype(str).apply(len)

# 조회수 정수형 변환
df['조회수'] = pd.to_numeric(df['조회수'], errors='coerce')

# 업로드 날짜 → 연도/월 추출
df['업로드 날짜'] = pd.to_datetime(df['업로드 날짜'])
df['업로드 연도'] = df['업로드 날짜'].dt.year
df['업로드 월'] = df['업로드 날짜'].dt.month

# ===============================
# 📊 1. 영상 길이 vs 조회수
plt.figure(figsize=(8, 5))
sns.scatterplot(data=df, x='영상 길이 (초)', y='조회수')
plt.title('Video Duration (sec) vs View Count')
plt.xlabel('Duration (sec)')
plt.ylabel('View Count')
plt.grid(True)
plt.show()

# 2. Title Length vs View Count (Boxplot)
plt.figure(figsize=(8, 5))
sns.boxplot(data=df, x='제목 길이', y='조회수')
plt.title('Title Length vs View Count (Boxplot)')
plt.xlabel('Title Length')
plt.ylabel('View Count')
plt.grid(True)
plt.show()

# 3. Average View Count by Upload Year
plt.figure(figsize=(8, 5))
sns.barplot(data=df, x='업로드 연도', y='조회수', estimator='mean')
plt.title('Average View Count by Upload Year')
plt.xlabel('Upload Year')
plt.ylabel('Average View Count')
plt.grid(True)
plt.show()