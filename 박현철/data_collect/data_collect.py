from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import isodate
import pandas as pd
import os
import time
from datetime import datetime, timedelta


API_KEY = 'AIzaSyBVfH5AA4ht6Y_mJ-JtiuV3eSK6l_5pJyU'  
search_queries = ['롤', '배틀그라운드', '닌텐도', '모바일 게임', '게임 리뷰', '인디 게임']
max_total = 500
per_request = 50

captions_folder = 'captions'
os.makedirs(captions_folder, exist_ok=True)

today = datetime.utcnow()
today_str = today.strftime('%Y%m%d')
csv_output_path = f'youtube_videos_{today_str}.csv'
today_ids_path = f'collected_ids_{today_str}.txt'
total_ids_path = 'collected_ids_total.txt'

# 게시일 조건: 60일 전 ~ 5일 전
published_before = (today - timedelta(days=5)).isoformat("T") + "Z"
published_after = (today - timedelta(days=60)).isoformat("T") + "Z"

# ================== 기존 수집 영상 불러오기 ==================
all_collected_ids = set()
if os.path.exists(total_ids_path):
    with open(total_ids_path, 'r', encoding='utf-8') as f:
        all_collected_ids = set(line.strip() for line in f)

# 다시 수집할 경우 코드 사용
today_collected_ids = set()
# 다시 수집할 경우 코드 사용
'''if os.path.exists(today_ids_path):
    os.remove(today_ids_path)  # ✅ 오늘자 ID 초기화

# 기존 CSV 불러오기 (오늘자 CSV는 삭제)
if os.path.exists(csv_output_path):
    os.remove(csv_output_path)
'''
video_data = []

# =================== API 객체 생성 ====================
youtube = build('youtube', 'v3', developerKey=API_KEY)

# ===================== 수집 시작 ======================
for query in search_queries:
    print(f"\n🔍 검색어: {query}")
    collected = 0
    next_page_token = None

    while collected < max_total:
        response = youtube.search().list(
            part='snippet',
            type='video',
            maxResults=min(per_request, max_total - collected),
            regionCode='KR',
            videoCategoryId='20',
            q=query,
            videoDuration='long',
            order='viewCount',
            pageToken=next_page_token
        ).execute()

        items = response.get('items', [])
        video_ids = [item['id']['videoId'] for item in items]
        channel_ids = [item['snippet']['channelId'] for item in items]

        # 중복 제거 (오늘자 제외하고 비교)
        new_video_ids = [vid for vid in video_ids if vid not in (all_collected_ids - today_collected_ids)]
        if not new_video_ids:
            print("새 영상 없음, 종료")
            break

        video_response = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            id=','.join(new_video_ids)
        ).execute()

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

            # 게시일 필터
            published_at = snippet.get('publishedAt', '')
            if not (published_after <= published_at <= published_before):
                continue

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
                '게시일': published_at,
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

            today_collected_ids.add(video_id)

        collected += len(new_video_ids)
        print(f"누적 수집: {collected}개")

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
        time.sleep(1)

# ===================== 결과 저장 ======================
# CSV 저장
df = pd.DataFrame(video_data)
df.to_csv(csv_output_path, index=False, encoding='utf-8-sig')
print(f"✅ CSV 저장 완료: {csv_output_path}")

# 오늘자 ID 저장
with open(today_ids_path, 'w', encoding='utf-8') as f:
    for vid in today_collected_ids:
        f.write(vid + '\n')
print(f"✅ 오늘자 videoId 저장 완료: {today_ids_path}")

# 전체 ID 업데이트 (오늘자 포함)
all_collected_ids.update(today_collected_ids)
with open(total_ids_path, 'w', encoding='utf-8') as f:
    for vid in all_collected_ids:
        f.write(vid + '\n')
print(f"✅ 누적 videoId 저장 완료: {total_ids_path}")