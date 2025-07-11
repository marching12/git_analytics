import hmac
import hashlib
import json
import logging
import requests

import config
from data_models import PullRequest, Review, Issue
from google.cloud import storage, secretmanager, bigquery

# --- 클라이언트 및 전역 캐시 ---
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

_webhook_secret_cache = None
_github_token_cache = None
_label_team_map_cache = None


# --- 헬퍼 함수: 인증 및 설정 ---
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

    secret = _get_secret(config.WEBHOOK_SECRET_ID)
    expected_signature = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise PermissionError("Request signature does not match.")
    logging.info("Webhook signature verified successfully.")


def _get_label_team_map():
    """BigQuery에서 레이블-팀 매핑 정보를 가져와 캐싱합니다."""
    global _label_team_map_cache
    if _label_team_map_cache is not None:
        return _label_team_map_cache

    logging.info(f"Fetching label-team map from BigQuery...")
    query = f"SELECT label_name, team_id FROM `{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.{config.LABEL_MAPPING_TABLE_NAME}`"
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
    """단일 Pydantic 모델을 JSON 형태로 GCS 버킷에 업로드합니다."""
    bucket = storage_client.bucket(config.GCS_BUCKET_NAME)
    blob = bucket.blob(f"{folder_name}/{file_name}")
    blob.upload_from_string(
        pydantic_model.model_dump_json(),
        content_type='application/json'
    )
    logging.info(f"Uploaded event to {folder_name}/{file_name}.")


# --- 이벤트 핸들러 함수 ---
def _handle_pull_request(payload):
    """PR 이벤트 처리: 상세 정보를 API로 다시 조회하여 완전한 데이터를 저장합니다."""
    pr_payload = payload.get('pull_request')
    action = payload.get('action')
    if not pr_payload: return

    try:
        # 데이터 일관성을 위해 상세 API 재호출
        headers = {"Authorization": f"token {_get_github_token()}"}
        pr_detail_json = requests.get(pr_payload['url'], headers=headers).json()

        label_map = _get_label_team_map()
        team_id = get_team_id_from_labels(pr_detail_json.get('labels', []), label_map)

        pr_model = PullRequest(
            pr_id=pr_detail_json['id'],
            repo_id=pr_detail_json['head']['repo']['id'],
            team_id=team_id,
            pr_number=pr_detail_json['number'],
            title=pr_detail_json['title'],
            state=pr_detail_json['state'],
            author_id=pr_detail_json.get('user', {}).get('id'),
            created_at=pr_detail_json['created_at'], updated_at=pr_detail_json['updated_at'],
            merged_at=pr_detail_json['merged_at'], closed_at=pr_detail_json['closed_at'],
            additions=pr_detail_json['additions'], deletions=pr_detail_json['deletions'],
            commit_count=pr_detail_json['commits'],
        )
        file_name = f"pr_{pr_model.pr_id}_{action}_{datetime.utcnow().isoformat()}.json"
        _upload_to_gcs('pull_requests_webhook', file_name, pr_model)
    except Exception as e:
        logging.error(f"Error handling pull_request event: {e}")


def _handle_issues(payload):
    """이슈 이벤트 처리"""
    issue_payload = payload.get('issue')
    action = payload.get('action')
    if not issue_payload or 'pull_request' in issue_payload:
        return

    try:
        issue_model = Issue(
            issue_id=issue_payload['id'],
            repo_id=payload.get('repository', {}).get('id'),
            issue_number=issue_payload['number'],
            title=issue_payload['title'],
            state=issue_payload['state'],
            author_id=issue_payload.get('user', {}).get('id'),
            created_at=issue_payload['created_at'],
            updated_at=issue_payload['updated_at'],
            closed_at=issue_payload['closed_at'],
        )
        file_name = f"issue_{issue_model.issue_id}_{action}_{datetime.utcnow().isoformat()}.json"
        _upload_to_gcs('issues_webhook', file_name, issue_model)
    except Exception as e:
        logging.error(f"Error handling issues event: {e}")


def _handle_pull_request_review(payload):
    """리뷰 이벤트 처리"""
    review_payload = payload.get('review')
    pr_payload = payload.get('pull_request')
    action = payload.get('action')
    if not review_payload or not pr_payload: return

    try:
        review_model = Review(
            review_id=review_payload['id'],
            pr_id=pr_payload['id'],
            reviewer_id=review_payload.get('user', {}).get('id'),
            state=review_payload['state'],
            submitted_at=review_payload['submitted_at'],
        )
        file_name = f"review_{review_model.review_id}_{action}_{datetime.utcnow().isoformat()}.json"
        _upload_to_gcs('reviews_webhook', file_name, review_model)
    except Exception as e:
        logging.error(f"Error handling pull_request_review event: {e}")


# --- 메인 프로세서 ---
EVENT_HANDLERS = {
    "pull_request": _handle_pull_request,
    "issues": _handle_issues,
    "pull_request_review": _handle_pull_request_review
}


def process_webhook(headers, body):
    """웹훅 요청을 검증하고 적절한 핸들러로 라우팅합니다."""
    _verify_signature(headers, body)

    event_type = headers.get("X-GitHub-Event")
    payload = json.loads(body.decode('utf-8'))

    logging.info(f"Processing event: {event_type}, action: {payload.get('action')}")

    if event_type == 'ping':
        logging.info("Received ping event. Returning pong.")
        return ("Webhook configured successfully (pong).", 200)

    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        handler(payload)
    else:
        logging.info(f"No handler for event type: {event_type}. Skipping.")

    return ("Event processing initiated.", 202)