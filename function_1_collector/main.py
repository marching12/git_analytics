import base64
import json
import logging

import config  # 우리가 만든 config 모듈
import requests
from google.cloud import tasks_v2, secretmanager
from google.oauth2 import id_token
from google.auth.transport import requests as auth_requests

# --- 로깅 설정 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
tasks_client = tasks_v2.CloudTasksClient()
secret_client = secretmanager.SecretManagerServiceClient()


def _get_github_token():
    """Secret Manager에서 GitHub 토큰을 안전하게 가져옵니다."""
    try:
        name = f"projects/{config.GCP_PROJECT_ID}/secrets/{config.SECRET_ID}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to access secret: {e}")
        raise


def _get_all_repo_names(token):
    """GitHub API를 통해 조직의 모든 레포지토리 이름을 가져옵니다."""
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

    logging.info(f"Found {len(repo_names)} repositories for organization {config.REPO_OWNER}.")
    return repo_names


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
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {oidc_token}"
            },
            "body": json.dumps(payload).encode()
        }
    }

    tasks_client.create_task(parent=parent, task=task)
    logging.info(f"Successfully created task for repository: {repo_name}")


def run(event, context):
    """Pub/Sub 메시지를 받아 파이프라인을 시작하는 메인 함수"""
    logging.info("Dispatcher function triggered.")

    try:
        if 'data' in event:
            message_data = base64.b64decode(event['data']).decode('utf-8')
            message_json = json.loads(message_data)
            collect_types = message_json.get('collect_types', ['pulls', 'issues', 'reviews'])
        else:
            collect_types = ['pulls', 'issues', 'reviews']
    except Exception as e:
        logging.error(f"Error parsing Pub/Sub message: {e}. Using default collect_types.")
        collect_types = ['pulls', 'issues', 'reviews']

    try:
        # ✨ Secret Manager에서 토큰을 가져오도록 수정
        github_token = _get_github_token()
        repo_names = _get_all_repo_names(github_token)

        for repo_name in repo_names:
            _create_task(repo_name, collect_types)

        logging.info(f"All {len(repo_names)} tasks have been dispatched.")
        return "OK"

    except Exception as e:
        logging.error(f"Dispatcher failed: {e}")
        raise