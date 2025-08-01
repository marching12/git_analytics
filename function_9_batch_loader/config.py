# function_9_batch_loader/config.py
import os

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
BIGQUERY_DATASET_ID = os.getenv("BIGQUERY_DATASET_ID")
PUBSUB_SUBSCRIPTION_ID = os.getenv("PUBSUB_SUBSCRIPTION_ID") # 읽어올 Pub/Sub 구독 ID
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")