import os
import json
from google.cloud import bigquery, tasks_v2

bigquery_client = bigquery.Client()
tasks_client = tasks_v2.CloudTasksClient()

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION")
TASK_QUEUE_ID = os.getenv("TASK_QUEUE_ID")
WORKER_FUNCTION_URL = os.getenv("WORKER_FUNCTION_URL")
TARGET_REPO_DATASET = "github_analytics"
TARGET_REPO_TABLE = "target_repositories"

def get_target_repo_names():
    table_ref = f"`{GCP_PROJECT_ID}.{TARGET_REPO_DATASET}.{TARGET_REPO_TABLE}`"
    query = f"SELECT repo_name FROM {table_ref}"
    repo_names = [row.repo_name for row in bigquery_client.query(query).result()]
    print(f"BigQuery에서 {len(repo_names)}개의 수집 대상 저장소를 로드했습니다.")
    return repo_names


def run(event, context):
    """
    스케줄러에 의해 실행되어, 각 저장소에 대한 수집 작업을 Cloud Tasks에 등록합니다.
    """
    print("=== 레포지토리 작업 분배 시작 ===")
    target_repos = get_target_repo_names()

    parent = tasks_client.queue_path(GCP_PROJECT_ID, GCP_REGION, TASK_QUEUE_ID)

    # ⚠️ Worker 함수가 사용하는 서비스 계정 이메일을 환경 변수에서 가져옵니다.
    worker_sa_email = os.getenv("WORKER_SERVICE_ACCOUNT")
    if not worker_sa_email:
        raise ValueError("WORKER_SERVICE_ACCOUNT 환경 변수가 설정되지 않았습니다.")

    for repo_name in target_repos:
        payload = {"repo_name": repo_name}

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": WORKER_FUNCTION_URL,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode("utf-8"),
                # [수정됨] 이 부분이 핵심입니다.
                # Cloud Tasks가 Worker 함수를 호출할 때 사용할 인증 정보(신분증)를 지정합니다.
                "oidc_token": {
                    "service_account_email": worker_sa_email,
                },
            }
        }

        try:
            response = tasks_client.create_task(parent=parent, task=task)
            print(f"'{repo_name}' 저장소에 대한 작업 생성 완료.")
        except Exception as e:
            print(f"[에러] '{repo_name}' 저장소에 대한 작업 생성 실패: {e}")

    print(f"총 {len(target_repos)}개의 작업 메시지 전송 완료.")