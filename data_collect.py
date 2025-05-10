from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import isodate
import pandas as pd
import os
import time
from datetime import datetime

# ====================== 설정 ======================
API_KEY = 'AIzaSyBVfH5AA4ht6Y_mJ-JtiuV3eSK6l_5pJyU'  # 여기에 본인의 API 키 입력
query = '게임'
max_total = 5000
captions_folder = 'captions'
os.makedirs(captions_folder, exist_ok=True)

# 날짜 기반 저장 파일명
today_str = datetime.now().strftime('%Y%m%d')
csv_output_path = f'youtube_videos_{today_str}.csv'
collected_ids_path = 'collected_video_ids.txt'

# ================== 기존 수집 영상 불러오기 ==================
collected_video_ids = set()
if os.path.exists(collected_ids_path):
    with open(collected_ids_path, 'r', encoding='utf-8') as f:
        collected_video_ids = set(line.strip() for line in f)

# =================== API 객체 생성 ====================
youtube = build('youtube', 'v3', developerKey=API_KEY)

# ===================== 수집 시작 ======================
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
        videoCategoryId='20',  # 게임 카테고리
        q=query,
        videoDuration='long',
        pageToken=next_page_token
    ).execute()

    items = response.get('items', [])
    video_ids = [item['id']['videoId'] for item in items]
    channel_ids = [item['snippet']['channelId'] for item in items]

    # 중복 제거
    new_video_ids = [vid for vid in video_ids if vid not in collected_video_ids]
    if not new_video_ids:
        print("✅ 새 영상 없음, 종료")
        break

    # 상세 영상 정보
    video_response = youtube.videos().list(
        part='snippet,contentDetails,statistics',
        id=','.join(new_video_ids)
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

        # 자막 저장
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            transcript_text = '\n'.join([line['text'] for line in transcript])
            caption_path = os.path.join(captions_folder, f'{video_id}.txt')
            with open(caption_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)
            caption_note = caption_path
            caption_type = 'transcript_api'
        except Exception:
            caption_note = ''
            caption_type = ''

        video_data.append({
            '영상ID': video_id,
            '영상제목': snippet.get('title', ''),
            '영상설명': snippet.get('description', ''),
            '게시일': snippet.get('publishedAt', ''),
            '태그': ', '.join(snippet.get('tags', [])) if 'tags' in snippet else '',
            '카테고리': snippet.get('categoryId', ''),
            '썸네일': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            '조회수': stats.get('viewCount', ''),
            '좋아요': stats.get('likeCount', ''),
            '영상길이(초)': isodate.parse_duration(content.get('duration', 'PT0S')).total_seconds(),
            '자막여부': content.get('caption', ''),
            '구독자 수': channel_stat.get('subscriberCount', ''),
            '채널 총 조회수': channel_stat.get('viewCount', ''),
            '업로드된 영상 수': channel_stat.get('videoCount', ''),
            '자막 유형': caption_type,
            '자막 파일': caption_note
        })

        # 중복 방지를 위해 기록
        collected_video_ids.add(video_id)

    collected += len(new_video_ids)
    print(f"✅ 누적 수집: {collected}개")

    next_page_token = response.get('nextPageToken')
    if not next_page_token:
        break
    time.sleep(1)

# ===================== 결과 저장 ======================
# 1. CSV 저장
df = pd.DataFrame(video_data)
df.to_csv(csv_output_path, index=False, encoding='utf-8-sig')
print(f"✅ CSV 저장 완료: {csv_output_path}")

# 2. 수집된 videoId 기록
with open(collected_ids_path, 'w', encoding='utf-8') as f:
    for vid in collected_video_ids:
        f.write(vid + '\n')

print("✅ videoId 중복 로그 저장 완료")