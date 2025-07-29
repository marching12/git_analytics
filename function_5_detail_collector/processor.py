import logging
from datetime import datetime

import config
from libs import collector_utils  # ✨ 새로 만든 공용 라이브러리 임포트
from libs.data_models import PullRequest, Review

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def get_team_id_from_labels(labels, label_map, common_team_id):
    """레이블 목록을 기반으로 팀 ID를 결정합니다."""
    for label in labels:
        if label.get('name') in label_map:
            return label_map[label['name']]
    return common_team_id


def process_single_pr(pr_url):
    """PR 하나에 대한 상세 정보와 리뷰를 수집하여 GCS에 저장합니다."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.info(f"Detail-Collector processing PR: {pr_url}")

    try:
        # --- 1. ✨ 공용 라이브러리를 사용하여 클라이언트와 설정 정보 가져오기 ---
        client = collector_utils.get_github_client(config.GCP_PROJECT_ID, config.SECRET_ID)
        label_map = collector_utils.get_label_team_map(config.LABEL_MAPPING_TABLE_ID)

        # --- 2. PR 상세 정보 처리 (이 부분은 PR-Collector 고유의 로직) ---
        pr_detail_json = client.get_pr_detail(pr_url)
        team_id = get_team_id_from_labels(pr_detail_json.get('labels', []), label_map, config.COMMON_TEAM_ID)

        pr_model = PullRequest(
            pr_id=pr_detail_json['id'], repo_id=pr_detail_json['head']['repo']['id'],
            team_id=team_id, pr_number=pr_detail_json['number'], title=pr_detail_json['title'],
            state=pr_detail_json['state'], author_id=pr_detail_json.get('user', {}).get('id'),
            created_at=pr_detail_json['created_at'], updated_at=pr_detail_json['updated_at'],
            merged_at=pr_detail_json['merged_at'], closed_at=pr_detail_json['closed_at'],
            additions=pr_detail_json['additions'], deletions=pr_detail_json['deletions'],
            commit_count=pr_detail_json['commits'],
        )

        # --- 3. ✨ 공용 라이브러리를 사용하여 GCS에 업로드 ---
        pr_blob_name = f"pull_requests/pr_{pr_model.pr_id}_{timestamp}.jsonl"
        collector_utils.upload_models_to_gcs(config.GCS_BUCKET_NAME, pr_blob_name, [pr_model])

        # --- 4. 리뷰 정보 처리 (이 부분도 PR-Collector 고유의 로직) ---
        reviews_json = client.get_reviews_for_pr(pr_url)
        collected_reviews = [
            Review(
                review_id=review['id'], pr_id=pr_detail_json['id'],
                reviewer_id=review.get('user', {}).get('id'),
                state=review['state'], submitted_at=review['submitted_at'],
            ) for review in reviews_json
        ]

        # --- 5. ✨ 공용 라이브러리를 사용하여 GCS에 업로드 ---
        review_blob_name = f"reviews/pr_{pr_model.pr_id}_reviews_{timestamp}.jsonl"
        collector_utils.upload_models_to_gcs(config.GCS_BUCKET_NAME, review_blob_name, collected_reviews)

        logging.info(f"Successfully processed PR #{pr_model.pr_number}")
        return True

    except Exception as e:
        logging.error(f"Failed to process PR {pr_url}: {e}")
        return False