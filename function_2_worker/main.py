import json
import logging
import os

import config
import processor
from google.auth.transport import requests
from google.oauth2 import id_token

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _validate_token(request):
    """(Dispatcher로부터의) OIDC 토큰을 검증합니다."""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise PermissionError("Authorization header is missing or invalid.")

        token = auth_header.split("Bearer ")[1]

        # 로컬 테스트 환경에서는 토큰 검증을 건너뜁니다.
        if os.getenv("FUNCTIONS_EMULATOR", "false").lower() == "true":
            logging.warning("Running in local emulator, skipping OIDC token validation.")
            return

        audience = config.WORKER_FUNCTION_URL  # 이 Worker 자신의 URL
        if not audience:
            raise ValueError("Target audience (WORKER_FUNCTION_URL) is not configured.")

        id_token.verify_oauth2_token(token, requests.Request(), audience=audience)
        logging.info("OIDC token validation successful.")

    except Exception as e:
        logging.error(f"Token validation failed: {e}")
        raise PermissionError("Token validation failed")


def run(request):
    """Dispatcher로부터 레포 처리 요청을 받아 PR 목록을 Fan-out하는 진입점"""

    # 1. 보안 검증
    try:
        _validate_token(request)
    except PermissionError as e:
        return (str(e), 403)

    # 2. 요청 파싱
    try:
        raw_data = request.get_data(as_text=True)
        request_json = json.loads(raw_data)
        repo_name = request_json.get('repo_name')
        if not repo_name:
            return ("'repo_name' is required.", 400)
    except Exception as e:
        logging.error(f"Error parsing request: {e}")
        return ("Bad Request", 400)

    # 3. Processor에게 작업 위임
    logging.info(f"PR-Lister received job for repo: {repo_name}")
    success = processor.list_and_dispatch_prs(repo_name)

    if success:
        return ("Successfully fanned out tasks.", 202)
    else:
        return ("Failed to fan-out tasks.", 500)