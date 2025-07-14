import os
import json
import logging
import base64

import config
from libs.github_client import GitHubAPIClient
from google.cloud import tasks_v2, secretmanager, bigquery
from google.oauth2 import id_token
from google.auth.transport import requests as auth_requests

# --- 로깅 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
tasks_client = tasks_v2.CloudTasksClient()
bigquery_client = bigquery.Client()
secret_client = secretmanager.SecretManagerServiceClient()

_github_token_cache = None


# --- 헬퍼 함수 ---
def _get_github_token():
    """GitHub API 토큰을 캐싱하며 가져옵니다."""
    global _github_token_cache
    if _github_token_cache is None:
        name = f"projects/{config.GCP_PROJECT_ID}/secrets/{config.SECRET_ID}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        _github_token_cache = response.payload.data.decode("UTF-8")
    return _github_token_cache


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
        query_job = bigquery_client.query(query)
        repos = [row.repo_name for row in query_job.result()]
        logging.info(f"Found {len(repos)} target repositories in BigQuery: {repos}")
        return repos
    except Exception as e:
        logging.error(f"Failed to fetch repositories from BigQuery: {e}")
        return None


def get_all_org_repos_from_github():
    """조직의 모든 레포지토리 목록을 공용 클라이언트를 사용해 가져옵니다."""
    logging.info(f"Fetching all repos from GitHub organization via client: {config.REPO_OWNER}")
    try:
        token = _get_github_token()
        client = GitHubAPIClient(token)
        repos_json = client.get_repos(config.REPO_OWNER)
        repo_names = [repo['name'] for repo in repos_json]
        logging.info(f"Found {len(repo_names)} repositories from GitHub.")
        return repo_names
    except Exception as e:
        logging.error(f"Failed to fetch repos from organization: {e}")
        return []


def _create_task(repo_name, collect_types):
    """특정 레포지토리에 대한 데이터 수집 작업을 Cloud Tasks에 등록합니다."""
    parent = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_REGION, config.TASK_QUEUE_ID)
    payload = {"repo_name": repo_name, "collect_types": collect_types}

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
    logging.info(f"Successfully created task for repository: {repo_name}")


# --- 메인 실행 함수 ---
def run(event, context):
    """Pub/Sub 메시지를 받아 데이터 수집 작업을 시작하는 메인 함수"""
    logging.info("Dispatcher function triggered.")

    collect_types = ['pulls', 'issues', 'reviews']
    if 'data' in event:
        try:
            message_data = base64.b64decode(event['data']).decode('utf-8')
            message_json = json.loads(message_data)
            collect_types = message_json.get('collect_types', collect_types)
        except Exception as e:
            logging.warning(f"Error parsing Pub/Sub message: {e}. Using default collect_types.")

    # BigQuery에서 레포 목록을 먼저 시도
    repos_to_process = get_target_repos_from_bigquery()

    # BigQuery 조회가 실패하거나 목록이 비었을 경우, GitHub에서 전체 목록을 가져오는 대체 로직 실행
    if not repos_to_process:
        logging.warning("Could not get repo list from BigQuery. Falling back to fetching all repos from GitHub org.")
        repos_to_process = get_all_org_repos_from_github()

    if not repos_to_process:
        logging.error("No repositories to process. Exiting.")
        return "No repositories found.", 200

    for repo_name in repos_to_process:
        try:
            _create_task(repo_name, collect_types)
        except Exception as e:
            logging.error(f"Failed to create task for repo {repo_name}: {e}")

    logging.info(f"All dispatch tasks completed for {len(repos_to_process)} repos.")
    return "OK", 200