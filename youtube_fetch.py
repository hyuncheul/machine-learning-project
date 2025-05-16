from googleapiclient.discovery import build
import pandas as pd
import time
import datetime
import isodate  # duration 처리용

# ✅ API Key 입력
api_key = 'API_KEY'
youtube = build('youtube', 'v3', developerKey=api_key)

# ✅ 날짜 계산 (최근 3개월)
today = datetime.datetime.utcnow()
three_months_ago = today - datetime.timedelta(days=90)
published_after = three_months_ago.isoformat("T") + "Z"  # RFC3339 형식

# ✅ 영상 ID 수집
def get_video_ids(keyword, max_results=50, page_token=None):
    request = youtube.search().list(
        part='id,snippet',
        q=keyword,
        type='video',
        order='date',
        publishedAfter=published_after,
        maxResults=max_results,
        pageToken=page_token
    )
    response = request.execute()
    video_data = []
    for item in response['items']:
        video_data.append({
            'videoId': item['id']['videoId'],
            'channelId': item['snippet']['channelId']
        })
    next_page_token = response.get('nextPageToken')
    return video_data, next_page_token

# ✅ 영상 상세 정보 수집
def get_video_details(video_ids):
    request = youtube.videos().list(
        part='snippet,contentDetails,statistics',
        id=','.join(video_ids)
    )
    response = request.execute()
    
    result = []
    for item in response['items']:
        snippet = item['snippet']
        stats = item.get('statistics', {})
        details = item['contentDetails']
        try:
            # duration을 초 단위로 변환
            duration_seconds = isodate.parse_duration(details['duration']).total_seconds()
        except:
            duration_seconds = 0

        result.append({
            'videoId': item['id'],
            'title': snippet.get('title'),
            'description': snippet.get('description'),
            'publishedAt': snippet.get('publishedAt'),
            'tags': snippet.get('tags', []),
            'categoryId': snippet.get('categoryId'),
            'thumbnail': snippet['thumbnails']['high']['url'],
            'viewCount': int(stats.get('viewCount', 0)),
            'likeCount': int(stats.get('likeCount', 0)),
            'duration': duration_seconds,
            'channelId': snippet.get('channelId')
        })
    return result

# ✅ 채널 정보 수집
def get_channel_details(channel_ids):
    request = youtube.channels().list(
        part='statistics',
        id=','.join(channel_ids)
    )
    response = request.execute()
    channel_stats = {}
    for item in response['items']:
        stats = item['statistics']
        channel_stats[item['id']] = {
            'subscriberCount': int(stats.get('subscriberCount', 0)),
            'channelViewCount': int(stats.get('viewCount', 0)),
            'videoCount': int(stats.get('videoCount', 0))
        }
    return channel_stats

# ✅ 메인 실행
if __name__ == "__main__":
    keywords = ['발로란트','배틀그라운드','마인크래프트','리그 오브 레전드']
    all_video_data = []
    collected_video_ids = []
    max_pages = 3  # 키워드당 페이지 수

    for keyword in keywords:
        print(f"\n🔍 [키워드: {keyword}] 영상 ID 수집 중...")
        next_page_token = None
        for _ in range(max_pages):
            try:
                video_infos, next_page_token = get_video_ids(keyword, 50, next_page_token)
                collected_video_ids.extend(video_infos)
                print(f"✅ {len(video_infos)}개 수집 완료")
                time.sleep(1)
                if not next_page_token:
                    break
            except Exception as e:
                print(f"❌ 오류 발생: {e}")
                break

    print(f"\n🎯 총 {len(collected_video_ids)}개의 영상 ID 수집 완료.")

    # 영상 + 채널 상세 정보 수집
    final_data = []
    for i in range(0, len(collected_video_ids), 50):
        batch = collected_video_ids[i:i+50]
        video_ids = [v['videoId'] for v in batch]
        channel_ids = list(set([v['channelId'] for v in batch]))
        try:
            video_details = get_video_details(video_ids)
            channel_stats = get_channel_details(channel_ids)

            for video in video_details:
                channel_id = video['channelId']
                channel_info = channel_stats.get(channel_id, {})
                video.update({
                    'subscriberCount': channel_info.get('subscriberCount'),
                    'channelViewCount': channel_info.get('channelViewCount'),
                    'videoCount': channel_info.get('videoCount')
                })
                final_data.append(video)

            print(f"📦 누적 수집: {len(final_data)}개")
            time.sleep(1)
        except Exception as e:
            print(f"❌ 상세 데이터 수집 오류: {e}")

    # ✅ 롱폼 필터 (60초 초과만)
    df = pd.DataFrame(final_data)
    df = df[df['duration'] > 60]  # 쇼츠 제거

    # ✅ 조회수 내림차순 정렬
    df_sorted = df.sort_values(by='viewCount', ascending=False)

    # ✅ 저장
    df_sorted.to_csv('youtube_view_prediction_data.csv', index=False, encoding='utf-8-sig')
    print(f"\n✅ 최종 {len(df_sorted)}개의 롱폼 영상이 조회수 순으로 저장되었습니다.")
