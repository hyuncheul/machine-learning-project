from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import isodate
import pandas as pd
import os
import time
from datetime import datetime
import json
import random

# -------------------- 설정 값 -------------------- #
API_KEY = '' # 여기에 본인의 API 키를 입력하세요.
if not API_KEY:
    print("오류: API_KEY가 설정되지 않았습니다. API 키를 입력해주세요.")
    exit()

SEARCH_KEYWORDS = [
    '롤', '리그오브레전드', '마인크래프트', '발로란트', 
    'FC온라인', '오버워치', '배틀그라운드', '던전앤파이터',
    '서든어택', '로스트아크', '메이플스토리', '스타크래프트'
]
MAX_TOTAL_VIDEOS_TO_COLLECT = 2000
VIDEOS_PER_REQUEST = 50
PUBLISHED_AFTER_DATE = "2024-10-01T00:00:00Z"
PUBLISHED_BEFORE_DATE = "2025-01-01T00:00:00Z"
MINIMUM_VIDEO_DURATION_SECONDS = 480  # 8분
MAX_VIDEO_DURATION_SECONDS = 7200     # 2시간

# 오늘 날짜 가져오기
today_str = datetime.today().strftime('%Y_%m_%d')

# 현재 파일이 있는 폴더 경로를 BASE_FOLDER_PATH로 설정
BASE_FOLDER_PATH = os.path.dirname(os.path.abspath(__file__))
os.makedirs(BASE_FOLDER_PATH, exist_ok=True)

# 자막 폴더 경로를 BASE_FOLDER_PATH 하위의 transcripts_api로 설정
TRANSCRIPTS_FOLDER_NAME = os.path.join(BASE_FOLDER_PATH, 'transcripts_api')
os.makedirs(TRANSCRIPTS_FOLDER_NAME, exist_ok=True)

# CSV 파일 경로 설정
CSV_FILE_NAME = os.path.join(BASE_FOLDER_PATH, 'game_api_data.csv')

# API 할당량 추적을 위한 카운터 초기화
api_quota_usage = {
    "search.list": 0,
    "videos.list": 0,
    "channels.list": 0,
    "captions.list": 0,
    "total_cost": 0
}

# 할당량 비용 (단위)
QUOTA_COSTS = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "captions.list": 50
}

# -------------------- 함수 정의 -------------------- #

def load_existing_video_ids():
    """기존 CSV 파일에서 이미 수집한 영상 ID를 로드합니다."""
    existing_ids = set()
    try:
        if os.path.exists(CSV_FILE_NAME):
            df = pd.read_csv(CSV_FILE_NAME)
            if '영상ID' in df.columns:
                existing_ids = set(df['영상ID'].tolist())
                print(f"이미 수집된 {len(existing_ids)}개 영상 ID를 로드했습니다.")
    except Exception as e:
        print(f"기존 데이터 로드 중 오류 발생: {e}")
    return existing_ids

def update_quota_usage(api_method):
    """API 호출 할당량 사용량을 업데이트합니다."""
    api_quota_usage[api_method] += 1
    api_quota_usage["total_cost"] += QUOTA_COSTS[api_method]
    
    if api_quota_usage["total_cost"] > 9000:
        print("⚠️ 경고: API 할당량의 90%를 사용했습니다.")

def get_popular_game_videos(youtube, search_query, page_token=None):
    """인기 있는 게임 관련 영상을 검색합니다."""
    try:
        search_response = youtube.search().list(
            part="id,snippet",
            q=search_query,
            type="video",
            videoCategoryId="20",
            maxResults=VIDEOS_PER_REQUEST,
            regionCode="KR",
            relevanceLanguage="ko",
            publishedAfter=PUBLISHED_AFTER_DATE,
            publishedBefore=PUBLISHED_BEFORE_DATE,
            order="relevance",
            pageToken=page_token,
            fields="nextPageToken,items(id(videoId),snippet(channelId,channelTitle,publishedAt,title))"
        ).execute()
        
        update_quota_usage("search.list")
        return search_response
    except Exception as e:
        print(f"❌ 영상 검색 중 오류 발생: {e}")
        time.sleep(5)
        return {"items": []}

def get_videos_details(youtube, video_ids):
    """여러 비디오 ID에 대한 상세 정보를 가져옵니다."""
    if not video_ids:
        return []
    
    try:
        video_response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(video_ids),
            fields="items(id,snippet(title,description,publishedAt,tags,thumbnails/high/url,channelId,channelTitle),contentDetails(duration,caption),statistics(viewCount,likeCount,commentCount))"
        ).execute()
        
        update_quota_usage("videos.list")
        return video_response.get("items", [])
    except Exception as e:
        print(f"❌ 영상 상세 정보 조회 중 오류 발생: {e}")
        time.sleep(3)
        return []

def get_channel_stats(youtube, channel_ids):
    """채널 ID 목록에 대한 통계 정보를 가져옵니다."""
    if not channel_ids:
        return {}
    
    unique_channel_ids = list(set(channel_ids))
    channel_stats = {}
    
    for i in range(0, len(unique_channel_ids), 50):
        batch_channel_ids = unique_channel_ids[i:i+50]
        try:
            channel_response = youtube.channels().list(
                part="statistics",
                id=",".join(batch_channel_ids),
                fields="items(id,statistics(subscriberCount,viewCount,videoCount))"
            ).execute()
            
            update_quota_usage("channels.list")
            
            for item in channel_response.get("items", []):
                channel_stats[item["id"]] = item.get("statistics", {})
            
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ 채널 정보 조회 중 오류 발생: {e}")
            time.sleep(3)
    
    return channel_stats

def get_video_transcript(video_id):
    """영상의 자막을 가져옵니다."""
    transcript_text = ""
    transcript_type = "none"
    
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(['ko'])
            transcript_data = transcript.fetch()
            transcript_text = TextFormatter().format_transcript(transcript_data)
            transcript_type = "manual_ko"
        except:
            try:
                transcript = transcript_list.find_generated_transcript(['ko'])
                transcript_data = transcript.fetch()
                transcript_text = TextFormatter().format_transcript(transcript_data)
                transcript_type = "auto_ko"
            except:
                pass
    except Exception as e:
        pass
    
    return transcript_text, transcript_type

def save_transcript_to_file(video_id, transcript_text):
    """자막 텍스트를 파일로 저장합니다."""
    if not transcript_text:
        return ""
    
    try:
        transcript_file_path = os.path.join(TRANSCRIPTS_FOLDER_NAME, f"{video_id}.txt")
        with open(transcript_file_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
        return transcript_file_path
    except Exception as e:
        print(f"❌ 자막 파일 저장 중 오류 발생: {e}")
        return ""

def format_duration(seconds):
    """초 단위 시간을 '시:분:초' 형식으로 변환합니다."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}" if hours else f"{int(minutes):02d}:{int(seconds):02d}"

def main():
    os.makedirs(TRANSCRIPTS_FOLDER_NAME, exist_ok=True)
    collected_video_ids = load_existing_video_ids()
    
    try:
        youtube = build('youtube', 'v3', developerKey=API_KEY)
    except Exception as e:
        print(f"❌ YouTube API 서비스 객체 생성 중 오류 발생: {e}")
        return

    video_data = []
    successfully_collected = 0

    print(f"🎮 게임 키워드별 인기 영상 수집 시작 (목표: {MAX_TOTAL_VIDEOS_TO_COLLECT}개)")
    
    for search_query in SEARCH_KEYWORDS:
        if successfully_collected >= MAX_TOTAL_VIDEOS_TO_COLLECT:
            break
            
        print(f"\n🔍 현재 키워드: {search_query}")
        next_page_token = None
        
        while successfully_collected < MAX_TOTAL_VIDEOS_TO_COLLECT:
            if api_quota_usage["total_cost"] >= 9500:
                print("⚠️ API 할당량이 거의 소진되었습니다.")
                break

            search_response = get_popular_game_videos(youtube, search_query, next_page_token)
            search_items = search_response.get("items", [])
            
            if not search_items:
                break

            video_ids = []
            for item in search_items:
                video_id = item["id"]["videoId"]
                if video_id not in collected_video_ids:
                    video_ids.append(video_id)
                    collected_video_ids.add(video_id)

            if not video_ids:
                next_page_token = search_response.get("nextPageToken")
                if not next_page_token:
                    break
                continue

            video_details = get_videos_details(youtube, video_ids)
            if not video_details:
                next_page_token = search_response.get("nextPageToken")
                if not next_page_token:
                    break
                continue

            channel_ids = [item.get("snippet", {}).get("channelId") for item in video_details if "snippet" in item]
            channel_stats = get_channel_stats(youtube, channel_ids)

            for video_item in video_details:
                if successfully_collected >= MAX_TOTAL_VIDEOS_TO_COLLECT:
                    break

                content_details = video_item.get("contentDetails", {})
                duration_iso = content_details.get("duration", "PT0S")
                duration_seconds = isodate.parse_duration(duration_iso).total_seconds()
                
                if not (MINIMUM_VIDEO_DURATION_SECONDS <= duration_seconds <= MAX_VIDEO_DURATION_SECONDS):
                    continue

                snippet = video_item.get("snippet", {})
                title = snippet.get('title', '')
                description = snippet.get('description', '')
                
                if not any(ord('가') <= ord(c) <= ord('힣') for c in title + description):
                    continue

                video_id = video_item["id"]
                stats = video_item.get("statistics", {})
                channel_id = snippet.get("channelId", "")
                channel_stat_info = channel_stats.get(channel_id, {})

                transcript_text, transcript_type = get_video_transcript(video_id)
                save_transcript_to_file(video_id, transcript_text)

                video_data.append({
                    '수집일자': today_str,
                    '영상ID': video_id,
                    '영상제목': title,
                    '영상설명': description,
                    '게시일': snippet.get('publishedAt', ''),
                    '태그': ', '.join(snippet.get('tags', [])),
                    '썸네일URL': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                    '조회수': int(stats.get('viewCount', 0)),
                    '좋아요수': int(stats.get('likeCount', 0)),
                    '댓글수': int(stats.get('commentCount', 0)),
                    '영상길이(초)': int(duration_seconds),
                    '영상길이(표시)': format_duration(duration_seconds),
                    '자막여부': content_details.get('caption', 'false'),
                    '채널ID': channel_id,
                    '채널명': snippet.get('channelTitle', ''),
                    '구독자수': int(channel_stat_info.get('subscriberCount', 0)),
                    '채널총조회수': int(channel_stat_info.get('viewCount', 0)),
                    '채널업로드영상수': int(channel_stat_info.get('videoCount', 0)),
                    '자막유형': transcript_type
                })

                successfully_collected += 1
                print(f"✅ [{successfully_collected}/{MAX_TOTAL_VIDEOS_TO_COLLECT}] {title[:40]}...")

            next_page_token = search_response.get("nextPageToken")
            if not next_page_token:
                break
            time.sleep(random.uniform(1.0, 2.5))
            
            # ✅ 키워드 단위 사용량 출력
            print(f"\n📊 '{search_query}' 키워드 수집 후 누적 API 사용량: {api_quota_usage['total_cost']}/10,000 단위\n")
            time.sleep(random.uniform(1.5, 3.0))  # 다음 키워드 전 대기


    if video_data:
        df = pd.DataFrame(video_data)
        if os.path.exists(CSV_FILE_NAME):
            existing_df = pd.read_csv(CSV_FILE_NAME)
            combined_df = pd.concat([existing_df, df], ignore_index=True)
            combined_df.drop_duplicates(subset=['영상ID'], keep='first', inplace=True)
            combined_df.to_csv(CSV_FILE_NAME, index=False, encoding='utf-8-sig')
            print(f"\n✅ 총 {len(combined_df)}개 영상 데이터 저장 완료 (기존 {len(existing_df)}개 + 새로운 {len(df)}개)")
        else:
            df.to_csv(CSV_FILE_NAME, index=False, encoding='utf-8-sig')
            print(f"\n✅ 총 {len(df)}개 영상 데이터 저장 완료")
    else:
        print("\n❌ 수집된 영상이 없습니다.")

    print("\n📊 API 할당량 사용 현황:")
    for method, count in api_quota_usage.items():
        if method != "total_cost":
            print(f"  - {method}: {count}회 호출 ({count * QUOTA_COSTS[method]} 단위)")
    print(f"  - 총 사용량: {api_quota_usage['total_cost']}/10,000 단위")

if __name__ == "__main__":
    main()
