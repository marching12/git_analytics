# ==============================================================================
# 로컬 개발 환경에서 GCS -> BigQuery 데이터 변환을 테스트하기 위한 스크립트
# ==============================================================================

# --- 1. 필요한 라이브러리 가져오기 ---
import os
import json
from datetime import datetime, timezone
from google.cloud import storage, bigquery
from dotenv import load_dotenv

# --- 2. 설정: .env 파일 로드 및 환경 변수 설정 ---
load_dotenv()

# ### 중요 ###: 아래 값들을 자신의 환경에 맞게 확인 및 수정해야 합니다.

# GCS 버킷 이름
GCS_BUCKET_NAME = "bcsd-github-analytics-row-data"

# BigQuery 테이블 정보
PROJECT_ID = os.getenv("GCP_PROJECT_ID")  # .env 파일에 GCP 프로젝트 ID 추가 필요
DATASET_ID = "github_analytics"
TABLE_ID = "temp_pull_requests"

# [시뮬레이션 대상 파일]
# 이전에 1번 스크립트로 GCS에 업로드했던 파일의 전체 경로를 여기에 적어줍니다.
# 이 파일을 읽어서 BigQuery에 넣는 테스트를 진행합니다.
GCS_FILE_TO_PROCESS = "raw/BCSDLab/KOIN_ANDROID/prs/2025/07/05/2025-07-05T10:58:03.617661+00:00.json"


# --- 3. 데이터 변환 및 BigQuery 적재 함수 ---
def transform_and_load_prs(bucket_name, file_name):
    """
    GCS에서 지정된 파일을 읽고, 데이터를 정제하여 BigQuery에 삽입합니다.
    """
    # 스토리지와 BigQuery 클라이언트를 초기화합니다.
    storage_client = storage.Client()
    bigquery_client = bigquery.Client(project=PROJECT_ID)

    # GCS에서 파일 내용(원시 데이터)을 텍스트로 읽어옵니다.
    print(f"GCS에서 파일 읽기 시작: gs://{bucket_name}/{file_name}")
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    raw_data = blob.download_as_text()

    # 읽어온 텍스트를 JSON(파이썬 리스트)으로 변환합니다.
    pull_requests = json.loads(raw_data)
    print("파일 읽기 및 JSON 파싱 완료.")

    rows_to_insert = []  # BigQuery에 삽입할 행들을 담을 리스트

    # 각 PR 데이터를 순회하며 BigQuery 테이블 스키마에 맞게 가공합니다.
    for pr in pull_requests:
        # 생성, 병합, 종료 시간 처리 (타임존 정보 포함)
        created_at = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) if pr.get('created_at') else None
        merged_at = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) if pr.get('merged_at') else None
        closed_at = datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00')) if pr.get('closed_at') else None

        # 리드 타임 계산 (병합된 경우에만 초 단위로 계산)
        lead_time_seconds = None
        if created_at and merged_at:
            lead_time = merged_at - created_at
            lead_time_seconds = int(lead_time.total_seconds())

        # BigQuery 테이블의 한 행(row)을 딕셔너리 형태로 만듭니다.
        # 테이블 스키마의 필드 이름과 딕셔너리의 key 이름이 일치해야 합니다.
        row = {
            "pr_id": pr['id'],
            "pr_number": pr['number'],
            "title": pr['title'],
            "author": pr['user']['login'] if pr.get('user') else None,
            "state": pr['state'],
            "created_at": created_at.isoformat() if created_at else None,
            "merged_at": merged_at.isoformat() if merged_at else None,
            "closed_at": closed_at.isoformat() if closed_at else None,
            "lead_time_seconds": lead_time_seconds,
            "repository": pr['base']['repo']['name'] if pr.get('base') and pr['base'].get('repo') else None,
            "merged": bool(pr.get('merged_at')),
        }
        rows_to_insert.append(row)

    # 가공된 데이터가 있을 경우, BigQuery에 스트리밍 방식으로 삽입합니다.
    if rows_to_insert:
        table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
        print(f"BigQuery에 데이터 삽입 시작: {len(rows_to_insert)}개의 행을 {table_ref} 테이블에 넣습니다.")

        errors = bigquery_client.insert_rows_json(table_ref, rows_to_insert)

        if not errors:
            print("데이터 삽입 성공!")
        else:
            print(f"[에러 발생] 데이터 삽입 중 에러 발생: {errors}")
    else:
        print("삽입할 데이터가 없습니다.")


# --- 4. 스크립트 메인 실행 부분 ---
if __name__ == "__main__":
    print("=== GCS -> BigQuery 변환 테스트 스크립트 시작 ===")
    try:
        # GCP 프로젝트 ID가 제대로 설정되었는지 확인
        if not PROJECT_ID:
            raise ValueError("환경 변수 GCP_PROJECT_ID가 설정되지 않았습니다. .env 파일을 확인해주세요.")

        transform_and_load_prs(GCS_BUCKET_NAME, GCS_FILE_TO_PROCESS)

    except Exception as e:
        print(f"[에러 발생] 예상치 못한 에러: {e}")

    print("=== 변환 테스트 스크립트 종료 ===")