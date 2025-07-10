# ==============================================================================
# Cloud Function 1: GitHub 증분 데이터 수집 및 GCS 저장 (최종)
# Rate Limit 방지를 위해 time.sleep() 추가
# ==============================================================================

import os
import requests
import json
import time  # API 호출 딜레이를 위한 time 모듈
from datetime import datetime, timezone, timedelta
from google.cloud import storage, secretmanager, bigquery

# --- 클라이언트 초기화 (전역 범위) ---
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

# --- 환경 변수 및 설정 ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REPO_OWNER = os.getenv("REPO_OWNER")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
SECRET_ID = os.getenv("SECRET_ID")

# BigQuery 제어 테이블 정보
CONTROL_DATASET = "github_analytics"
CONTROL_TABLE = "pipeline_control"
PIPELINE_NAME = "github_collector"
TARGET_REPO_TABLE = "target_repositories"


def get_last_run_timestamp():
    """BigQuery 제어 테이블에서 마지막 성공 시간을 가져옵니다."""
    table_ref = f"{GCP_PROJECT_ID}.{CONTROL_DATASET}.{CONTROL_TABLE}"
    query = f"SELECT last_successful_timestamp FROM `{table_ref}` WHERE pipeline_name = '{PIPELINE_NAME}' LIMIT 1"

    try:
        query_job = bigquery_client.query(query)
        results = list(query_job.result())
        if results:
            last_run_time = results[0].last_successful_timestamp
            print(f"제어 테이블에서 마지막 실행 시간 로드: {last_run_time.isoformat()}")
            return last_run_time
    except Exception as e:
        print(f"[경고] 제어 테이블 조회 실패: {e}. 기본값으로 진행합니다.")

    default_start_time = datetime.now(timezone.utc) - timedelta(days=365)
    print(f"기본 시작 시간 설정: {default_start_time.isoformat()}")
    return default_start_time


def update_last_run_timestamp(new_timestamp):
    """BigQuery 제어 테이블에 마지막 성공 시간을 업데이트합니다."""
    table_ref = f"`{GCP_PROJECT_ID}.{CONTROL_DATASET}.{CONTROL_TABLE}`"
    query = f"""
        MERGE {table_ref} T
        USING (SELECT '{PIPELINE_NAME}' AS pipeline_name) AS S
        ON T.pipeline_name = S.pipeline_name
        WHEN MATCHED THEN
            UPDATE SET T.last_successful_timestamp = TIMESTAMP('{new_timestamp.isoformat()}')
        WHEN NOT MATCHED THEN
            INSERT (pipeline_name, last_successful_timestamp) VALUES(S.pipeline_name, TIMESTAMP('{new_timestamp.isoformat()}'))
    """
    bigquery_client.query(query).result()
    print(f"마지막 실행 시간 업데이트 완료: {new_timestamp.isoformat()}")


def get_github_token():
    """Secret Manager에서 GitHub PAT를 가져옵니다."""
    name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"
    response = secret_manager_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_target_repo_names():
    """BigQuery에서 수집 대상 저장소 목록을 가져옵니다."""
    table_ref = f"`{GCP_PROJECT_ID}.{CONTROL_DATASET}.{TARGET_REPO_TABLE}`"
    query = f"SELECT repo_name FROM {table_ref}"

    try:
        query_job = bigquery_client.query(query)
        repo_names = [row.repo_name for row in query_job.result()]
        print(f"BigQuery에서 {len(repo_names)}개의 수집 대상 저장소를 로드했습니다.")
        return repo_names
    except Exception as e:
        print(f"[에러] 수집 대상 저장소 목록 조회 실패: {e}")
        return []


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

        # --- 재시도 로직 시작 ---
        max_retries = 3
        base_delay = 10  # 초
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()  # 4xx, 5xx 에러 시 예외 발생
                data = response.json()
                break  # 성공 시 루프 탈출
            except requests.exceptions.HTTPError as http_e:
                # 403 오류이고, 이차 속도 제한일 가능성이 있을 때만 재시도
                if http_e.response.status_code == 403 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[경고] GitHub API 403 오류. {delay}초 후 재시도합니다... ({attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise http_e  # 마지막 시도이거나 다른 에러이면 그대로 에러 발생
        # --- 재시도 로직 끝 ---

        prs.extend(data['items'])

        if len(prs) >= data.get('total_count', 0) or not data['items']:
            break
        page += 1
        time.sleep(2)

    print(f"[{repo}] 총 {len(prs)}개의 PR 데이터를 가져왔습니다.")
    return prs


def upload_to_gcs(bucket_name, data, destination_blob_name):
    """가져온 데이터를 JSON 파일로 GCS 버킷에 업로드합니다."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    print(f"GCS에 업로드 중: gs://{bucket_name}/{destination_blob_name}")
    blob.upload_from_string(json.dumps(data, indent=2, ensure_ascii=False), content_type='application/json')
    print("업로드 완료!")


def run(event, context):
    """Pub/Sub 메시지에 의해 트리거되는 메인 함수"""
    print("=== 증분 데이터 수집 파이프라인 시작 ===")

    current_run_time = datetime.now(timezone.utc)
    start_time = get_last_run_timestamp()

    if (current_run_time - start_time) < timedelta(minutes=1):
        print("마지막 실행 후 시간이 너무 짧아 실행을 건너뜁니다.")
        print("=== 증분 데이터 수집 파이프라인 종료 ===")
        return

    try:
        github_token = get_github_token()
        target_repos = get_target_repo_names()

        for repo_name in target_repos:
            try:
                pr_data = fetch_prs_with_search(REPO_OWNER, repo_name, github_token, start_time, current_run_time)

                if pr_data:
                    file_path = f"raw/{REPO_OWNER}/{repo_name}/prs/{current_run_time.strftime('%Y-%m-%d')}/{current_run_time.isoformat()}.json"
                    upload_to_gcs(GCS_BUCKET_NAME, pr_data, file_path)
                time.sleep(2)

            except requests.exceptions.HTTPError as http_e:
                print(f"[API 에러] '{repo_name}' 저장소 처리 중 문제 발생: {http_e.response.status_code}")
            except Exception as repo_e:
                print(f"[에러] '{repo_name}' 저장소 처리 중 문제 발생: {repo_e}")

        update_last_run_timestamp(current_run_time)

    except Exception as e:
        print(f"[치명적 에러] 파이프라인 실행 중 문제 발생: {e}")
        raise e

    print("=== 증분 데이터 수집 파이프라인 종료 ===")