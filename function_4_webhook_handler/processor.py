import hmac
import hashlib
import json
import logging
import requests
from datetime import datetime

import config
from libs.data_models import PullRequest, Review, Issue
from libs.github_client import GitHubAPIClient
from google.cloud import storage, secretmanager, bigquery

# --- 로깅 설정 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

# --- 전역 캐시 변수 ---
_webhook_secret_cache = None
_github_token_cache = None
_label_team_map_cache = None


# --- 헬퍼 함수: 인증, 설정, GCS 업로드 ---
def _get_secret(secret_id):
    """Secret Manager에서 Secret 값을 가져옵니다."""
    name = f"projects/{config.GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data


def _get_github_token():
    """GitHub API 토큰을 캐싱하며 가져옵니다."""
    global _github_token_cache
    if _github_token_cache is None:
        _github_token_cache = _get_secret(config.SECRET_ID).decode("UTF-8")
    return _github_token_cache


def _verify_signature(headers, body):
    """GitHub Webhook의 서명을 검증합니다."""
    signature_header = headers.get("X-Hub-Signature-256")
    if not signature_header:
        raise PermissionError("X-Hub-Signature-256 header is missing.")

    global _webhook_secret_cache
    if _webhook_secret_cache is None:
        _webhook_secret_cache = _get_secret(config.WEBHOOK_SECRET_ID)

    expected_signature = "sha256=" + hmac.new(_webhook_secret_cache, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise PermissionError("Request signature does not match.")
    logging.info("Webhook signature verified successfully.")


def _get_label_team_map():
    """BigQuery에서 레이블-팀 매핑 정보를 가져와 캐싱합니다."""
    global _label_team_map_cache
    if _label_team_map_cache is not None:
        return _label_team_map_cache

    logging.info(f"Fetching label-team map from BigQuery...")
    query = f"SELECT label_name, team_id FROM `{config.LABEL_MAPPING_TABLE_ID}`"
    try:
        rows = bigquery_client.query(query).result()
        label_map = {row.label_name: row.team_id for row in rows}
        _label_team_map_cache = label_map
        logging.info(f"Successfully cached {len(label_map)} label mappings.")
        return _label_team_map_cache
    except Exception as e:
        logging.error(f"Failed to fetch label-team map: {e}")
        _label_team_map_cache = {}
        return _label_team_map_cache


def get_team_id_from_labels(labels, label_map):
    """레이블 목록을 기반으로 팀 ID를 결정합니다."""
    for label in labels:
        if label.get('name') in label_map:
            return label_map[label['name']]
    return config.COMMON_TEAM_ID


def _upload_to_gcs(folder_name, file_name, pydantic_model):
    """단일 Pydantic 모델을 JSONL 형태로 GCS 버킷에 업로드합니다."""
    bucket = storage_client.bucket(config.GCS_BUCKET_NAME)
    blob = bucket.blob(f"{folder_name}/{file_name}")
    blob.upload_from_string(
        pydantic_model.model_dump_json(),  # 단일 JSON 객체를 문자열로 변환
        content_type='application/jsonl+json'  # BigQuery Load에 유리한 JSONL 타입으로 지정
    )
    logging.info(f"Uploaded event to {folder_name}/{file_name}.")


# --- 이벤트 핸들러 함수 ---
def _handle_pull_request(payload, client: GitHubAPIClient, label_map: dict):
    """PR 이벤트 처리"""
    pr_payload = payload.get('pull_request')
    action = payload.get('action')
    if not pr_payload: return

    try:
        pr_detail_json = client.get_pr_detail(pr_payload['url'])
        team_id = get_team_id_from_labels(pr_detail_json.get('labels', []), label_map)

        pr_model = PullRequest(
            pr_id=pr_detail_json['id'], repo_id=pr_detail_json['head']['repo']['id'], team_id=team_id,
            pr_number=pr_detail_json['number'], title=pr_detail_json['title'], state=pr_detail_json['state'],
            author_id=pr_detail_json.get('user', {}).get('id'), created_at=pr_detail_json['created_at'],
            updated_at=pr_detail_json['updated_at'], merged_at=pr_detail_json['merged_at'],
            closed_at=pr_detail_json['closed_at'], additions=pr_detail_json['additions'],
            deletions=pr_detail_json['deletions'], commit_count=pr_detail_json['commits'],
        )
        file_name = f"pr_{pr_model.pr_id}_{action}_{datetime.utcnow().isoformat()}.jsonl"
        _upload_to_gcs('pull_requests_webhook', file_name, pr_model)
    except Exception as e:
        logging.error(f"Error handling pull_request event (ID: {pr_payload.get('id')}): {e}")


def _handle_issues(payload, client: GitHubAPIClient, label_map: dict):
    """이슈 이벤트 처리"""
    issue_payload = payload.get('issue')
    action = payload.get('action')
    if not issue_payload or 'pull_request' in issue_payload: return

    try:
        issue_model = Issue(
            issue_id=issue_payload['id'], repo_id=payload.get('repository', {}).get('id'),
            issue_number=issue_payload['number'], title=issue_payload['title'],
            state=issue_payload['state'], author_id=issue_payload.get('user', {}).get('id'),
            created_at=issue_payload['created_at'], updated_at=issue_payload['updated_at'],
            closed_at=issue_payload['closed_at'],
        )
        file_name = f"issue_{issue_model.issue_id}_{action}_{datetime.utcnow().isoformat()}.jsonl"
        _upload_to_gcs('issues_webhook', file_name, issue_model)
    except Exception as e:
        logging.error(f"Error handling issues event (ID: {issue_payload.get('id')}): {e}")


def _handle_pull_request_review(payload, client: GitHubAPIClient, label_map: dict):
    """리뷰 이벤트 처리"""
    review_payload = payload.get('review')
    pr_payload = payload.get('pull_request')
    action = payload.get('action')
    if not review_payload or not pr_payload: return

    try:
        review_model = Review(
            review_id=review_payload['id'], pr_id=pr_payload['id'],
            reviewer_id=review_payload.get('user', {}).get('id'),
            state=review_payload['state'], submitted_at=review_payload['submitted_at'],
        )
        file_name = f"review_{review_model.review_id}_{action}_{datetime.utcnow().isoformat()}.jsonl"
        _upload_to_gcs('reviews_webhook', file_name, review_model)
    except Exception as e:
        logging.error(f"Error handling pull_request_review event (ID: {review_payload.get('id')}): {e}")


# --- 메인 프로세서 ---
EVENT_HANDLERS = {
    "pull_request": _handle_pull_request,
    "issues": _handle_issues,
    "pull_request_review": _handle_pull_request_review,
}


def process_webhook(headers, body):
    """웹훅 요청을 검증하고, 리소스를 초기화한 뒤, 적절한 핸들러로 라우팅합니다."""
    try:
        _verify_signature(headers, body)

        event_type = headers.get("X-GitHub-Event")
        payload = json.loads(body.decode('utf-8'))

        logging.info(f"Processing event: {event_type}, action: {payload.get('action')}")

        if event_type == 'ping':
            return "Webhook configured successfully (pong).", 200

        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            api_client = GitHubAPIClient(_get_github_token())
            team_map = _get_label_team_map()
            handler(payload, api_client, team_map)
        else:
            logging.info(f"No handler for event type: {event_type}. Skipping.")

        return "Event processing initiated.", 202

    except PermissionError as e:
        logging.error(f"Permission denied during webhook processing: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred in processor: {e}")
        raise