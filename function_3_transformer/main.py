import logging
import config  # 우리가 만든 config 모듈을 임포트

from google.cloud import bigquery

# --- 로깅 설정 및 클라이언트 초기화 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bigquery_client = bigquery.Client()


def run(event, context):
    """
    GCS 파일 생성을 트리거로 BigQuery에 데이터를 로드하는 함수.
    파일 경로의 첫 번째 폴더 이름을 테이블 이름으로 사용합니다.
    """

    bucket_name = event['bucket']
    file_name = event['name']

    logging.info(f"Triggered by file: {file_name} in bucket: {bucket_name}")

    # --- 파일 경로에서 테이블 이름을 동적으로 추출 ---
    try:
        # 예: "pull_requests/KOIN_ANDROID_20250712.jsonl" -> "pull_requests"
        table_name = file_name.split('/')[0]

        # 처리할 대상 폴더 목록 (원치 않는 파일이 로드되는 것을 방지)
        allowed_tables = ['pull_requests', 'issues', 'reviews']
        if table_name not in allowed_tables:
            logging.warning(f"File path '{file_name}' is not in an allowed directory. Skipping.")
            return 'OK'

    except IndexError:
        logging.warning(f"File {file_name} is not in a subdirectory. Skipping.")
        return 'OK'

    table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.{table_name}"
    uri = f"gs://{bucket_name}/{file_name}"

    logging.info(f"Attempting to load data from {uri} into {table_id}")

    # BigQuery 로드 작업 구성
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        # 테이블 스키마는 이미 정의되어 있으므로, 자동 감지를 사용하지 않음
        autodetect=False,
    )

    try:
        load_job = bigquery_client.load_table_from_uri(
            uri, table_id, job_config=job_config
        )
        load_job.result()  # 작업이 끝날 때까지 대기

        destination_table = bigquery_client.get_table(table_id)
        logging.info(f"Loaded {load_job.output_rows} rows into {table_id}. Total rows: {destination_table.num_rows}")

    except Exception as e:
        logging.error(f"Failed to load data from {uri} to {table_id}. Reason: {e}")
        # 실패 시 에러를 다시 발생시켜 Cloud Functions 로그에 실패로 기록
        raise

    return 'OK'