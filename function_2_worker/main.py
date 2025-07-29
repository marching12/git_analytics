import json
import logging

import processor

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def run(request):
    """Dispatcher로부터 레포 처리 요청을 받아 PR과 이슈 Task를 Fan-out하는 진입점"""

    # 1. 요청 파싱
    try:
        raw_data = request.get_data(as_text=True)
        request_json = json.loads(raw_data)
        repo_name = request_json.get('repo_name')
        if not repo_name:
            logging.error("'repo_name' is required in the request body.")
            return ("'repo_name' is required.", 400)
    except Exception as e:
        logging.error(f"Error parsing request: {e}")
        return ("Bad Request", 400)

    # 2. Processor에게 작업 위임 (✨ 함수 이름 및 로그 메시지 수정)
    logging.info(f"Worker received job for repo: {repo_name}")
    success = processor.process_repository(repo_name)

    if success:
        return ("Successfully dispatched tasks.", 202)
    else:
        return ("Failed to dispatch tasks.", 500)