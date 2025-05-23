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
API_KEY = ''
if not API_KEY:
    print("오류: API_KEY가 설정되지 않았습니다. API 키를 입력해주세요.")
    exit()

SEARCH_QUERY = '게임'  # 검색할 키워드
MAX_TOTAL_VIDEOS_TO_COLLECT = 100  # 수집할 최대 영상 개수
VIDEOS_PER_REQUEST = 50  # 한 번의 API 요청으로 가져올 최대 영상 개수 (50보다 작게 설정하여 할당량 관리)
PUBLISHED_AFTER_DATE = "2024-01-01T00:00:00Z"  # 2024년 이후 영상
MINIMUM_VIDEO_DURATION_SECONDS = 480  # 영상 길이 필터링 기준 (초 단위, 8분 = 480초)
MAX_VIDEO_DURATION_SECONDS = 4000  # 최대 영상 길이 (2시간 = 7200초, 너무 긴 영상 제외)

# 오늘 날짜 가져오기
today_str = datetime.today().strftime('%Y_%m_%d')

# 바탕화면의 youtube-ML 경로 생성
BASE_FOLDER_PATH = os.path.join(os.path.expanduser("~"), 'Desktop', 'youtube-ML')
os.makedirs(BASE_FOLDER_PATH, exist_ok=True)

# 자막 폴더 및 CSV 파일 경로 설정
TRANSCRIPTS_FOLDER_NAME = os.path.join(BASE_FOLDER_PATH, f'transcripts_{today_str}')
CSV_FILE_NAME = os.path.join(BASE_FOLDER_PATH, f'game_videos_{today_str}.csv')
#QUOTA_LOG_FILE = os.path.join(BASE_FOLDER_PATH, 'api_quota_usage.json')

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

# 이미 수집된 비디오 ID를 저장할 집합
collected_video_ids = set()

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
    """API 호출 할당량 사용량을 업데이트하고 로그에 기록합니다."""
    api_quota_usage[api_method] += 1
    api_quota_usage["total_cost"] += QUOTA_COSTS[api_method]
    
    # 할당량 경고
    if api_quota_usage["total_cost"] > 9000:  # 일일 할당량 10,000의 90%
        print("⚠️ 경고: API 할당량의 90%를 사용했습니다. 곧 한도에 도달할 수 있습니다.")

def get_popular_game_videos(youtube, page_token=None):
    """인기 있는 게임 관련 영상을 검색합니다."""
    try:
        # 필요한 필드만 요청하여 응답 크기 최소화
        search_response = youtube.search().list(
            part="id,snippet",
            #q=SEARCH_QUERY,
            type="video",
            videoCategoryId="20",  # 게임 카테고리
            videoDefinition="high",  # 고화질 영상 (일반적으로 더 인기 있는 영상)
            maxResults=VIDEOS_PER_REQUEST,
            regionCode="KR",
            relevanceLanguage="ko",
            publishedAfter=PUBLISHED_AFTER_DATE,
            videoDuration="long",  # 20분 초과 영상만 검색
            order="viewCount",  # 'rating'은 인기도 기준 정렬 (viewCount, relevance도 고려 가능)
            pageToken=page_token,
            fields="nextPageToken,items(id(videoId),snippet(channelId,channelTitle,publishedAt,title))"
        ).execute()
        
        update_quota_usage("search.list")
        return search_response
    except Exception as e:
        print(f"❌ 영상 검색 중 오류 발생: {e}")
        time.sleep(5)  # API 오류 시 잠시 대기
        return {"items": []}

def get_videos_details(youtube, video_ids):
    """여러 비디오 ID에 대한 상세 정보를 가져옵니다."""
    if not video_ids:
        return []
    
    try:
        # 필요한 필드만 요청
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
    
    # 한 번에 요청할 채널 ID 수 제한 (최대 50개)
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
            
            time.sleep(0.5)  # API 요청 간 짧은 대기
        except Exception as e:
            print(f"❌ 채널 정보 조회 중 오류 발생: {e}")
            time.sleep(3)
    
    return channel_stats

def get_video_transcript(video_id):
    """영상의 자막을 가져와 텍스트로 반환합니다. 자동 생성 자막도 활용합니다."""
    transcript_text = ""
    transcript_type = "none"
    
    try:
        # 사용 가능한 모든 자막 목록 가져오기
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 1. 한국어 수동 자막 시도
        try:
            transcript = transcript_list.find_manually_created_transcript(['ko'])
            transcript_data = transcript.fetch()
            transcript_text = TextFormatter().format_transcript(transcript_data)
            transcript_type = "manual_ko"
            return transcript_text, transcript_type
        except:
            pass
        
        # 2. 한국어 자동 생성 자막 시도
        try:
            transcript = transcript_list.find_generated_transcript(['ko'])
            transcript_data = transcript.fetch()
            transcript_text = TextFormatter().format_transcript(transcript_data)
            transcript_type = "auto_ko"
            return transcript_text, transcript_type
        except:
            pass
        
        # 3. 영어 자막 + 번역 시도
        try:
            transcript = transcript_list.find_transcript(['en'])
            # 영어 자막을 한국어로 번역
            translated_transcript = transcript.translate('ko')
            transcript_data = translated_transcript.fetch()
            transcript_text = TextFormatter().format_transcript(transcript_data)
            transcript_type = "translated_ko"
            return transcript_text, transcript_type
        except:
            pass
        
        # 4. 다른 언어 자막 + 번역 시도
        try:
            # 사용 가능한 첫 번째 자막 선택
            transcript = next(iter(transcript_list))
            # 한국어로 번역
            translated_transcript = transcript.translate('ko')
            transcript_data = translated_transcript.fetch()
            transcript_text = TextFormatter().format_transcript(transcript_data)
            transcript_type = f"translated_from_other"
            return transcript_text, transcript_type
        except:
            pass
            
    except Exception as e:
        # 자막을 가져올 수 없는 경우
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
    
    if hours > 0:
        return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}"
    else:
        return f"{int(minutes):02d}:{int(seconds):02d}"

def main():
    """메인 함수: 유튜브 게임 영상 데이터를 수집하고 CSV로 저장합니다."""
    # 자막 저장 폴더 생성
    os.makedirs(TRANSCRIPTS_FOLDER_NAME, exist_ok=True)
    
    collected_video_ids = load_existing_video_ids()
    try:
        # YouTube API 서비스 객체 생성
        youtube = build('youtube', 'v3', developerKey=API_KEY)
    except Exception as e:
        print(f"❌ YouTube API 서비스 객체 생성 중 오류 발생: {e}")
        return
    
    video_data = []
    next_page_token = None
    total_processed = 0
    successfully_collected = 0
    
    print(f"🎮 '{SEARCH_QUERY}' 관련 인기 게임 영상 수집 시작 (목표: {MAX_TOTAL_VIDEOS_TO_COLLECT}개)")
    print(f"📅 {PUBLISHED_AFTER_DATE} 이후 게시된 20분 초과 영상 대상")
    
    # 수집 시작
    while successfully_collected < MAX_TOTAL_VIDEOS_TO_COLLECT:
        # API 할당량 확인
        if api_quota_usage["total_cost"] >= 9500:  # 일일 할당량 10,000의 95%
            print("⚠️ API 할당량이 거의 소진되었습니다. 데이터 수집을 중단합니다.")
            break
        
        # 1. 인기 게임 영상 검색
        search_response = get_popular_game_videos(youtube, next_page_token)
        search_items = search_response.get("items", [])
        
        if not search_items:
            print("📌 더 이상 검색 결과가 없습니다.")
            break
        
        # 검색된 영상 ID와 채널 ID 추출
        video_ids = []
        for item in search_items:
            video_id = item["id"]["videoId"]
            if video_id not in collected_video_ids:
                video_ids.append(video_id)
                collected_video_ids.add(video_id)
        
        total_processed += len(search_items)
        
        if not video_ids:
            # 모든 영상이 이미 수집된 경우 다음 페이지로
            next_page_token = search_response.get("nextPageToken")
            if not next_page_token:
                break
            continue
        
        # 2. 영상 상세 정보 가져오기
        video_details = get_videos_details(youtube, video_ids)
        
        if not video_details:
            # 상세 정보를 가져오지 못한 경우 다음 페이지로
            next_page_token = search_response.get("nextPageToken")
            if not next_page_token:
                break
            continue
        
        # 채널 ID 수집
        channel_ids = [item.get("snippet", {}).get("channelId") for item in video_details if "snippet" in item]
        
        # 3. 채널 통계 정보 가져오기
        channel_stats = get_channel_stats(youtube, channel_ids)
        
        # 4. 영상별 처리
        for video_item in video_details:
            if successfully_collected >= MAX_TOTAL_VIDEOS_TO_COLLECT:
                break

            content_details = video_item.get("contentDetails", {})
            duration_iso = content_details.get("duration", "PT0S")
            duration_seconds = isodate.parse_duration(duration_iso).total_seconds()

            if duration_seconds < MINIMUM_VIDEO_DURATION_SECONDS or duration_seconds > MAX_VIDEO_DURATION_SECONDS:
                continue

            video_id = video_item["id"]
            snippet = video_item.get("snippet", {})
            title = snippet.get('title', '')
            description = snippet.get('description', '')

            # 한글 포함 여부 확인
            has_korean = any(ord('가') <= ord(char) <= ord('힣') for char in title + description)
            if not has_korean:
                continue

            channel_id = snippet.get("channelId", "")
            
            # 💡 여기서 한국 채널 여부 확인
            try:
                channels_response = youtube.channels().list(
                    part="snippet",
                    id=channel_id,
                    fields="items(snippet(country))"
                ).execute()
                update_quota_usage("channels.list")
                country = channels_response['items'][0]['snippet'].get('country', '')
                if country != 'KR':
                    continue
            except Exception as e:
                print(f"❌ 채널 국가 확인 중 오류: {e}")
                continue

            stats = video_item.get("statistics", {})
            channel_stat_info = channel_stats.get(channel_id, {})
            
            # 5. 자막 가져오기
            transcript_text, transcript_type = get_video_transcript(video_id)
            transcript_file_path = save_transcript_to_file(video_id, transcript_text)
            
            # 6. 데이터 저장
            video_data.append({
                '영상ID': video_id,
                '영상제목': snippet.get('title', ''),
                '영상설명': snippet.get('description', ''),
                '게시일': snippet.get('publishedAt', ''),
                '태그': ', '.join(snippet.get('tags', [])),
                '카테고리ID': snippet.get('categoryId', ''),
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
                '자막유형': transcript_type,
            })
            
            successfully_collected += 1
            print(f"✅ [{successfully_collected}/{MAX_TOTAL_VIDEOS_TO_COLLECT}] 수집: {snippet.get('title', '')[:40]}... (길이: {format_duration(duration_seconds)}, 조회수: {stats.get('viewCount', '0')})")
        
        # 다음 페이지 토큰 설정
        next_page_token = search_response.get("nextPageToken")
        if not next_page_token:
            print("📌 모든 검색 결과를 확인했습니다.")
            break
        
        # API 요청 간 대기 시간 (무작위로 설정하여 API 제한 방지)
        wait_time = random.uniform(1.0, 2.5)
        print(f"--- 현재까지 {successfully_collected}개 수집, 다음 페이지 요청 대기 ({wait_time:.1f}초) ---")
        time.sleep(wait_time)
    
    # 7. CSV 파일로 저장
    if video_data:
        # 새로운 데이터를 DataFrame으로 변환
        new_df = pd.DataFrame(video_data)
        
        # 기존 CSV 파일이 있으면 병합
        if os.path.exists(CSV_FILE_NAME):
            try:
                existing_df = pd.read_csv(CSV_FILE_NAME)
                # 기존 데이터와 새 데이터 병합
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                # 영상 ID 기준으로 중복 제거 (첫 번째 항목 유지)
                combined_df.drop_duplicates(subset=['영상ID'], keep='first', inplace=True)
                combined_df.to_csv(CSV_FILE_NAME, index=False, encoding='utf-8-sig')
                print(f"\n✅ 기존 {len(existing_df)}개 + 새로운 {len(new_df)}개 = 총 {len(combined_df)}개 영상 데이터 (중복 제거 후)")
            except Exception as e:
                print(f"데이터 병합 중 오류 발생: {e}")
                # 오류 발생 시 새 데이터만 저장
                new_df.to_csv(CSV_FILE_NAME, index=False, encoding='utf-8-sig')
                print(f"\n✅ 총 {len(new_df)}개의 게임 영상 데이터를 '{CSV_FILE_NAME}' 파일로 저장 완료했습니다.")
        else:
            # 기존 파일이 없으면 새로 저장
            new_df.to_csv(CSV_FILE_NAME, index=False, encoding='utf-8-sig')
            print(f"\n✅ 총 {len(new_df)}개의 게임 영상 데이터를 '{CSV_FILE_NAME}' 파일로 저장 완료했습니다.")
        
        print(f"✅ 자막 파일은 '{TRANSCRIPTS_FOLDER_NAME}' 폴더에 저장되었습니다.")
    else:
        print("\n❌ 조건에 맞는 영상 데이터가 수집되지 않았습니다.")
    
    # 8. API 사용량 요약
    print("\n📊 API 할당량 사용 현황:")
    for method, count in api_quota_usage.items():
        if method != "total_cost":
            cost = count * QUOTA_COSTS[method]
            print(f"  - {method}: {count}회 호출 (비용: {cost} 단위)")
    print(f"  - 총 사용량: {api_quota_usage['total_cost']} / 10,000 단위")

if __name__ == "__main__":
    main()x