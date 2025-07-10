# ==============================================================================
# 함수 2: Collector (데이터 수집가 / Worker)
# 역할: 단일 저장소의 PR 데이터를 수집하여 GCS에 저장
# ==============================================================================

import os
import requests
import json
import time
from datetime import datetime, timezone, timedelta
from google.cloud import storage, secretmanager, bigquery

# --- 클라이언트 초기화 (전역 범위) ---
# 함수가 여러 번 호출되어도 클라이언트를 한 번만 초기화하여 성능을 최적화합니다.
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

# --- 환경 변수 설정 ---
# 배포 시점에 --set-env-vars 플래그를 통해 설정할 값들입니다.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REPO_OWNER = os.getenv("REPO_OWNER")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
SECRET_ID = os.getenv("SECRET_ID")

# BigQuery 제어 테이블 정보
CONTROL_DATASET = "github_analytics"
CONTROL_TABLE = "pipeline_control"
PIPELINE_NAME = "github_collector"


def get_github_token():
    """Secret Manager에서 GitHub PAT를 가져옵니다."""
    name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"
    response = secret_manager_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_last_run_timestamp():
    """BigQuery 제어 테이블에서 마지막 성공 시간을 가져옵니다."""
    table_ref = f"{GCP_PROJECT_ID}.{CONTROL_DATASET}.{CONTROL_TABLE}"
    query = f"SELECT last_successful_timestamp FROM `{table_ref}` WHERE pipeline_name = '{PIPELINE_NAME}' LIMIT 1"
    try:
        results = list(bigquery_client.query(query).result())
        if results:
            return results[0].last_successful_timestamp
    except Exception as e:
        print(f"[경고] 제어 테이블 조회 실패: {e}. 기본값으로 진행합니다.")
    # 최초 실행이거나 에러 발생 시, 1년 전을 기본값으로 사용
    return datetime.now(timezone.utc) - timedelta(days=365)


def fetch_prs_with_search(owner, repo, token, start_time, end_time):
    """GitHub 검색 API를 사용하여 지정된 기간의 PR을 가져옵니다. (재시도 로직 포함)"""
    prs = []
    page = 1
    start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    query = f"repo:{owner}/{repo} is:pr created:{start_str}..{end_str}"
    print(f"[{repo}] 검색 시작 (기간: {start_str} ~ {end_str})")

    while True:
        url = "https://api.github.com/search/issues"
        headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        params = {'q': query, 'sort': 'created', 'order': 'asc', 'per_page': 100, 'page': page}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                break  # 성공 시 루프 탈출
            except requests.exceptions.HTTPError as http_e:
                if http_e.response.status_code == 403 and attempt < max_retries - 1:
                    delay = 10 * (2 ** attempt)
                    print(f"[{repo}] 경고: GitHub API 403 오류. {delay}초 후 재시도합니다... ({attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise http_e  # 마지막 시도이거나 다른 에러이면 그대로 에러 발생

        prs.extend(data.get('items', []))

        # 더 이상 가져올 데이터가 없으면 종료
        if len(prs) >= data.get('total_count', 0) or not data.get('items'):
            break
        page += 1
        time.sleep(2)  # 다음 페이지 요청 전 딜레이

    print(f"[{repo}] 총 {len(prs)}개의 PR 데이터를 가져왔습니다.")
    return prs


def upload_to_gcs(bucket_name, data, destination_blob_name):
    """가져온 데이터를 JSON 파일로 GCS 버킷에 업로드합니다."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    print(f"GCS에 업로드 중: gs://{bucket_name}/{destination_blob_name}")
    blob.upload_from_string(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
    print("업로드 완료!")


def run(request):
    """Cloud Tasks의 HTTP 요청을 받아 단일 저장소의 데이터를 수집합니다."""
    request_json = request.get_json(silent=True)
    if not request_json or 'repo_name' not in request_json:
        print("[에러] 요청 본문에 'repo_name'이 없습니다.")
        return ("Bad Request: 'repo_name' not found in payload", 400)

    repo_name = request_json['repo_name']
    print(f"=== '{repo_name}' 저장소 데이터 수집 시작 ===")

    # 일관된 파일명을 위해 현재 시간을 미리 정의
    current_run_time = datetime.now(timezone.utc)
    # 제어 테이블에서 마지막 성공 시간을 가져와 검색 시작 시간으로 사용
    start_time = get_last_run_timestamp()

    try:
        # 1. GitHub 인증 토큰 가져오기
        github_token = get_github_token()

        # 2. GitHub에서 특정 기간의 PR 데이터 가져오기
        pr_data = fetch_prs_with_search(REPO_OWNER, repo_name, github_token, start_time, current_run_time)

        # 3. 가져온 데이터가 있을 경우 GCS에 업로드
        if pr_data:
            file_path = f"raw/{REPO_OWNER}/{repo_name}/prs/{current_run_time.strftime('%Y-%m-%d')}/{current_run_time.isoformat()}.json"
            upload_to_gcs(GCS_BUCKET_NAME, pr_data, file_path)

    except Exception as e:
        print(f"[치명적 에러] '{repo_name}' 처리 중 문제 발생: {e}")
        # 에러 발생 시, Cloud Tasks가 재시도할 수 있도록 HTTP 500 에러를 반환
        return (f"Error processing {repo_name}: {e}", 500)

    print(f"=== '{repo_name}' 저장소 데이터 수집 종료 ===")
    # 모든 작업이 성공했을 때, 성공했다는 HTTP 200 OK 응답을 반환
    return ("Success", 200)