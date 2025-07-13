import os

# GCP 환경에서는 .env가 없으므로 load_dotenv를 사용하지 않습니다.
# 로컬 테스트 시에는 .env 파일이 자동으로 로드됩니다.

# --- 환경 변수 로드 및 검증 ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

# Webhook 검증용 Secret ID
WEBHOOK_SECRET_ID = os.getenv("WEBHOOK_SECRET_ID")
# GitHub API 호출용 토큰이 저장된 Secret ID
SECRET_ID = os.getenv("SECRET_ID")
REPO_OWNER = os.getenv("REPO_OWNER")

# BigQuery 조회용
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
LABEL_MAPPING_TABLE_NAME = os.getenv("LABEL_MAPPING_TABLE_NAME")
COMMON_TEAM_ID = int(os.getenv("COMMON_TEAM_ID", 4))


REQUIRED_VARS = [
    GCP_PROJECT_ID, GCS_BUCKET_NAME, WEBHOOK_SECRET_ID, SECRET_ID, REPO_OWNER,
    BIGQUERY_DATASET_ID, LABEL_MAPPING_TABLE_NAME
]
if not all(REQUIRED_VARS):
    raise ValueError("필수 환경 변수 중 일부가 설정되지 않았습니다.")

# --- BigQuery 테이블 경로 ---
LABEL_MAPPING_TABLE_ID = f"{GCP_PROJECT_ID}.{BIGQUERY_DATASET_ID}.{LABEL_MAPPING_TABLE_NAME}"