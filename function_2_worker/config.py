import os

# --- 환경 변수 로드 ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION")
REPO_OWNER = os.getenv("REPO_OWNER")
SECRET_ID = os.getenv("SECRET_ID") # GitHub 토큰이 저장된 Secret
WORKER_SERVICE_ACCOUNT = os.getenv("WORKER_SERVICE_ACCOUNT") # 이 함수의 서비스 계정

# ↓↓↓ Detail-Collector 호출을 위한 새로운 환경 변수 ↓↓↓
DETAIL_COLLECTOR_QUEUE_ID = os.getenv("DETAIL_COLLECTOR_QUEUE_ID")
DETAIL_COLLECTOR_FUNCTION_URL = os.getenv("DETAIL_COLLECTOR_FUNCTION_URL")

# 필수 변수 검증
REQUIRED_VARS = [
    GCP_PROJECT_ID, GCP_REGION, REPO_OWNER, SECRET_ID,
    WORKER_SERVICE_ACCOUNT, DETAIL_COLLECTOR_QUEUE_ID, DETAIL_COLLECTOR_FUNCTION_URL
]
if not all(REQUIRED_VARS):
    raise ValueError("PR-Lister(Worker)에 필요한 환경 변수 중 일부가 없습니다.")