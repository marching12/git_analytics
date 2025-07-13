import os


# --- 환경 변수 로드 및 검증 ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REPO_OWNER = os.getenv("REPO_OWNER")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
SECRET_ID = os.getenv("SECRET_ID")
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
LABEL_MAPPING_TABLE_NAME = os.getenv("LABEL_MAPPING_TABLE_NAME")
# Dispatcher가 호출할 이 Worker 함수의 URL (Cloud Functions 배포 후 확인하여 .env에 추가)
#WORKER_FUNCTION_URL = os.getenv("WORKER_FUNCTION_URL")
COMMON_TEAM_ID = int(os.getenv("COMMON_TEAM_ID", 4))

REQUIRED_VARS = [
    GCP_PROJECT_ID, REPO_OWNER, GCS_BUCKET_NAME, SECRET_ID,
    BIGQUERY_DATASET_ID, LABEL_MAPPING_TABLE_NAME, WORKER_FUNCTION_URL
]
if not all(REQUIRED_VARS):
    raise ValueError("필수 환경 변수 중 일부가 .env 파일 또는 환경에 설정되지 않았습니다.")

# --- BigQuery 테이블 경로 ---
LABEL_MAPPING_TABLE_ID = f"{GCP_PROJECT_ID}.{BIGQUERY_DATASET_ID}.{LABEL_MAPPING_TABLE_NAME}"