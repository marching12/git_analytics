import os
import json
import logging

import processor
import config
from google.auth.transport import requests
from google.oauth2 import id_token

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _validate_token(request):
    """요청 헤더의 OIDC 토큰을 검증하여 허가된 호출인지 확인합니다."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise PermissionError("Authorization header is missing or invalid.")

    token = auth_header.split("Bearer ")[1]

    # config.WORKER_FUNCTION_URL은 2차 배포 시 환경 변수로 주입됩니다.
    # 이 값이 없으면 verify_oauth2_token에서 자연스럽게 오류가 발생합니다.
    audience = config.WORKER_FUNCTION_URL
    if not audience:
        raise ValueError("Target audience (WORKER_FUNCTION_URL) is not configured.")

    id_token.verify_oauth2_token(token, requests.Request(), audience=audience)
    logging.info("OIDC token validation successful.")


def run(request):
    """HTTP 요청을 받아 processor에게 작업을 위임하는 최종 진입점"""
    try:
        _validate_token(request)
    except Exception as e:
        logging.error(f"Permission denied: {e}")
        return ("Unauthorized", 403)

    try:
        raw_data = request.get_data(as_text=True)
        if not raw_data:
            return ("Request body is empty.", 400)
        request_json = json.loads(raw_data)
        if 'repo_name' not in request_json:
            return ("'repo_name' is required.", 400)
    except json.JSONDecodeError:
        return ("Malformed JSON.", 400)

    repo_name = request_json['repo_name']
    collect_types = request_json.get('collect_types', ['pulls', 'issues', 'reviews'])

    logging.info(f"Main handler received a valid job for {repo_name}")
    success = processor.process_repo_data(repo_name, collect_types)

    if success:
        return ("Processing initiated successfully.", 202)
    else:
        return ("Failed to initiate processing due to internal error.", 500)