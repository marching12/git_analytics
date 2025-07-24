import logging
from google.cloud import bigquery
import config

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# BigQuery 클라이언트 초기화
bigquery_client = bigquery.Client()


def run(event, context):
    """
    GCS에 파일이 생성되면, 해당 데이터를 BigQuery의 스테이징 테이블에 INSERT(Append)합니다.
    """
    # GCS 이벤트에서 버킷과 파일 이름 가져오기
    bucket_name = event['bucket']
    file_name = event['name']
    logging.info(f"Triggered by file: gs://{bucket_name}/{file_name}")

    try:
        # 파일 경로를 분석하여 대상 테이블 이름을 결정합니다.
        # 예: 'pull_requests/...' -> 'pull_requests_staging'
        table_name_base = file_name.split('/')[0].replace('_webhook', '')
        allowed_tables = {'pull_requests', 'issues', 'reviews'}
        if table_name_base not in allowed_tables:
            logging.warning(f"'{table_name_base}'는 처리 대상 테이블이 아니므로 건너뜁니다.")
            return 'OK'
    except IndexError:
        logging.warning(f"파일 경로 '{file_name}'의 형식이 올바르지 않아 건너뜁니다.")
        return 'OK'

    # 최종 목적지인 '스테이징 테이블'의 전체 ID를 구성합니다.
    staging_table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.{table_name_base}_staging"

    # GCS 파일의 전체 URI
    uri = f"gs://{bucket_name}/{file_name}"

    try:
        # BigQuery Load Job 설정을 정의합니다.
        job_config = bigquery.LoadJobConfig(
            # 소스 파일은 JSONL (줄바꿈으로 구분된 JSON) 형식임을 지정합니다.
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            # 데이터를 덮어쓰지 않고, 기존 데이터에 추가(Append)합니다.
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        # GCS URI로부터 스테이징 테이블로 데이터를 로드하는 작업을 시작합니다.
        load_job = bigquery_client.load_table_from_uri(uri, staging_table_id, job_config=job_config)

        logging.info(f"Staging table '{staging_table_id}'로 데이터 로드 작업을 시작합니다. (Job ID: {load_job.job_id})")

        # 작업이 완료될 때까지 기다립니다.
        load_job.result()

        logging.info(f"성공! {load_job.output_rows}개의 행을 '{staging_table_id}'에 추가했습니다.")

    except Exception as e:
        logging.error(f"'{staging_table_id}'로 데이터 로드 중 에러 발생: {e}")
        raise  # 에러를 다시 발생시켜 Cloud Functions에서 실패로 기록되게 함

    return 'OK'