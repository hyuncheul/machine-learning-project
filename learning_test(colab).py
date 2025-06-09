# 라이브러리
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib.ticker as ticker

# 시각화용 한글 단위 설정
def format_yticks_log(val, pos):
    true_val = np.expm1(val)
    if true_val >= 1e6:
        return f"{true_val/1e6:.1f}백만 회"
    elif true_val >= 1e4:
        return f"{true_val/1e4:.1f}만 회"
    elif true_val >= 1e3:
        return f"{true_val/1e3:.0f}천 회"
    else:
        return f"{int(true_val)}회"

def plot_prediction_comparison(y_train, y_train_pred, y_test, y_test_pred, game_name):
    plt.figure(figsize=(8, 6))
    plt.scatter(np.log1p(y_train), np.log1p(y_train_pred), alpha=0.4, label="Train", c='blue', marker='o')
    plt.scatter(np.log1p(y_test), np.log1p(y_test_pred), alpha=0.7, label="Test", c='red', marker='x')

    min_val = min(np.log1p(y_train).min(), np.log1p(y_test).min())
    max_val = max(np.log1p(y_train).max(), np.log1p(y_test).max())
    plt.plot([min_val, max_val], [min_val, max_val], 'k--')

    plt.title(f'📊 실제 vs 예측 조회수 (log scale) - {game_name}')
    plt.xlabel('실제 조회수')
    plt.ylabel('예측 조회수')
    plt.legend()
    plt.grid(True)

    ax = plt.gca()
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_yticks_log))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(format_yticks_log))

    plt.tight_layout()
    plt.show()

# 데이터 로딩 및 전처리
df = pd.read_csv("merged_result.csv")

def categorize_hour(hour):
    if 6 <= hour < 12: return '오전'
    elif 12 <= hour < 18: return '오후'
    elif 18 <= hour < 24: return '저녁'
    else: return '새벽'

df['시간대'] = df['업로드_시각'].apply(categorize_hour)
df['얼굴_감지여부'] = df['얼굴_감지여부'].astype(int)

# 피처 정의
feature_cols = [
    '영상길이(초)', '채널총조회수', '채널업로드영상수',
    'topic_score', '업로드_경과일', '게시_분기',
    '텍스트_개수', '텍스트_신뢰도', '텍스트_비중',
    '얼굴_개수', '얼굴_비중',
    '감정_angry', '감정_disgust', '감정_fear', '감정_happy',
    '감정_sad', '감정_surprise', '감정_neutral',
    '요일', '시간대', '주요_감정', '얼굴_감지여부'
]
target_col = '조회수'
categorical_features = ['요일', '시간대', '주요_감정']
numeric_features = list(set(feature_cols) - set(categorical_features))

# 게임별 반복 분석
for game in df['게임명_x'].dropna().unique():
    print(f"\n🎮 [게임명: {game}]")

    df_game = df[df['게임명_x'] == game]
    df_game_filtered = df_game[feature_cols + [target_col]].dropna()

    if len(df_game_filtered) < 100:
        print(f"⚠️ 데이터 수 부족: {len(df_game_filtered)}개 → 스킵")
        continue

    X = df_game_filtered[feature_cols]
    y = df_game_filtered[target_col]

    preprocessor = ColumnTransformer([
        ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
    ], remainder='passthrough')

    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('regressor', XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42))
    ])

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline.fit(X_train, y_train)

    y_train_pred = pipeline.predict(X_train)
    y_test_pred = pipeline.predict(X_test)

    mse = mean_squared_error(y_test, y_test_pred)
    r2 = r2_score(y_test, y_test_pred)
    print(f"✅ MSE: {mse:,.0f} | R²: {r2:.3f}")

    plot_prediction_comparison(y_train, y_train_pred, y_test, y_test_pred, game)
