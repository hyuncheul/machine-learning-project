from googleapiclient.discovery import build
import pandas as pd
import time

API_KEY = "AIzaSyBVfH5AA4ht6Y_mJ-JtiuV3eSK6l_5pJyU"  # ← 본인의 API 키 입력
yt = build("youtube", "v3", developerKey=API_KEY)

def get_related_channels(query, max_pages=5):
    channels = {}
    next_page_token = None

    for _ in range(max_pages):
        response = yt.search().list(
            q=query,
            type="channel",
            part="id,snippet",
            maxResults=50,
            pageToken=next_page_token,
            regionCode="KR",
            relevanceLanguage="ko"
        ).execute()

        for item in response["items"]:
            channel_id = item["id"]["channelId"]
            title = item["snippet"]["channelTitle"]
            if channel_id not in channels:
                channels[channel_id] = title

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.2)  # quota-safe sleep

    return pd.DataFrame([
        {"channelId": cid, "channelTitle": title}
        for cid, title in channels.items()
    ])

# 실행 예시
df_channels = get_related_channels("롤", max_pages=10)
print(df_channels.head())
df_channels.to_csv("related_lol_channels.csv", index=False)
