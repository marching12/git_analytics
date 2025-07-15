import os
import logging
from google.cloud import bigquery

import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bigquery_client = bigquery.Client()


def run(event, context):
    bucket_name = event['bucket']
    file_name = event['name']
    logging.info(f"Triggered by file: {file_name} in bucket: {bucket_name}")

    temp_table_id = None
    try:
        table_name = file_name.split('/')[0].replace('_webhook', '')
        allowed_tables = {'pull_requests', 'issues', 'reviews'}
        if table_name not in allowed_tables:
            logging.warning(f"File path '{file_name}' not in allowed directory. Skipping.")
            return 'OK'
    except IndexError:
        return 'OK'

    target_table_id = f"{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET_ID}.{table_name}"
    temp_table_id = f"{target_table_id}_temp_{context.event_id.replace('-', '')}"
    uri = f"gs://{bucket_name}/{file_name}"

    try:
        # 원본 테이블의 스키마와 파티션/클러스터링 설정을 가져옵니다.
        target_table = bigquery_client.get_table(target_table_id)

        temp_table = bigquery.Table(temp_table_id, schema=target_table.schema)
        temp_table.time_partitioning = target_table.time_partitioning
        temp_table.clustering_fields = target_table.clustering_fields

        bigquery_client.create_table(temp_table, exists_ok=True)

        # 데이터를 임시 테이블에 로드합니다.
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        load_job = bigquery_client.load_table_from_uri(uri, temp_table_id, job_config=job_config)
        load_job.result()
        logging.info(f"Loaded {load_job.output_rows} rows to temp table {temp_table_id}.")

        # MERGE 쿼리를 실행합니다.
        primary_keys = {'pull_requests': 'pr_id', 'issues': 'issue_id', 'reviews': 'review_id'}
        pk_column = primary_keys.get(table_name)
        all_columns = [field.name for field in target_table.schema]
        set_clause = ", ".join([f"T.{col} = S.{col}" for col in all_columns])

        merge_sql = f"""
            MERGE `{target_table_id}` T
            USING `{temp_table_id}` S ON T.{pk_column} = S.{pk_column}
            WHEN MATCHED THEN UPDATE SET {set_clause}
            WHEN NOT MATCHED THEN INSERT ROW
        """

        merge_job = bigquery_client.query(merge_sql)
        merge_job.result()
        logging.info(f"MERGE completed for {target_table_id}.")

    except Exception as e:
        logging.error(f"Operation failed for {target_table_id}. Reason: {e}")
        raise
    finally:
        if temp_table_id:
            bigquery_client.delete_table(temp_table_id, not_found_ok=True)
            logging.info(f"Deleted temporary table {temp_table_id}.")

    return 'OK'