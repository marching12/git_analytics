import json
import logging
from datetime import datetime

import config
from github_client import GitHubAPIClient
from data_models import PullRequest, Review, Issue
from google.cloud import storage, secretmanager, bigquery

# --- 로깅 설정 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

_github_token_cache = None
_label_team_map_cache = None


# --- 헬퍼 함수들 ---
def _get_github_token():
    """GitHub API 토큰을 캐싱하며 가져옵니다."""
    global _github_token_cache
    if _github_token_cache is None:
        name = f"projects/{config.GCP_PROJECT_ID}/secrets/{config.SECRET_ID}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        _github_token_cache = response.payload.data.decode("UTF-8")
    return _github_token_cache


def _get_label_team_map():
    """BigQuery에서 레이블-팀 매핑 정보를 가져와 캐싱합니다."""
    global _label_team_map_cache
    if _label_team_map_cache is not None:
        return _label_team_map_cache

    logging.info(f"Fetching label-team map from BigQuery table: {config.LABEL_MAPPING_TABLE_ID}")
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


def _upload_to_gcs(blob_name, data_list):
    """Pydantic 모델 리스트를 JSONL 형식으로 GCS 버킷에 업로드합니다."""
    if not data_list:
        return
    bucket = storage_client.bucket(config.GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)
    # 각 Pydantic 모델을 JSON 문자열로 변환하고, 줄바꿈으로 연결 (JSONL)
    jsonl_data = "\n".join([model.model_dump_json() for model in data_list])
    blob.upload_from_string(jsonl_data, content_type='application/jsonl+json')
    logging.info(f"Uploaded {len(data_list)} records to {blob_name}.")


# --- 핵심 처리 로직 ---
def process_repo_data(repo_name, collect_types):
    """Worker의 핵심 로직: 데이터를 스트리밍 방식으로 처리하여 메모리를 최적화합니다."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"Processor started for {repo_name} at {timestamp}")

    try:
        token = _get_github_token()
        client = GitHubAPIClient(token)
        label_map = _get_label_team_map()
    except Exception as e:
        logging.error(f"Initialization failed for {repo_name}: {e}")
        return False

    # PR 및 리뷰 처리
    if 'pulls' in collect_types or 'reviews' in collect_types:
        try:
            pr_summaries = client.get_pull_requests(config.REPO_OWNER, repo_name)
            logging.info(f"Found {len(pr_summaries)} PRs in {repo_name}. Processing one by one...")

            for pr_summary in pr_summaries:
                try:
                    pr_detail_json = client.get_pr_detail(pr_summary['url'])
                    team_id = get_team_id_from_labels(pr_detail_json.get('labels', []), label_map)

                    pr_model = PullRequest(
                        pr_id=pr_detail_json['id'], repo_id=pr_detail_json['head']['repo']['id'],
                        team_id=team_id, pr_number=pr_detail_json['number'], title=pr_detail_json['title'],
                        state=pr_detail_json['state'], author_id=pr_detail_json.get('user', {}).get('id'),
                        created_at=pr_detail_json['created_at'], updated_at=pr_detail_json['updated_at'],
                        merged_at=pr_detail_json['merged_at'], closed_at=pr_detail_json['closed_at'],
                        additions=pr_detail_json['additions'], deletions=pr_detail_json['deletions'],
                        commit_count=pr_detail_json['commits'],
                    )
                    _upload_to_gcs(f"pull_requests/{repo_name}_pr_{pr_model.pr_id}.jsonl", [pr_model])

                    if 'reviews' in collect_types:
                        reviews_json = client.get_reviews_for_pr(pr_summary['url'])
                        collected_reviews = [
                            Review(
                                review_id=review['id'], pr_id=pr_detail_json['id'],
                                reviewer_id=review.get('user', {}).get('id'),
                                state=review['state'], submitted_at=review['submitted_at'],
                            ) for review in reviews_json
                        ]
                        _upload_to_gcs(f"reviews/{repo_name}_pr_{pr_model.pr_id}_reviews.jsonl", collected_reviews)

                except Exception as e:
                    logging.error(f"Error processing PR #{pr_summary.get('number', 'N/A')}: {e}")

        except Exception as e:
            logging.error(f"Failed to fetch PR list for {repo_name}: {e}")

    # 이슈 처리
    if 'issues' in collect_types:
        try:
            issues_json = client.get_issues(config.REPO_OWNER, repo_name)
            logging.info(f"Found {len(issues_json)} total issues/PRs in {repo_name}. Processing one by one...")

            for issue_json in issues_json:
                if 'pull_request' in issue_json: continue
                try:
                    issue_model = Issue(
                        issue_id=issue_json['id'], repo_id=issue_json.get('repository', {}).get('id'),
                        issue_number=issue_json['number'], title=issue_json['title'],
                        state=issue_json['state'], author_id=issue_json.get('user', {}).get('id'),
                        created_at=issue_json['created_at'], updated_at=issue_json['updated_at'],
                        closed_at=issue_json['closed_at'],
                    )
                    _upload_to_gcs(f"issues/{repo_name}_issue_{issue_model.issue_id}.jsonl", [issue_model])
                except Exception as e:
                    logging.error(f"Error processing Issue #{issue_json.get('number', 'N/A')}: {e}")

        except Exception as e:
            logging.error(f"Failed to fetch issue list for {repo_name}: {e}")

    logging.info(f"Processor finished successfully for {repo_name}")
    return True