import os
import json
import logging
import uuid
# from datetime import datetime # 이제 libs/data_models에서 처리

import config
from google.cloud import bigquery

# libs/data_models에서 헬퍼 함수들을 임포트합니다.
from libs.data_models import get_model_info, pydantic_to_bigquery_schema

# --- 로깅 설정 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bigquery_client = bigquery.Client()

def run(event, context):
    """
    GCS 파일 생성을 트리거로 BigQuery에 데이터를 MERGE(Upsert)하는 함수.
    Pydantic 모델을 사용하여 스키마를 동적으로 정의합니다.
    """
    bucket_name = event['bucket']
    file_name = event['name']
    logging.info(f"Triggered by file: {file_name} in bucket: {bucket_name}")

    temp_table_id = None # finally 블록에서 사용하기 위해 초기화

    try:
        # 파일 경로에서 테이블 이름 추출
        table_name = file_name.split('/')[0]
        model_class, unique_key = get_model_info(table_name) # libs/data_models에서 가져옴

        if not model_class:
            logging.warning(f"No Pydantic model mapping found for table '{table_name}'. Skipping.")
            return 'OK'
        if not unique_key:
            logging.error(f"Unique key not defined for table '{table_name}'. Cannot perform MERGE.")
            return 'Error: Unique key missing', 500

    except IndexError:
        logging.warning(f"File {file_name} is not in a recognized subdirectory format. Skipping.")
        return 'OK'
    except Exception as e:
        logging.error(f"Error processing file name or model info: {e}")
        return 'Error processing input', 500

    # --- 1. 임시 테이블 생성 및 데이터 로드 ---
    project_id = config.GCP_PROJECT_ID
    dataset_id = config.BIGQUERY_DATASET_ID
    target_table_id = f"{project_id}.{dataset_id}.{table_name}"
    
    # 고유한 임시 테이블 이름 생성
    temp_table_name = f"temp_{table_name}_{uuid.uuid4().hex}"
    temp_table_id = f"{project_id}.{dataset_id}.{temp_table_name}"
    
    uri = f"gs://{bucket_name}/{file_name}"

    # Pydantic 모델로부터 BigQuery 스키마 생성 (libs/data_models에서 가져옴)
    bq_schema = pydantic_to_bigquery_schema(model_class)

    # BigQuery 로드 작업 구성
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=bq_schema, # 동적으로 생성된 스키마 사용
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE, # 임시 테이블은 항상 새로 씀
    )

    try:
        logging.info(f"Loading data from {uri} into temporary table {temp_table_id}")
        load_job = bigquery.Client().load_table_from_uri(
            uri, temp_table_id, job_config=job_config
        )
        load_job.result()  # 작업이 끝날 때까지 대기
        logging.info(f"Loaded {load_job.output_rows} rows into temporary table {temp_table_id}.")
    except Exception as e:
        logging.error(f"Failed to load data into temporary table {temp_table_id}. Reason: {e}")
        raise # 에러 발생 시 함수 종료

    # --- 2. MERGE 쿼리 실행 ---
    try:
        # 대상 테이블의 스키마를 동적으로 가져와 MERGE 문의 SET, VALUES 절을 구성
        column_names = [field.name for field in bq_schema]
        
        # UPDATE SET 절 구성
        set_clause = ", ".join([f"T.{col} = S.{col}" for col in column_names])
        
        # INSERT VALUES 절 구성
        values_clause = ", ".join(column_names)
        source_columns = ", ".join([f"S.{col}" for col in column_names])

        merge_query = f"""
            MERGE `{target_table_id}` T
            USING `{temp_table_id}` S
            ON T.{unique_key} = S.{unique_key}
            WHEN MATCHED THEN
                UPDATE SET {set_clause}
            WHEN NOT MATCHED THEN
                INSERT ({values_clause})
                VALUES ({source_columns})
        """
        
        logging.info(f"Executing MERGE query for table {table_name}...")
        merge_job = bigquery.Client().query(merge_query)
        merge_job.result() # 작업이 끝날 때까지 대기
        logging.info(f"MERGE operation completed successfully for {table_name}. Affected rows: {merge_job.num_dml_affected_rows}")

    except Exception as e:
        logging.error(f"Failed to execute MERGE query for {table_name}. Reason: {e}")
        raise # 에러 발생 시 함수 종료
    finally:
        # --- 3. 임시 테이블 삭제 ---
        if temp_table_id:
            try:
                logging.info(f"Deleting temporary table {temp_table_id}")
                bigquery.Client().delete_table(temp_table_id, not_found_ok=True)
                logging.info(f"Temporary table {temp_table_id} deleted.")
            except Exception as e:
                logging.warning(f"Failed to delete temporary table {temp_table_id}. Reason: {e}")

    return 'OK', 200
