# function_9_batch_loader/main.py
import os
import functions_framework
from collections import defaultdict
from google.cloud import pubsub_v1, bigquery
from libs.data_models import get_model_info, pydantic_to_bigquery_schema
import config

# 클라이언트 초기화
subscriber_client = pubsub_v1.SubscriberClient()
bigquery_client = bigquery.Client()


@functions_framework.http
def run(request):
    """Pub/Sub 구독에서 파일 목록을 가져와 BigQuery에 일괄 로드합니다."""

    subscription_path = subscriber_client.subscription_path(config.GCP_PROJECT_ID, config.PUBSUB_SUBSCRIPTION_ID)

    # 1. Pub/Sub에서 메시지(파일 경로) 가져오기
    try:
        response = subscriber_client.pull(subscription=subscription_path, max_messages=1000)  # 한 번에 최대 1000개
    except Exception as e:
        print(f"Pub/Sub pull 실패: {e}")
        return "Failed to pull messages", 500

    if not response.received_messages:
        return "처리할 파일이 없습니다.", 200

    # 2. 파일 경로를 타입별로 그룹화하고, 메시지 Acknowledge
    file_uris_by_type = defaultdict(list)
    ack_ids = []
    for msg in response.received_messages:
        file_name = msg.message.data.decode("utf-8")
        table_type = file_name.split('/')[0]
        file_uris_by_type[table_type].append(f"gs://{config.GCS_BUCKET_NAME}/{file_name}")
        ack_ids.append(msg.ack_id)

    if ack_ids:
        subscriber_client.acknowledge(subscription=subscription_path, ack_ids=ack_ids)
        print(f"{len(ack_ids)}개의 메시지를 처리했습니다.")

    # 3. 타입별로 BigQuery에 일괄 로드
    for table_type, uris in file_uris_by_type.items():
        model_class, _ = get_model_info(table_type)
        if not model_class:
            print(f"'{table_type}'에 대한 모델 정보 없음. 건너뜁니다.")
            continue

        schema = pydantic_to_bigquery_schema(model_class)
        table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.staging_{table_type}"

        job_config = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        try:
            load_job = bigquery_client.load_table_from_uri(uris, table_id, job_config=job_config)
            load_job.result()
            print(f"'{table_type}' 타입의 파일 {len(uris)}개를 '{table_id}'에 성공적으로 로드했습니다.")
        except Exception as e:
            print(f"'{table_type}' 로드 작업 실패: {e}")

    return "배치 로드 작업 완료.", 200