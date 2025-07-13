import os

# GCP 환경에서는 .env가 없으므로 load_dotenv를 사용하지 않습니다.
# 로컬 테스트 시에는 .env 파일이 자동으로 로드됩니다.

# --- 환경 변수 로드 및 검증 ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION")
TASK_QUEUE_ID = os.getenv("TASK_QUEUE_ID")
WORKER_FUNCTION_URL = os.getenv("WORKER_FUNCTION_URL")
WORKER_SERVICE_ACCOUNT = os.getenv("WORKER_SERVICE_ACCOUNT")
REPO_OWNER = os.getenv("REPO_OWNER")
# BigQuery에서 레포 목록을 가져오지 못했을 때를 대비한 대체 옵션용
SECRET_ID = os.getenv("SECRET_ID")

# BigQuery 테이블 정보
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
TARGET_REPO_TABLE = os.getenv("TARGET_REPO_TABLE") # 예: "repositories"

# 필수 변수 검증
REQUIRED_VARS = [
    GCP_PROJECT_ID, GCP_REGION, TASK_QUEUE_ID, WORKER_FUNCTION_URL,
    WORKER_SERVICE_ACCOUNT, REPO_OWNER, BIGQUERY_DATASET_ID, TARGET_REPO_TABLE
]
if not all(REQUIRED_VARS):
    raise ValueError("필수 환경 변수 중 일부가 설정되지 않았습니다.")