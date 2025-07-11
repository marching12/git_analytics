import logging
import processor

def run(request):
    """HTTP 요청을 받아 processor에게 작업을 위임하는 진입점"""
    try:
        headers = request.headers
        body = request.get_data()
        return processor.process_webhook(headers, body)
    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        return ("Permission denied.", 403)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return ("Internal Server Error.", 500)