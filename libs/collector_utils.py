import logging
from google.cloud import storage, secretmanager, bigquery
from libs.github_client import GitHubAPIClient

# --- 클라이언트 초기화 (애플리케이션 시작 시 한 번만 수행) ---
storage_client = storage.Client()
secret_client = secretmanager.SecretManagerServiceClient()
bigquery_client = bigquery.Client()

_github_token_cache = None
_label_team_map_cache = None


def get_github_client(gcp_project_id, secret_id):
    """Secret Manager에서 GitHub 토큰을 가져와 GitHubAPIClient를 반환합니다."""
    global _github_token_cache
    if _github_token_cache is None:
        logging.info("Fetching GitHub token from Secret Manager...")
        name = f"projects/{gcp_project_id}/secrets/{secret_id}/versions/latest"
        response = secret_client.access_secret_version(request={"name": name})
        _github_token_cache = response.payload.data.decode("UTF-8")

    return GitHubAPIClient(_github_token_cache)


def get_label_team_map(table_id):
    """BigQuery에서 레이블-팀 매핑 정보를 가져와 캐싱하며 반환합니다."""
    global _label_team_map_cache
    if _label_team_map_cache is not None:
        return _label_team_map_cache

    logging.info(f"Fetching label-team map from BigQuery table: {table_id}")
    query = f"SELECT label_name, team_id FROM `{table_id}`"
    try:
        rows = bigquery_client.query(query).result()
        label_map = {row.label_name: row.team_id for row in rows}
        _label_team_map_cache = label_map
        logging.info(f"Successfully cached {len(label_map)} label mappings.")
        return _label_team_map_cache
    except Exception as e:
        logging.error(f"Failed to fetch label-team map: {e}")
        _label_team_map_cache = {}  # 실패 시 빈 맵 반환
        return _label_team_map_cache


def upload_models_to_gcs(bucket_name, blob_name, data_list):
    """Pydantic 모델 리스트를 JSONL 형식으로 GCS 버킷에 업로드합니다."""
    if not data_list:
        logging.warning(f"No data to upload for {blob_name}. Skipping.")
        return

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Pydantic v2에서는 model_dump_json()을 사용합니다.
    jsonl_data = "\n".join([model.model_dump_json() for model in data_list])

    blob.upload_from_string(jsonl_data, content_type='application/jsonl')
    logging.info(f"Uploaded {len(data_list)} records to gs://{bucket_name}/{blob_name}")