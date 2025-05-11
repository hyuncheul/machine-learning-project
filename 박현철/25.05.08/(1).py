from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import isodate
import pandas as pd
import os
import time

# API 설정
API_KEY = 'AIzaSyBVfH5AA4ht6Y_mJ-JtiuV3eSK6l_5pJyU'
youtube = build('youtube', 'v3', developerKey=API_KEY)
query = '게임'
max_total = 200
captions_folder = 'captions'
os.makedirs(captions_folder, exist_ok=True)

video_data = []
next_page_token = None
collected = 0
per_request = 50

while collected < max_total:
    response = youtube.search().list(
        part='snippet',
        type='video',
        maxResults=min(per_request, max_total - collected),
        regionCode='KR',
        videoCategoryId='20',
        q=query,
        videoDuration='long',
        pageToken=next_page_token
    ).execute()

    items = response.get('items', [])
    video_ids = [item['id']['videoId'] for item in items]
    channel_ids = [item['snippet']['channelId'] for item in items]

    # 영상 상세 정보
    video_response = youtube.videos().list(
        part='snippet,contentDetails,statistics',
        id=','.join(video_ids)
    ).execute()

    # 채널 정보
    channel_response = youtube.channels().list(
        part='statistics',
        id=','.join(set(channel_ids))
    ).execute()
    channel_stats = {item['id']: item['statistics'] for item in channel_response['items']}

    for item in video_response['items']:
        snippet = item['snippet']
        stats = item.get('statistics', {})
        content = item.get('contentDetails', {})

        video_id = item['id']
        channel_id = snippet['channelId']
        channel_stat = channel_stats.get(channel_id, {})

        # 자막 정보 수집
        try:
            caption_list = youtube.captions().list(part='snippet', videoId=video_id).execute()
            captions = caption_list.get('items', [])
            if captions:
                caption_id = captions[0]['id']
                caption_type = captions[0]['snippet'].get('trackKind', 'manual')
            else:
                caption_id, caption_type = '', ''
        except Exception:
            caption_id, caption_type = '', ''

        # 자막 파일 저장
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            transcript_text = '\n'.join([line['text'] for line in transcript])
            caption_path = os.path.join(captions_folder, f'{video_id}.txt')
            with open(caption_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)
            caption_note = caption_path
        except Exception:
            caption_note = ''

        video_data.append({
            '영상제목': snippet.get('title', ''),
            '영상설명': snippet.get('description', ''),
            '게시일': snippet.get('publishedAt', ''),
            '태그': ', '.join(snippet.get('tags', [])) if 'tags' in snippet else '',
            '카테고리': snippet.get('categoryId', ''),
            '썸네일': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            '조회수': stats.get('viewCount', ''),
            '좋아요': stats.get('likeCount', ''),
            '영상길이': isodate.parse_duration(content.get('duration', 'PT0S')).total_seconds(),
            '자막여부': content.get('caption', ''),
            '구독자 수': channel_stat.get('subscriberCount', ''),
            '채널 총 조회수': channel_stat.get('viewCount', ''),
            '업로드된 영상 수': channel_stat.get('videoCount', ''),
            '자막 ID': caption_id,
            '자막 유형': caption_type,
            '자막 파일': caption_note
        })

    collected += len(video_ids)
    print(f"✅ 누적 수집: {collected}개")

    next_page_token = response.get('nextPageToken')
    if not next_page_token:
        break
    time.sleep(1)

# CSV 저장
df = pd.DataFrame(video_data)
df.to_csv('youtube_game_videos.csv', index=False, encoding='utf-8-sig')
print("✅ CSV 저장 완료 + 자막 .txt 저장 완료")