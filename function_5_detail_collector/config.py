import os

# from dotenv import load_dotenv # GCP 환경에서는 이 줄을 삭제하거나 주석 처리
# load_dotenv()

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REPO_OWNER = os.getenv("REPO_OWNER")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
SECRET_ID = os.getenv("SECRET_ID")
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
LABEL_MAPPING_TABLE_NAME = os.getenv("LABEL_MAPPING_TABLE_NAME")
# ↓↓↓ 이 변수는 코드에서 계속 사용하지만, 필수 시작 조건에서는 제외합니다.
WORKER_FUNCTION_URL = os.getenv("WORKER_FUNCTION_URL")
COMMON_TEAM_ID = int(os.getenv("COMMON_TEAM_ID", 4))

# ↓↓↓ WORKER_FUNCTION_URL을 이 목록에서 제외해야 시작 오류가 발생하지 않습니다.
REQUIRED_VARS = [
    GCP_PROJECT_ID, REPO_OWNER, GCS_BUCKET_NAME, SECRET_ID,
    BIGQUERY_DATASET_ID, LABEL_MAPPING_TABLE_NAME
]
if not all(REQUIRED_VARS):
    raise ValueError("필수 환경 변수 중 일부가 없습니다.")

LABEL_MAPPING_TABLE_ID = f"{GCP_PROJECT_ID}.{BIGQUERY_DATASET_ID}.{LABEL_MAPPING_TABLE_NAME}"