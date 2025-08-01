import os
import functions_framework
from google.cloud import pubsub_v1
import config

# Pub/Sub 클라이언트 초기화
publisher_client = pubsub_v1.PublisherClient()


@functions_framework.cloud_event
def run(cloud_event):
    """
    GCS 파일 생성 이벤트를 받아, 해당 파일의 경로를 Pub/Sub 토픽으로 발행합니다.
    """
    data = cloud_event.data
    # bucket_name = data["bucket"] # 버킷 이름은 메시지에 포함할 필요 없음
    file_name = data["name"]

    print(f"GCS 파일 감지: '{file_name}'. Pub/Sub으로 경로를 전달합니다.")

    # config.py에서 토픽 정보 가져오기
    topic_path = publisher_client.topic_path(config.GCP_PROJECT_ID, config.PUBSUB_TOPIC_ID)

    try:
        # 파일 경로(이름)를 메시지로 발행
        # data 인코딩이 필요합니다.
        future = publisher_client.publish(topic_path, data=file_name.encode("utf-8"))
        message_id = future.result()
        print(f"파일 '{file_name}'의 경로를 메시지 ID {message_id}로 토픽 '{config.PUBSUB_TOPIC_ID}'에 발행했습니다.")

    except Exception as e:
        print(f"메시지 발행 실패: {e}")
        # 오류를 다시 발생시켜 Cloud Functions가 재시도하도록 함
        raise e