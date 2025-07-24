# function_6_merger/main.py

import os
import functions_framework
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPICallError

# 공용 라이브러리에서 모델 정보 조회 함수를 임포트
from libs.data_models import get_model_info

# BigQuery 클라이언트 초기화
client = bigquery.Client()


@functions_framework.http
def merge_data(request):
    """
    데이터셋 내의 모든 'staging_' 테이블을 동적으로 찾아,
    각각에 해당하는 메인 테이블로 데이터를 병합(MERGE)합니다.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    dataset_id = os.environ.get("BIGQUERY_DATASET_ID")

    if not all([project_id, dataset_id]):
        error_msg = "오류: GCP_PROJECT_ID, BIGQUERY_DATASET_ID 환경 변수가 모두 필요합니다."
        print(error_msg)
        return error_msg, 500

    # 1. INFORMATION_SCHEMA를 쿼리하여 병합할 staging 테이블 목록을 동적으로 조회
    schema_query = f"""
        SELECT table_name FROM `{project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES`
        WHERE table_name LIKE 'staging_%'
    """
    print(f"병합할 스테이징 테이블을 찾습니다: {schema_query}")

    try:
        query_job = client.query(schema_query)
        staging_tables = [row.table_name for row in query_job.result()]
    except GoogleAPICallError as e:
        error_msg = f"오류: INFORMATION_SCHEMA 조회 실패 - {e}"
        print(error_msg)
        return error_msg, 500

    if not staging_tables:
        msg = "처리할 스테이징 테이블이 없습니다. 작업을 종료합니다."
        print(msg)
        return msg, 200

    print(f"처리 대상 테이블: {staging_tables}")

    # 처리 결과를 저장할 리스트
    results = []

    # 2. 조회된 각 staging 테이블에 대해 MERGE 작업 순차 실행
    for staging_table_name in staging_tables:
        main_table_name = staging_table_name.replace("staging_", "", 1)

        # data_models.py 에서 모델 정보 가져오기
        model_class, unique_key = get_model_info(main_table_name)
        if not model_class or not unique_key:
            msg = f"[{main_table_name}]: 모델 정보 없음. 건너뜁니다."
            print(msg)
            results.append(msg)
            continue

        # MERGE 쿼리 동적 생성
        columns = list(model_class.__fields__.keys())
        update_setters = ", ".join([f"T.{col} = S.{col}" for col in columns if col != unique_key])
        insert_columns = ", ".join(columns)
        value_columns = ", ".join([f"S.{col}" for col in columns])

        main_table_full_id = f"{project_id}.{dataset_id}.{main_table_name}"
        staging_table_full_id = f"{project_id}.{dataset_id}.{staging_table_name}"

        merge_query = f"""
            MERGE `{main_table_full_id}` T
            USING `{staging_table_full_id}` S ON T.{unique_key} = S.{unique_key}
            WHEN MATCHED THEN UPDATE SET {update_setters}
            WHEN NOT MATCHED BY TARGET THEN INSERT ({insert_columns}) VALUES ({value_columns})
        """

        # MERGE 쿼리 실행
        try:
            merge_job = client.query(merge_query)
            merge_job.result()
            affected_rows = merge_job.num_dml_affected_rows
            msg = f"[{main_table_name}]: 성공. {affected_rows}개 행 처리."
            print(msg)
            results.append(msg)
        except Exception as e:
            msg = f"[{main_table_name}]: 실패. 오류: {e}"
            print(msg)
            results.append(msg)

    return f"전체 병합 작업 완료.\n결과:\n" + "\n".join(results), 200