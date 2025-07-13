import os

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION") # Cloud Tasks는 리전 정보가 필요
REPO_OWNER = os.getenv("REPO_OWNER")
SECRET_ID = os.getenv("SECRET_ID") # GitHub 토큰을 가져오기 위해 필요

# Cloud Tasks 설정
TASK_QUEUE_ID = os.getenv("TASK_QUEUE_ID") # 작업을 보낼 큐 ID
WORKER_FUNCTION_URL = os.getenv("WORKER_FUNCTION_URL") # 호출할 Worker 함수의 URL
WORKER_SERVICE_ACCOUNT = os.getenv("WORKER_SERVICE_ACCOUNT") # Worker의 서비스 계정

REQUIRED_VARS = [
    GCP_PROJECT_ID, GCP_REGION, REPO_OWNER, SECRET_ID,
    TASK_QUEUE_ID, WORKER_FUNCTION_URL, WORKER_SERVICE_ACCOUNT
]
if not all(REQUIRED_VARS):
    raise ValueError("Dispatcher에 필요한 환경 변수 중 일부가 없습니다.")