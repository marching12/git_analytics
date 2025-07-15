import json
import logging

import processor

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def run(request):
    """Dispatcher로부터 레포 처리 요청을 받아 PR 목록을 Fan-out하는 진입점"""

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

    # 2. Processor에게 작업 위임
    logging.info(f"PR-Lister received job for repo: {repo_name}")
    success = processor.list_and_dispatch_prs(repo_name)

    if success:
        return ("Successfully fanned out tasks.", 202)
    else:
        return ("Failed to fan-out tasks.", 500)