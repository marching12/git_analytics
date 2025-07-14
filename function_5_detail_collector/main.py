import json
import logging
import processor  # 아래에서 만들 processor.py를 임포트

logging.basicConfig(level=logging.INFO)


def run(request):
    """Cloud Task로부터 PR 처리 요청을 받는 진입점"""
    try:
        # Cloud Tasks는 OIDC 토큰을 자동으로 추가하지 않으므로 보안 검증은 생략
        raw_data = request.get_data(as_text=True)
        request_json = json.loads(raw_data)

        pr_url = request_json.get('pr_url')
        if not pr_url:
            return ("'pr_url' is required.", 400)

        logging.info(f"Detail-Collector received job for PR: {pr_url}")
        success = processor.process_single_pr(pr_url)

        return ("OK", 200) if success else ("Failed", 500)

    except Exception as e:
        logging.error(f"Critical error in Detail-Collector: {e}")
        return ("Internal Server Error", 500)