import json
import logging

import config
from libs.github_client import GitHubAPIClient
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


def _create_pr_task(pr_url):
    """PR 하나를 처리하는 세부 작업을 'Detail-Collector' 큐에 등록합니다."""
    parent = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_REGION, config.DETAIL_COLLECTOR_QUEUE_ID)
    payload = {"pr_url": pr_url}
    auth_req = auth_requests.Request()
    oidc_token = id_token.fetch_id_token(auth_req, config.DETAIL_COLLECTOR_FUNCTION_URL)
    task = {"http_request": {"http_method": tasks_v2.HttpMethod.POST, "url": config.DETAIL_COLLECTOR_FUNCTION_URL,
                             "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {oidc_token}"},
                             "body": json.dumps(payload).encode()}}
    tasks_client.create_task(parent=parent, task=task)
    logging.info(f"Successfully created PR task for: {pr_url}")


# --- 추가된 부분: 이슈 작업을 생성하는 헬퍼 함수 ---
def _create_issue_task(issue_url):
    """이슈 하나를 처리하는 세부 작업을 'Issue-Collector' 큐에 등록합니다."""
    parent = tasks_client.queue_path(config.GCP_PROJECT_ID, config.GCP_REGION, config.ISSUE_COLLECTOR_QUEUE_ID)
    payload = {"issue_url": issue_url}
    auth_req = auth_requests.Request()
    oidc_token = id_token.fetch_id_token(auth_req, config.ISSUE_COLLECTOR_FUNCTION_URL)
    task = {"http_request": {"http_method": tasks_v2.HttpMethod.POST, "url": config.ISSUE_COLLECTOR_FUNCTION_URL,
                             "headers": {"Content-Type": "application/json", "Authorization": f"Bearer {oidc_token}"},
                             "body": json.dumps(payload).encode()}}
    tasks_client.create_task(parent=parent, task=task)
    logging.info(f"Successfully created Issue task for: {issue_url}")


# --- ✨ 수정된 부분: 함수 이름 변경 및 client 인자 추가 ---
def list_and_dispatch_prs(repo_name, client: GitHubAPIClient):
    """레포지토리의 PR 목록을 가져와 Task를 생성합니다."""
    total_dispatched_count = 0
    url = f"{client.BASE_URL}/repos/{config.REPO_OWNER}/{repo_name}/pulls"
    params = {'state': 'all', 'per_page': 100}
    while url:
        response = client._send_request_with_retry(url, params=params)
        pr_summaries = response.json()
        logging.info(f"Processing page with {len(pr_summaries)} PRs for {repo_name}.")
        for pr_summary in pr_summaries:
            try:
                _create_pr_task(pr_summary['url'])
                total_dispatched_count += 1
            except Exception as e:
                logging.error(f"Failed to create task for PR URL {pr_summary.get('url')}: {e}")
        url = response.links.get('next', {}).get('url')
        params = {}
    logging.info(f"Successfully dispatched a total of {total_dispatched_count} PR tasks for {repo_name}.")


# --- 추가된 부분: 이슈 목록을 가져와 Task를 생성하는 함수 ---
def list_and_dispatch_issues(repo_name, client: GitHubAPIClient):
    """레포지토리의 이슈 목록을 가져와 Task를 생성합니다."""
    total_dispatched_count = 0
    url = f"{client.BASE_URL}/repos/{config.REPO_OWNER}/{repo_name}/issues"
    params = {'state': 'all', 'per_page': 100}
    while url:
        response = client._send_request_with_retry(url, params=params)
        issues = response.json()
        logging.info(f"Processing page with {len(issues)} issues for {repo_name}.")
        for issue in issues:
            if 'pull_request' in issue:  # PR은 이슈 API에서도 조회되므로 제외
                continue
            try:
                _create_issue_task(issue['url'])
                total_dispatched_count += 1
            except Exception as e:
                logging.error(f"Failed to create task for Issue URL {issue.get('url')}: {e}")
        url = response.links.get('next', {}).get('url')
        params = {}
    logging.info(f"Successfully dispatched a total of {total_dispatched_count} Issue tasks for {repo_name}.")


# --- ✨ 수정된 부분: 전체 작업을 지휘하는 메인 함수 ---
def process_repository(repo_name):
    """레포지토리의 PR과 이슈를 모두 처리합니다."""
    logging.info(f"Worker processor started for {repo_name}")
    try:
        token = _get_github_token()
        client = GitHubAPIClient(token)

        # 1. PR 처리
        list_and_dispatch_prs(repo_name, client)

        # 2. 이슈 처리
        list_and_dispatch_issues(repo_name, client)

        return True

    except Exception as e:
        logging.error(f"Major failure in processing repository {repo_name}: {e}")
        return False