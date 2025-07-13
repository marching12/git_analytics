import os


GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# GitHub Webhook 설정 시 입력한 Secret을 저장한 Secret Manager의 ID
WEBHOOK_SECRET_ID = os.getenv("WEBHOOK_SECRET_ID")

REQUIRED_VARS = [GCP_PROJECT_ID, GCS_BUCKET_NAME, WEBHOOK_SECRET_ID]
if not all(REQUIRED_VARS):
    raise ValueError("Webhook 핸들러에 필요한 환경 변수 중 일부가 없습니다.")