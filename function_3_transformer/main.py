# ==============================================================================
# Cloud Function 2: GCS 데이터 정제 및 BigQuery 적재 (배포용)
# 트리거: Google Cloud Storage (google.storage.object.finalize)
# ==============================================================================

import os
import json
from datetime import datetime
from google.cloud import storage, bigquery

# --- 클라이언트 초기화 (전역 범위) ---
# 함수가 여러 번 호출되어도 클라이언트를 한 번만 초기화하여 성능을 최적화합니다.
storage_client = storage.Client()
bigquery_client = bigquery.Client()

# --- 환경 변수에서 설정값 가져오기 ---
# 배포 시점에 설정할 값들입니다.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
DATASET_ID = os.getenv("DATASET_ID", "github_analytics")  # 기본값 설정
TABLE_ID = os.getenv("TABLE_ID", "temp_pull_requests")  # 기본값 설정


def transform_pr(pr_dict):
    """
    하나의 Pull Request 데이터(딕셔너리)를 BigQuery에 맞게 변환합니다.
    이 함수는 데이터 변환 로직만 담당하여 코드를 명확하게 합니다.
    """
    # 타임스탬프 문자열을 datetime 객체로 변환 (None일 경우 처리 포함)
    created_at_str = pr_dict.get('created_at')
    merged_at_str = pr_dict.get('merged_at')
    closed_at_str = pr_dict.get('closed_at')

    created_at = datetime.fromisoformat(created_at_str) if created_at_str else None
    merged_at = datetime.fromisoformat(merged_at_str) if merged_at_str else None
    closed_at = datetime.fromisoformat(closed_at_str) if closed_at_str else None

    # 리드 타임 계산 (병합된 경우에만 초 단위로)
    lead_time_seconds = None
    if created_at and merged_at:
        lead_time = merged_at - created_at
        lead_time_seconds = int(lead_time.total_seconds())

    # BigQuery 테이블 스키마에 맞춰 최종 행(row)을 구성합니다.
    return {
        "pr_id": pr_dict.get('id'),
        "pr_number": pr_dict.get('number'),
        "title": pr_dict.get('title'),
        "author": pr_dict.get('user', {}).get('login'),
        "state": pr_dict.get('state'),
        "created_at": created_at.isoformat() if created_at else None,
        "merged_at": merged_at.isoformat() if merged_at else None,
        "closed_at": closed_at.isoformat() if closed_at else None,
        "lead_time_seconds": lead_time_seconds,
        "repository": pr_dict.get('base', {}).get('repo', {}).get('name'),
        "merged": bool(merged_at),
    }


def run(event, context):
    """
    GCS에 파일이 생성되면 트리거되는 Cloud Function의 시작점
    """
    bucket_name = event['bucket']
    file_name = event['name']

    # 이미 처리된 폴더의 파일은 무시 (무한 루프 방지)
    if 'raw/' not in file_name:
        print(f"'{file_name}' 파일은 처리 대상이 아니므로 건너뜁니다.")
        return

    print(f"처리 시작: gs://{bucket_name}/{file_name}")

    try:
        # 1. GCS에서 원시 데이터 파일 읽기
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        raw_data = blob.download_as_text()
        pull_requests = json.loads(raw_data)
        print(f"{len(pull_requests)}개의 PR 데이터를 JSON에서 로드했습니다.")

        # 2. 데이터 변환
        # 리스트 컴프리헨션을 사용하여 모든 PR 데이터를 한 번에 변환합니다.
        rows_to_insert = [transform_pr(pr) for pr in pull_requests]

        # 3. BigQuery에 데이터 삽입
        if rows_to_insert:
            table_ref = f"{GCP_PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
            print(f"BigQuery에 데이터 삽입 시작: {len(rows_to_insert)}개의 행을 {table_ref} 테이블에 넣습니다.")

            errors = bigquery_client.insert_rows_json(table_ref, rows_to_insert)

            if not errors:
                print("데이터 삽입 성공!")
            else:
                print(f"[에러 발생] BigQuery 데이터 삽입 중 에러: {errors}")
        else:
            print("삽입할 데이터가 없습니다.")

    except Exception as e:
        print(f"[에러 발생] 예상치 못한 에러: {e}")
        raise e

    print(f"처리 완료: {file_name}")