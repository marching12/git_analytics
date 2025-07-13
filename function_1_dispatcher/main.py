# function_1_dispatcher/main.py (환경변수 적용 버전)
import os
import json
import logging
import base64
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

import config
import requests
from google.cloud import tasks_v2, bigquery, secretmanager
from google.oauth2 import id_token
from google.auth.transport import requests as auth_requests

# --- 로깅 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
tasks_client = tasks_v2.CloudTasksClient()
bigquery_client = bigquery.Client()
secret_client = secretmanager.SecretManagerServiceClient()

_github_token_cache = None

# --- ✨ 수정된 부분: 환경변수에서 배치 시작 날짜 가져오기 ---
# BATCH_START_DATE 환경변수가 없으면 "2023-01-01"을 기본값으로 사용합니다.
BATCH_START_DATE = os.environ.get("BATCH_START_DATE", "2023-01-01")


def _get_github_token():
    """GitHub API 토큰을 캐싱하며 가져옵니다."""
    global _github_token_cache
    if _github_token_cache is None:
        name = f"projects/{config.GCP_PROJECT_ID}/secrets/{config.SECRET_ID}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        _github_token_cache = response.payload.data.decode("UTF-8")
    return _github_token_cache


# ... (get_target_repos_from_bigquery 함수는 기존과 동일) ...
def get_target_repos_from_bigquery():
    """BigQuery의 'repositories' 테이블에서 분석 대상 레포 목록을 조회합니다."""
    table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.{config.TARGET_REPO_TABLE}"
    query = f"""
        SELECT REGEXP_EXTRACT(repo_name, r'/(.*)') as repo_name
        FROM `{table_id}`
        WHERE REGEXP_EXTRACT(repo_name, r'/(.*)') IS NOT NULL
    """
    logging.info(f"Fetching target repositories from BigQuery table: {table_id}")
    try:
        rows = bigquery_client.query(query).result()
        repos = [row.repo_name for row in rows]
        logging.info(f"Found {len(repos)} target repositories in BigQuery: {repos}")
        return repos
    except Exception as e:
        logging.error(f"Failed to fetch repositories from BigQuery: {e}")
        return None


# ... (get_all_org_repos_from_github 함수는 기존과 동일) ...
def get_all_org_repos_from_github():
    """조직의 모든 레포지토리 목록을 가져옵니다 (대체 옵션)."""
    logging.info(f"Fetching all repos from GitHub organization: {config.REPO_OWNER}")
    try:
        token = _get_github_token()
        headers = {"Authorization": f"token {token}"}
        url = f"https://api.github.com/orgs/{config.REPO_OWNER}/repos"
        repo_names = []
        params = {'per_page': 100}
        while url:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            repos = response.json()
            repo_names.extend([repo['name'] for repo in repos])
            url = response.links.get('next', {}).get('url')
            params = {}
        logging.info(f"Found {len(repo_names)} repositories from GitHub.")
        return repo_names
    except Exception as e:
        logging.error(f"Failed to fetch repos from organization: {e}")
        return []


# ... (_generate_monthly_time_windows 함수는 기존과 동일) ...
def _generate_monthly_time_windows(start_date_str):
    """지정된 시작일부터 현재까지 월 단위의 시간 범위를 생성합니다."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    current_date = datetime.now(timezone.utc)

    while start_date <= current_date:
        end_of_month = start_date + relativedelta(months=1) - relativedelta(seconds=1)
        yield start_date.isoformat(), end_of_month.isoformat()
        start_date += relativedelta(months=1)


# ... (_create_task 함수는 기존과 동일) ...
def _create_task(repo_name, collect_types, start_date, end_date):
    """특정 레포지토리의 '특정 기간'에 대한 데이터 수집 작업을 Cloud Tasks에 등록합니다."""
    parent = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_REGION, config.TASK_QUEUE_ID)

    payload = {
        "repo_name": repo_name,
        "collect_types": collect_types,
        "start_date": start_date,
        "end_date": end_date
    }

    auth_req = auth_requests.Request()
    oidc_token = id_token.fetch_id_token(auth_req, config.WORKER_FUNCTION_URL)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": config.WORKER_FUNCTION_URL,
            "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {oidc_token}"},
            "body": json.dumps(payload).encode()
        }
    }
    tasks_client.create_task(parent=parent, task=task)
    logging.info(f"Created task for {repo_name} from {start_date} to {end_date}")


# ... (run 함수는 기존과 동일) ...
def run(event, context):
    """Pub/Sub 메시지를 받아 '월 단위'로 분할된 데이터 수집 작업을 시작하는 메인 함수"""
    logging.info("Dispatcher function triggered.")
    logging.info(f"Using BATCH_START_DATE: {BATCH_START_DATE}")  # 환경변수 값 로깅 추가

    collect_types = ['pulls', 'issues', 'reviews']

    repos_to_process = get_target_repos_from_bigquery()
    if not repos_to_process:
        logging.warning("Falling back to fetching all repos from GitHub org.")
        repos_to_process = get_all_org_repos_from_github()

    if not repos_to_process:
        logging.error("No repositories to process. Exiting.")
        return "No repositories found.", 200

    time_windows = list(_generate_monthly_time_windows(BATCH_START_DATE))
    logging.info(f"Generated {len(time_windows)} monthly tasks per repository.")

    total_task_count = 0
    for repo_name in repos_to_process:
        for start_date, end_date in time_windows:
            try:
                _create_task(repo_name, collect_types, start_date, end_date)
                total_task_count += 1
            except Exception as e:
                logging.error(f"Failed to create task for {repo_name} ({start_date}): {e}")

    logging.info(f"All dispatch tasks completed. Created a total of {total_task_count} tasks.")
    return "OK", 200