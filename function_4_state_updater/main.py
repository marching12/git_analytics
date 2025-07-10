import os
from datetime import datetime, timezone, timedelta
from google.cloud import storage, bigquery


def run(event, context):
    """
    마지막 실행 시간을 기록하고, GCS 결과를 바탕으로 최종 요약 로그를 출력합니다.
    모든 초기화 로직을 함수 내부로 이동하여 시작 오류를 방지합니다.
    """
    print("=== 파이프라인 상태 업데이트 및 결과 요약 시작 ===")

    # --- 1. 함수 실행 시점에 초기화 및 설정값 로드 ---
    # 이렇게 하면 초기화 오류 발생 시 로그에 명확한 기록이 남습니다.
    try:
        storage_client = storage.Client()
        bigquery_client = bigquery.Client()

        GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
        GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
        REPO_OWNER = os.getenv("REPO_OWNER")

        # 필수 환경변수가 없는 경우 에러 발생
        if not all([GCP_PROJECT_ID, GCS_BUCKET_NAME, REPO_OWNER]):
            raise ValueError("하나 이상의 필수 환경 변수가 설정되지 않았습니다.")

        CONTROL_DATASET = "github_analytics"
        TARGET_REPO_TABLE = "target_repositories"
        CONTROL_TABLE = "pipeline_control"
        PIPELINE_NAME = "github_collector"

    except Exception as e:
        print(f"[치명적 에러] 함수 초기화 중 문제 발생: {e}")
        raise e

    # --- 2. 메인 로직 실행 ---
    try:
        run_time = datetime.now(timezone.utc)

        # BigQuery에서 수집 대상 저장소 총 개수 가져오기
        target_table_ref = f"`{GCP_PROJECT_ID}.{CONTROL_DATASET}.{TARGET_REPO_TABLE}`"
        total_query = f"SELECT count(repo_name) as total_count FROM {target_table_ref}"
        total_repos = list(bigquery_client.query(total_query).result())[0].total_count

        # GCS에서 성공적으로 수집된 저장소 개수 세기
        prefix = f"raw/{REPO_OWNER}/"
        # 스케줄러가 새벽에 도므로, 약 하루 전 데이터를 기준으로 검색
        date_to_check = (run_time - timedelta(hours=12)).strftime('%Y-%m-%d')

        blobs = storage_client.list_blobs(GCS_BUCKET_NAME, prefix=prefix)
        successful_repos = set()
        for blob in blobs:
            if f"/{date_to_check}/" in blob.name:
                try:
                    repo_name = blob.name.split('/')[2]
                    successful_repos.add(repo_name)
                except IndexError:
                    continue

        # 최종 결과 로그 출력
        print("--- 파이프라인 최종 결과 요약 ---")
        print(f"총 대상 저장소: {total_repos}개")
        print(f"성공적으로 수집된 저장소: {len(successful_repos)}개")
        print(f"실패 또는 데이터 없음: {total_repos - len(successful_repos)}개")
        print("---------------------------------")

        # 마지막 실행 시간 업데이트
        control_table_ref = f"`{GCP_PROJECT_ID}.{CONTROL_DATASET}.{CONTROL_TABLE}`"
        update_query = f"""
            MERGE {control_table_ref} T
            USING (SELECT '{PIPELINE_NAME}' AS pipeline_name) AS S ON T.pipeline_name = S.pipeline_name
            WHEN MATCHED THEN
                UPDATE SET T.last_successful_timestamp = TIMESTAMP('{run_time.isoformat()}')
            WHEN NOT MATCHED THEN
                INSERT (pipeline_name, last_successful_timestamp) VALUES(S.pipeline_name, TIMESTAMP('{run_time.isoformat()}'))
        """
        bigquery_client.query(update_query).result()
        print(f"파이프라인 마지막 실행 시간 업데이트 완료: {run_time.isoformat()}")

    except Exception as e:
        print(f"[치명적 에러] 메인 로직 실행 중 문제 발생: {e}")
        raise e

    print("=== 파이프라인 상태 업데이트 및 결과 요약 종료 ===")