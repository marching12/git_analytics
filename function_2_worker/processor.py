import json
import logging

import config
from libs.github_client import GitHubAPIClient  # 공용 클라이언트 사용
from google.cloud import tasks_v2, secretmanager
from google.oauth2 import id_token
from google.auth.transport import requests as auth_requests

# --- 로깅 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
tasks_client = tasks_v2.CloudTasksClient()
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


def _create_detail_task(pr_url):
    """PR 하나를 처리하는 세부 작업을 'Detail-Collector' 큐에 등록합니다."""
    parent = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_REGION, config.DETAIL_COLLECTOR_QUEUE_ID)
    payload = {"pr_url": pr_url}

    auth_req = auth_requests.Request()
    oidc_token = id_token.fetch_id_token(auth_req, config.DETAIL_COLLECTOR_FUNCTION_URL)

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": config.DETAIL_COLLECTOR_FUNCTION_URL,
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {oidc_token}"
            },
            "body": json.dumps(payload).encode()
        }
    }
    tasks_client.create_task(parent=parent, task=task)
    logging.info(f"Successfully created detail-task for PR: {pr_url}")


# --- ✨ 수정된 핵심 처리 로직 ---
def list_and_dispatch_prs(repo_name):
    """레포지토리의 PR 목록을 페이지 단위로 처리하여 메모리 사용량을 최적화합니다."""
    logging.info(f"PR-Lister processor started for {repo_name}")

    total_dispatched_count = 0
    try:
        token = _get_github_token()
        client = GitHubAPIClient(token)

        # GitHubAPIClient의 페이지네이션 로직을 직접 활용
        url = f"{client.BASE_URL}/repos/{config.REPO_OWNER}/{repo_name}/pulls"
        params = {'state': 'all', 'per_page': 100}

        while url:
            response = client._send_request_with_retry(url, params=params)
            pr_summaries = response.json()
            logging.info(f"Processing page with {len(pr_summaries)} PRs for {repo_name}.")

            for pr_summary in pr_summaries:
                try:
                    _create_detail_task(pr_summary['url'])
                    total_dispatched_count += 1
                except Exception as e:
                    logging.error(f"Failed to create task for PR URL {pr_summary.get('url')}: {e}")

            # 다음 페이지 URL을 가져옴
            url = response.links.get('next', {}).get('url')
            params = {}  # 첫 페이지 이후에는 params가 필요 없음

        logging.info(f"Successfully dispatched a total of {total_dispatched_count} tasks for {repo_name}.")
        return True

    except Exception as e:
        logging.error(f"Failed to fan-out tasks for {repo_name}: {e}")
        return False