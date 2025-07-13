import os
import json
import logging
from datetime import datetime

import processor
import config
from google.auth.transport import requests
from google.oauth2 import id_token

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _validate_token(request):
    """요청 헤더의 OIDC 토큰을 검증하여 허가된 호출인지 확인합니다."""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise PermissionError("Authorization header is missing or invalid.")

        token = auth_header.split("Bearer ")[1]

        # 로컬 테스트 환경에서는 토큰 검증을 건너뜁니다.
        if os.getenv("FUNCTIONS_EMULATOR", "false").lower() == "true":
            logging.warning("Running in local emulator, skipping OIDC token validation.")
            return

        audience = config.WORKER_FUNCTION_URL
        if not audience:
            raise ValueError("Target audience (WORKER_FUNCTION_URL) is not configured.")

        id_token.verify_oauth2_token(token, requests.Request(), audience=audience)

        logging.info("OIDC token validation successful.")

    except Exception as e:
        logging.error(f"Token validation failed: {e}")
        raise PermissionError("Token validation failed")


def run(request):
    """HTTP 요청을 받아 processor에게 작업을 위임하는 최종 진입점"""

    # 1. 보안 토큰 검증
    try:
        _validate_token(request)
    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        return ("Unauthorized", 403)

    # 2. 요청 파싱
    try:
        raw_data = request.get_data(as_text=True)
        if not raw_data:
            logging.error("Request body is empty.")
            return ("Invalid request: Body is empty.", 400)

        request_json = json.loads(raw_data)

        if 'repo_name' not in request_json:
            logging.error("Invalid JSON: 'repo_name' key is missing.")
            return ("Invalid request: 'repo_name' is required.", 400)

    except json.JSONDecodeError:
        logging.error("Failed to decode JSON from request body.")
        return ("Malformed JSON.", 400)
    except Exception as e:
        logging.error(f"Error parsing request: {e}")
        return ("Internal Server Error during request parsing.", 500)

    # 3. Processor에게 작업 위임
    repo_name = request_json['repo_name']
    collect_types = request_json.get('collect_types', ['pulls', 'issues', 'reviews'])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logging.info(f"Main handler received job for {repo_name} at {timestamp}")

    try:
        success = processor.process_repo_data(repo_name, collect_types, timestamp)

        if success:
            return ("Processing initiated successfully.", 202)
        else:
            return ("Failed to initiate processing due to an error in the processor.", 500)

    except Exception as e:
        logging.error(f"Critical error calling processor for {repo_name}: {e}")
        return ("Internal Server Error.", 500)