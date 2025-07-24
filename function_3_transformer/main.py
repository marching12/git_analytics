import os
import functions_framework
from google.cloud import bigquery
from libs.data_models import get_model_info, pydantic_to_bigquery_schema

# BigQuery 클라이언트 초기화
client = bigquery.Client()


@functions_framework.cloud_event
def run(cloud_event):
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_name = data["name"]

    # 환경 변수에서 설정 값 가져오기
    project_id = os.environ.get("GCP_PROJECT_ID")
    dataset_id = os.environ.get("BIGQUERY_DATASET_ID")

    if not all([project_id, dataset_id]):
        print("오류: GCP_PROJECT_ID, BIGQUERY_DATASET_ID 환경 변수가 모두 필요합니다.")
        return

    print(f"GCS 버킷 '{bucket_name}'에서 '{file_name}' 파일 감지됨.")

    # 파일 이름에서 테이블 타입을 추출 (예: 'pull_requests_1234.json' -> 'pull_requests')
    try:
        table_type = file_name.split('_')[0]
    except IndexError:
        print(f"오류: 파일 이름 '{file_name}'에서 테이블 타입을 추출할 수 없습니다.")
        return

    # data_models.py를 이용해 테이블에 맞는 모델과 고유 키를 가져옴
    model_class, _ = get_model_info(table_type)
    if not model_class:
        print(f"오류: '{table_type}'에 해당하는 모델 정보를 data_models.py에서 찾을 수 없습니다.")
        return

    # Pydantic 모델을 BigQuery 스키마로 변환
    schema = pydantic_to_bigquery_schema(model_class)

    # 대상 스테이징 테이블 ID 정의
    staging_table_id = f"{project_id}.{dataset_id}.staging_{table_type}"

    # BigQuery 로드 작업 구성
    job_config = bigquery.LoadJobConfig(
        schema=schema,  # ⭐️ 스키마를 직접 지정
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,  # 데이터를 계속 추가
    )

    gcs_uri = f"gs://{bucket_name}/{file_name}"

    try:
        print(f"'{gcs_uri}'의 데이터를 '{staging_table_id}' 테이블로 로드합니다...")
        load_job = client.load_table_from_uri(
            gcs_uri,
            staging_table_id,
            job_config=job_config
        )
        load_job.result()  # 작업이 완료될 때까지 대기

        destination_table = client.get_table(staging_table_id)
        print(f"로드 작업 성공. 총 {destination_table.num_rows}개의 행이 '{staging_table_id}'에 로드되었습니다.")

    except Exception as e:
        print(f"'{staging_table_id}'로 데이터 로드 중 에러 발생: {e}")
        # 오류를 다시 발생시켜 Cloud Functions가 재시도하도록 할 수 있습니다.
        raise e