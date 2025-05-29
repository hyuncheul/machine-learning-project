import pandas as pd

# 1. 데이터 불러오기 (게임명, 태그, 조회수 포함)
df = pd.read_csv('game_api_data_sum.csv', encoding='cp949')

# 2. 전처리
df['tags'] = df['태그'].fillna('').astype(str)
df['viewCount'] = pd.to_numeric(df['viewCount'], errors='coerce')

# 3. 태그를 리스트로 분리
df['tag_list'] = df['tags'].apply(lambda x: x.split(','))

# 4. 게임별 + 태그별로 분해하고 통계 계산
game_tag_view_stats = (
    df.explode('tag_list')                                      # 태그 분해
    .assign(tag_list=lambda x: x['tag_list'].str.strip())       # 공백 제거
    .groupby(['게임명', 'tag_list'])['viewCount']                # 게임명 + 태그 기준
    .agg(['count', 'mean', 'median'])                           # 조회수 통계 계산
    .reset_index()
    .sort_values(by=['게임명', 'count'], ascending=[True, False])  # 보기 쉽게 정렬
)

# 5. 결과 저장 (선택)
# game_tag_view_stats.to_csv("game_tag_view_stats.csv", index=False, encoding='utf-8-sig')

# 6. 결과 미리 보기 (선택)
print(game_tag_view_stats.head(20))
