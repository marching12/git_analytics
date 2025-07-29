# function_8_issue_collector/processor.py
import logging
from datetime import datetime

import config
from libs import collector_utils
from libs.data_models import Issue

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_team_id_from_labels(labels, label_map, common_team_id):
    """(PR Collector와 동일) 레이블 목록을 기반으로 팀 ID를 결정합니다."""
    for label in labels:
        if label.get('name') in label_map:
            return label_map[label['name']]
    return common_team_id


def process_single_issue(issue_url):
    """이슈 하나에 대한 상세 정보를 수집하여 GCS에 저장합니다."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"Issue-Collector processing issue: {issue_url}")

    try:
        client = collector_utils.get_github_client(config.GCP_PROJECT_ID, config.SECRET_ID)
        label_map = collector_utils.get_label_team_map(config.LABEL_MAPPING_TABLE_ID)

        # 1. 이슈 상세 정보 처리 (이슈 Collector 고유 로직)
        issue_detail_json = client.get(issue_url).json()  # 일반 get 요청
        team_id = get_team_id_from_labels(issue_detail_json.get('labels', []), label_map, config.COMMON_TEAM_ID)

        issue_model = Issue(
            issue_id=issue_detail_json['id'],
            repo_id=issue_detail_json.get('repository', {}).get('id'),
            issue_number=issue_detail_json['number'],
            title=issue_detail_json['title'],
            state=issue_detail_json['state'],
            author_id=issue_detail_json.get('user', {}).get('id'),
            created_at=issue_detail_json['created_at'],
            updated_at=issue_detail_json['updated_at'],
            closed_at=issue_detail_json['closed_at'],
            # team_id는 Issue 모델에 없으므로 추가가 필요할 수 있습니다.
            # 지금은 Pydantic이 모르는 필드는 무시합니다.
        )

        # 2. 공용 라이브러리를 사용하여 GCS에 업로드
        blob_name = f"issues/issue_{issue_model.issue_id}_{timestamp}.jsonl"
        collector_utils.upload_models_to_gcs(config.GCS_BUCKET_NAME, blob_name, [issue_model])

        logging.info(f"Successfully processed Issue #{issue_model.issue_number}")
        return True

    except Exception as e:
        logging.error(f"Failed to process Issue {issue_url}: {e}")
        return False