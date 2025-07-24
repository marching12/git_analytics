# function_7_validator/main.py

import os
import re
import json
from datetime import datetime
import functions_framework
from google.cloud import storage, bigquery
from google.api_core.exceptions import GoogleAPICallError

# 클라이언트 초기화
storage_client = storage.Client()
bigquery_client = bigquery.Client()

# 검증할 데이터 타입과 관련 정보 매핑
# 형식: {GCS 폴더 이름: (BigQuery 테이블 이름, 고유 키, 파일 이름에서 ID 추출용 정규식)}
VALIDATION_CONFIG = {
    "pull_requests": ("pull_requests", "pr_id", r"pr_(\d+)_"),
    "reviews": ("reviews", "review_id", r"review_(\d+)_"),
    "issues": ("issues", "issue_id", r"issue_(\d+)_"),
}

@functions_framework.http
def validate_data_consistency(request):
    """
    GCS 버킷의 파일 목록과 BigQuery 테이블 데이터를 비교하여,
    누락된 데이터가 있는지 검증하고 결과를 리포트합니다.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    dataset_id = os.environ.get("BIGQUERY_DATASET_ID")
    gcs_bucket_name = os.environ.get("GCS_BUCKET_NAME")
    report_table_id = f"{project_id}.{dataset_id}.data_validation_reports"


    if not all([project_id, dataset_id, gcs_bucket_name]):
        error_msg = "오류: GCP_PROJECT_ID, BIGQUERY_DATASET_ID, GCS_BUCKET_NAME 환경 변수가 필요합니다."
        print(error_msg)
        return error_msg, 500

    all_results = []

    # 설정된 모든 데이터 타입에 대해 순차적으로 검증 실행
    for gcs_prefix, (table_name, unique_key, id_pattern) in VALIDATION_CONFIG.items():
        print(f"--- [{table_name}] 데이터 검증 시작 ---")

        try:
            # 1. GCS에서 파일 이름에 포함된 ID 목록 추출
            gcs_ids = set()
            blobs = storage_client.list_blobs(gcs_bucket_name, prefix=f"{gcs_prefix}/")
            for blob in blobs:
                match = re.search(id_pattern, os.path.basename(blob.name))
                if match:
                    gcs_ids.add(int(match.group(1)))
            
            if not gcs_ids:
                print(f"[{table_name}] GCS에서 처리할 파일을 찾을 수 없습니다.")
                continue

            # 2. BigQuery 메인 테이블에서 ID 목록 조회
            bq_query = f"SELECT DISTINCT {unique_key} FROM `{project_id}.{dataset_id}.{table_name}`"
            query_job = bigquery_client.query(bq_query)
            bq_ids = {row[unique_key] for row in query_job.result()}

            # 3. 데이터 비교 및 누락된 ID 찾기
            missing_ids = gcs_ids - bq_ids
            
            result = {
                "table": table_name,
                "gcs_count": len(gcs_ids),
                "bq_count": len(bq_ids),
                "missing_count": len(missing_ids),
                "missing_ids_sample": sorted(list(missing_ids))[:100] # 샘플로 100개만 저장
            }
            all_results.append(result)
            
            print(f"[{table_name}] GCS 파일 ID: {len(gcs_ids)}개, BigQuery 레코드 ID: {len(bq_ids)}개")
            if missing_ids:
                print(f"[{table_name}] 누락된 ID 발견: {len(missing_ids)}개. 샘플: {result['missing_ids_sample']}")
            else:
                print(f"[{table_name}] 데이터 정합성 확인 완료. 누락된 데이터 없음.")

        except Exception as e:
            error_msg = f"[{table_name}] 검증 중 오류 발생: {e}"
            print(error_msg)
            all_results.append({"table": table_name, "error": error_msg})

    # 4. 검증 결과를 별도의 BigQuery 테이블에 저장
    _save_report_to_bigquery(report_table_id, all_results)

    return f"전체 데이터 검증 완료. 상세 내용은 로그 또는 {report_table_id} 테이블을 확인하세요.", 200


def _save_report_to_bigquery(report_table_id, results):
    """검증 결과를 BigQuery의 리포트 테이블에 저장합니다."""
    rows_to_insert = []
    for res in results:
        if "error" not in res:
            rows_to_insert.append({
                "validated_at": datetime.utcnow().isoformat(),
                "table_name": res["table"],
                "gcs_file_count": res["gcs_count"],
                "bigquery_record_count": res["bq_count"],
                "missing_record_count": res["missing_count"],
                "missing_ids_sample": json.dumps(res["missing_ids_sample"])
            })

    if not rows_to_insert:
        print("BigQuery에 저장할 검증 결과가 없습니다.")
        return

    try:
        # 참고: 리포트 테이블이 없다면 아래 스키마로 미리 생성해야 합니다.
        # schema = [
        #     bigquery.SchemaField("validated_at", "TIMESTAMP", "REQUIRED"),
        #     bigquery.SchemaField("table_name", "STRING", "REQUIRED"),
        #     bigquery.SchemaField("gcs_file_count", "INT64", "REQUIRED"),
        #     bigquery.SchemaField("bigquery_record_count", "INT64", "REQUIRED"),
        #     bigquery.SchemaField("missing_record_count", "INT64", "REQUIRED"),
        #     bigquery.SchemaField("missing_ids_sample", "STRING", "NULLABLE"),
        # ]
        
        errors = bigquery_client.insert_rows_json(report_table_id, rows_to_insert)
        if not errors:
            print(f"{len(rows_to_insert)}개의 검증 결과를 {report_table_id} 테이블에 저장했습니다.")
        else:
            print(f"리포트 저장 실패: {errors}")
    except Exception as e:
        print(f"리포트 테이블 저장 중 오류 발생: {e}")
