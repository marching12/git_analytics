from google.cloud import bigquery


def _generate_model_code(client: bigquery.Client, table_id: str, class_name: str) -> str:
    """하나의 BigQuery 테이블 스키마를 읽어 Pydantic 모델 코드 문자열을 생성합니다."""

    table = client.get_table(table_id)
    print(f"Generating model for {table_id}...")

    # BigQuery 타입을 Python/Pydantic 타입으로 매핑
    type_mapping = {
        "INTEGER": "int", "INT64": "int",
        "FLOAT": "float", "FLOAT64": "float",
        "STRING": "str",
        "BOOLEAN": "bool", "BOOL": "bool",
        "TIMESTAMP": "datetime",
        "DATETIME": "datetime",
    }

    model_code = f"class {class_name}(BaseModel):\n"
    for field in table.schema:
        field_type = type_mapping.get(field.field_type, "str")
        # NULLABLE 필드는 Optional 타입으로 처리
        if field.mode == 'NULLABLE':
            field_type = f"Optional[{field_type}] = None"
        model_code += f"    {field.name}: {field_type}\n"

    return model_code + "\n"


def generate_pydantic_models():
    """지정된 모든 테이블에 대한 Pydantic 모델을 생성하여 파일에 씁니다."""
    client = bigquery.Client(project="bcsd-github")

    # 생성할 테이블과 클래스 이름 매핑
    tables_to_generate = {
        "bcsd-github.github_analytics.pull_requests": "PullRequest",
        "bcsd-github.github_analytics.reviews": "Review",
        "bcsd-github.github_analytics.issues": "Issue",
    }

    # 최종 파일에 쓸 전체 코드
    final_code = "from pydantic import BaseModel\n"
    final_code += "from typing import Optional\n"
    final_code += "from datetime import datetime\n\n"

    for table_id, class_name in tables_to_generate.items():
        final_code += _generate_model_code(client, table_id, class_name)

    # data_models.py 파일에 최종 코드 저장
    with open("../libs/data_models.py", "w", encoding="utf-8") as f:
        f.write(final_code)

    print("✅ data_models.py has been generated successfully with all models.")


if __name__ == "__main__":
    generate_pydantic_models()