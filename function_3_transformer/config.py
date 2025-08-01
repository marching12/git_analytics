import os

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
# PUBSUB_TOPIC_ID는 새로 만들 'files-to-load' 토픽을 가리킵니다.
PUBSUB_TOPIC_ID = os.getenv("PUBSUB_TOPIC_ID")

REQUIRED_VARS = [GCP_PROJECT_ID, PUBSUB_TOPIC_ID]
if not all(REQUIRED_VARS):
    raise ValueError("필수 환경 변수 GCP_PROJECT_ID 또는 PUBSUB_TOPIC_ID가 없습니다.")