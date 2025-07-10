# ==============================================================================
# 로컬 개발 환경에서 GitHub 데이터 수집을 테스트하기 위한 스크립트 (수정 완료)
# ==============================================================================

# --- 1. 필요한 라이브러리 가져오기 ---
import os
import requests
import json
from datetime import datetime, timezone
from google.cloud import storage
from dotenv import load_dotenv  # .env 파일을 사용하기 위한 라이브러리

# --- 2. 설정: .env 파일 로드 및 환경 변수 설정 ---

# .env 파일을 로드하여 파일 안의 변수들을 환경 변수로 설정합니다.
load_dotenv()

# GitHub Personal Access Token (PAT). .env 파일에서 값을 가져옵니다.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# 분석하려는 GitHub 저장소의 소유자 (조직 또는 개인 계정 이름)
REPO_OWNER = "BCSDLab"

# 분석하려는 GitHub 저장소의 이름
# FIX: 여러 저장소를 분석하려면 이 부분을 리스트로 만들고 반복문을 사용해야 합니다.
#      우선 하나의 저장소를 대상으로 테스트합니다.
REPO_NAME = "KOIN_ANDROID"  # 예시: 'KOIN_ANDROID'

# 수집한 데이터를 저장할 Google Cloud Storage(GCS) 버킷의 이름
GCS_BUCKET_NAME = "bcsd-github-analytics-row-data"

# [FIX-1] GCP 인증을 위한 서비스 계정 키 파일 경로 수정
# 윈도우 경로의 역슬래시(\)는 파이썬에서 특수 문자로 인식될 수 있어 문제를 일으킵니다.
# 1. 슬래시(/)를 사용하거나
# 2. 역슬래시를 두 개(\\) 사용하거나
# 3. 문자열 앞에 r을 붙여 raw string으로 만들어야 합니다.
# 여기서는 가장 일반적인 슬래시 방식으로 수정했습니다.
# 또한, 이 코드를 다른 사람과 공유할 때를 대비하여 터미널에서 환경 변수를 설정하는 것이 가장 좋은 방법입니다.
# os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "C:/Users/march/Desktop/key/bcsd-github-752b7f944cfa.json"


# --- 3. GitHub API 호출 함수 ---
def fetch_github_prs(owner, repo, token):
    """
    지정된 GitHub 저장소에서 Pull Request 목록을 가져옵니다.
    """
    # [FIX-2] URL 주소에서 불필요한 꺾쇠(<, >)를 제거했습니다.
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    params = {
        'state': 'all',
        'sort': 'updated',
        'direction': 'desc',
        'per_page': 10
    }

    print(f"GitHub API에 요청 시작: {owner}/{repo} 저장소의 PR 데이터를 가져옵니다...")
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    print(f"성공! {len(response.json())}개의 PR 데이터를 가져왔습니다.")
    return response.json()


# --- 4. GCS에 파일 업로드 함수 ---
def upload_to_gcs(bucket_name, data, destination_blob_name):
    """
    가져온 데이터를 JSON 파일로 GCS 버킷에 업로드합니다.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    print(f"GCS에 파일 업로드 시작: gs://{bucket_name}/{destination_blob_name}")
    blob.upload_from_string(
        json.dumps(data, indent=2, ensure_ascii=False),  # 한글이 깨지지 않도록 ensure_ascii=False 추가
        content_type='application/json'
    )
    print("파일 업로드 완료!")


# --- 5. 스크립트 메인 실행 부분 ---
if __name__ == "__main__":
    print("=== 로컬 디버깅 스크립트 시작 ===")
    try:
        # GITHUB_TOKEN이 제대로 설정되었는지 확인
        if not GITHUB_TOKEN:
            raise ValueError("환경 변수 GITHUB_TOKEN이 설정되지 않았습니다. .env 파일을 확인해주세요.")

        # 1단계: GitHub에서 데이터 가져오기
        pr_data = fetch_github_prs(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)

        if pr_data:
            # 2단계: GCS에 저장할 파일 경로와 이름 생성
            utc_now = datetime.now(timezone.utc)
            file_path = f"raw/{REPO_OWNER}/{REPO_NAME}/prs/{utc_now.strftime('%Y/%m/%d')}/{utc_now.isoformat()}.json"

            # 3단계: GCS에 데이터 업로드
            upload_to_gcs(GCS_BUCKET_NAME, pr_data, file_path)

    except requests.exceptions.HTTPError as e:
        print(f"[에러 발생] GitHub API 에러: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"[에러 발생] 예상치 못한 에러: {e}")

    print("=== 로컬 디버깅 스크립트 종료 ===")