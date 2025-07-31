from pydantic import BaseModel
from typing import Optional, Union, get_args, get_origin  # ✨ Union, get_args, get_origin 추가
from datetime import datetime
from google.cloud import bigquery


class PullRequest(BaseModel):
    pr_id: int
    repo_id: int
    team_id: Optional[int] = None
    pr_number: int
    title: Optional[str] = None
    state: Optional[str] = None
    author_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    commit_count: Optional[int] = None


class Review(BaseModel):
    review_id: int
    pr_id: int
    reviewer_id: Optional[int] = None
    state: str
    submitted_at: datetime


class Issue(BaseModel):
    issue_id: int
    repo_id: Optional[int] = None
    issue_number: int
    title: Optional[str] = None
    state: str
    author_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


# --- BigQuery 스키마 변환 및 모델 정보 헬퍼 함수 ---

def get_model_info(table_name):
    """테이블 이름에 따라 Pydantic 모델과 고유 키를 반환합니다."""
    model_map = {
        'pull_requests': (PullRequest, 'pr_id'),
        'reviews': (Review, 'review_id'),
        'issues': (Issue, 'issue_id')
    }
    return model_map.get(table_name, (None, None))


# --- ✨ 수정된 부분: Pydantic v2 문법으로 변경 ---
def pydantic_to_bigquery_schema(model_class):
    """Pydantic v2 모델을 BigQuery 스키마로 변환합니다."""
    schema = []
    type_mapping = {
        str: 'STRING',
        int: 'INT64',
        float: 'FLOAT64',
        bool: 'BOOL',
        datetime: 'TIMESTAMP'
    }

    # Pydantic v2에서는 model_fields를 사용
    for name, field in model_class.model_fields.items():
        field_type = field.annotation

        # Optional[T] 와 같은 Union 타입을 처리
        origin_type = get_origin(field_type)
        is_nullable = origin_type is Union and type(None) in get_args(field_type)

        if is_nullable:
            # Union[T, None]에서 실제 타입 T를 추출
            base_type = get_args(field_type)[0]
        else:
            base_type = field_type

        bq_type = type_mapping.get(base_type, 'STRING')
        mode = 'NULLABLE' if is_nullable else 'REQUIRED'

        schema.append(bigquery.SchemaField(name, bq_type, mode=mode))

    return schema