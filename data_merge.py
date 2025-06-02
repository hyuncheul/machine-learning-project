import pandas as pd

df = pd.read_csv("total_game_api_data.csv")
tag_score_df = pd.read_csv("video_with_tag_score.csv")

tag_mean_df = tag_score_df.groupby('채널ID', as_index=False)['tag_mean_score'].mean()

df = df.merge(tag_mean_df, on='채널ID', how='left')

df['tag_mean_score'] = df.groupby('게임명')['tag_mean_score'].transform(lambda x: x.fillna(x.mean()))

df.to_csv("merged_game_api_data.csv", index=False)

print("✅ 병합 및 저장 완료! → merged_game_api_data.csv")
