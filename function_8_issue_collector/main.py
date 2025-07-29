# function_8_issue_collector/main.py
import json
import logging
import processor

logging.basicConfig(level=logging.INFO)

def run(request):
    """Cloud Task로부터 이슈 처리 요청을 받는 진입점"""
    try:
        raw_data = request.get_data(as_text=True)
        request_json = json.loads(raw_data)

        issue_url = request_json.get('issue_url')
        if not issue_url:
            return ("'issue_url' is required.", 400)

        logging.info(f"Issue-Collector received job for Issue: {issue_url}")
        success = processor.process_single_issue(issue_url)

        return ("OK", 200) if success else ("Failed", 500)

    except Exception as e:
        logging.error(f"Critical error in Issue-Collector: {e}")
        return ("Internal Server Error", 500)