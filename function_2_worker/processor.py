import json
import logging
from datetime import datetime
from google.cloud import storage, secretmanager, bigquery

# 다른 모듈에서 설정과 클래스를 가져옵니다.
import config
from github_client import GitHubAPIClient
from data_models import PullRequest, Review, Issue

# GCP 클라이언트 초기화
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()
_label_team_map_cache = None


def _get_github_token():
    """Secret Manager에서 GitHub 토큰을 안전하게 가져옵니다."""
    try:
        name = f"projects/{config.GCP_PROJECT_ID}/secrets/{config.SECRET_ID}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logging.error(f"Failed to access secret: {e}")
        raise


def _upload_to_gcs(blob_name, data_list):
    """Pydantic 모델 리스트를 JSONL 형식으로 GCS 버킷에 업로드합니다."""
    if not data_list:
        logging.warning(f"No data to upload for {blob_name}. Skipping.")
        return

    bucket = storage_client.bucket(config.GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)

    # 각 Pydantic 모델을 JSON 문자열로 변환하고, 줄바꿈으로 연결 (JSONL)
    jsonl_data = "\n".join([model.model_dump_json() for model in data_list])

    blob.upload_from_string(
        jsonl_data,
        content_type='application/jsonl+json'
    )
    logging.info(f"Successfully uploaded {len(data_list)} records to {blob_name}.")


def _get_label_team_map():
    """BigQuery에서 레이블-팀 매핑 정보를 가져와 캐싱합니다."""
    global _label_team_map_cache
    if _label_team_map_cache is not None:
        return _label_team_map_cache

    logging.info(f"Fetching label-team map from BigQuery table: {config.LABEL_MAPPING_TABLE_ID}")
    query = f"SELECT label_name, team_id FROM `{config.LABEL_MAPPING_TABLE_ID}`"
    try:
        query_job = bigquery_client.query(query)
        rows = query_job.result()
        label_map = {row.label_name: row.team_id for row in rows}
        _label_team_map_cache = label_map
        logging.info(f"Successfully cached {len(label_map)} label mappings.")
        return _label_team_map_cache
    except Exception as e:
        logging.error(f"Failed to fetch or build label-team map: {e}")
        _label_team_map_cache = {}
        return _label_team_map_cache


def get_team_id_from_labels(labels, label_map):
    """레이블 목록과 매핑 정보를 기반으로 팀 ID를 결정합니다."""
    for label in labels:
        if label.get('name') in label_map:
            return label_map[label['name']]
    return config.COMMON_TEAM_ID


def process_repo_data(repo_name, collect_types, timestamp):
    """Worker의 핵심 로직: 데이터를 수집, 변환, 저장합니다."""

    try:
        token = _get_github_token()
        client = GitHubAPIClient(token)
        label_map = _get_label_team_map()
    except Exception as e:
        logging.error(f"Initialization failed: {e}")
        return

    # PR 및 리뷰 처리
    if 'pulls' in collect_types or 'reviews' in collect_types:
        try:
            pr_summaries = client.get_pull_requests(config.REPO_OWNER, repo_name)
            logging.info(f"Found {len(pr_summaries)} PRs in {repo_name}.")

            collected_prs = []
            collected_reviews = []

            for pr_summary in pr_summaries:
                pr_detail_json = client.get_pr_detail(pr_summary['url'])

                team_id = get_team_id_from_labels(pr_detail_json.get('labels', []), label_map)
                pr_data = {
                    'pr_id': pr_detail_json['id'],
                    'repo_id': pr_detail_json['head']['repo']['id'],
                    'team_id': team_id,
                    'pr_number': pr_detail_json['number'],
                    'title': pr_detail_json['title'],
                    'state': pr_detail_json['state'],
                    'author_id': pr_detail_json.get('user', {}).get('id'),
                    'created_at': pr_detail_json['created_at'],
                    'updated_at': pr_detail_json['updated_at'],
                    'merged_at': pr_detail_json['merged_at'],
                    'closed_at': pr_detail_json['closed_at'],
                    'additions': pr_detail_json['additions'],
                    'deletions': pr_detail_json['deletions'],
                    'commit_count': pr_detail_json['commits'],
                }
                collected_prs.append(PullRequest(**pr_data))

                if 'reviews' in collect_types:
                    reviews_json = client.get_reviews(f"{pr_detail_json['url']}/reviews")
                    for review_json in reviews_json:
                        review_data = {
                            'review_id': review_json['id'],
                            'pr_id': pr_detail_json['id'],
                            'reviewer_id': review_json.get('user', {}).get('id'),
                            'state': review_json['state'],
                            'submitted_at': review_json['submitted_at'],
                        }
                        collected_reviews.append(Review(**review_data))

            _upload_to_gcs(f"pull_requests/{repo_name}_{timestamp}.jsonl", collected_prs)
            _upload_to_gcs(f"reviews/{repo_name}_{timestamp}.jsonl", collected_reviews)

        except Exception as e:
            logging.error(f"Error processing PRs/reviews for {repo_name}: {e}")

    # 이슈 처리
    if 'issues' in collect_types:
        try:
            issues_json = client.get_issues(config.REPO_OWNER, repo_name)
            logging.info(f"Found {len(issues_json)} total issues/PRs in {repo_name}.")

            collected_issues = []
            for issue_json in issues_json:
                if 'pull_request' in issue_json:
                    continue  # PR은 이슈 목록에서 제외

                issue_data = {
                    'issue_id': issue_json['id'],
                    'repo_id': issue_json.get('repository', {}).get('id'),
                    'issue_number': issue_json['number'],
                    'title': issue_json['title'],
                    'state': issue_json['state'],
                    'author_id': issue_json.get('user', {}).get('id'),
                    'created_at': issue_json['created_at'],
                    'updated_at': issue_json['updated_at'],
                    'closed_at': issue_json['closed_at'],
                }
                collected_issues.append(Issue(**issue_data))

            logging.info(f"Filtered to {len(collected_issues)} pure issues.")
            _upload_to_gcs(f"issues/{repo_name}_{timestamp}.jsonl", collected_issues)

        except Exception as e:
            logging.error(f"Error processing issues for {repo_name}: {e}")