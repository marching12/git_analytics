import json
import logging
import traceback  # 오류 추적을 위한 라이브러리 임포트

# --- 로깅 설정 ---
# 다른 모듈보다 먼저 로깅 설정을 구성합니다.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def run(request):
    """
    HTTP 요청을 받아 processor에게 작업을 위임하는 진입점.
    시작 오류를 잡기 위해 모든 로직을 try-except로 감쌉니다.
    """
    try:
        # --- 함수가 호출될 때마다 필요한 모듈을 임포트 ---
        # 이렇게 하면 임포트 과정에서 발생하는 오류도 잡을 수 있습니다.
        import processor

        # 1. 요청 파싱
        raw_data = request.get_data(as_text=True)
        if not raw_data:
            logging.error("Request body is empty.")
            return ("Invalid request: Body is empty.", 400)

        request_json = json.loads(raw_data)

        if 'repo_name' not in request_json:
            logging.error("Invalid JSON: 'repo_name' key is missing.")
            return ("Invalid request: 'repo_name' is required.", 400)

        # 2. Processor에게 작업 위임
        repo_name = request_json['repo_name']
        collect_types = request_json.get('collect_types', ['pulls', 'issues', 'reviews'])

        logging.info(f"Main handler received a valid job for {repo_name}")

        success = processor.process_repo_data(repo_name, collect_types)

        if success:
            return ("Processing initiated successfully.", 202)
        else:
            # Processor 내부에서 이미 에러 로깅을 했을 것이므로, 여기서는 실패 응답만 반환
            return ("Failed to process data. Check logs for details.", 500)

    except Exception as e:
        # --- 모든 종류의 오류를 여기서 포착하여 로깅 ---
        # 컨테이너 시작 실패의 진짜 원인이 여기에 기록됩니다.
        error_traceback = traceback.format_exc()
        logging.error(f"An uncaught exception occurred: {e}")
        logging.error(f"Full Traceback:\n{error_traceback}")

        # 오류 내용을 응답으로 반환하여 배포 로그에서도 쉽게 확인 가능
        return (f"Internal Server Error: {e}\n{error_traceback}", 500)