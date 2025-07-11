# ==============================================================================
# GCP Cloud Functions 배포 자동화 Makefile
# ==============================================================================

# .env 파일을 읽어와서 Makefile 변수로 사용합니다.
include .env
export

# --- 공용 변수 설정 ---
GCP_REGION = "us-central1"
SERVICE_ACCOUNT = "bcsd-github-analytics-debug@bcsd-github.iam.gserviceaccount.com"
RUNTIME = "python311"

# --- 함수 이름 및 디렉토리 ---
DISPATCHER_NAME = "github-repo-dispatcher"
DISPATCHER_DIR = "./function_1_dispatcher"
WORKER_NAME = "github-pr-collector-worker"
WORKER_DIR = "./function_2_worker"
TRANSFORMER_NAME = "github-data-transformer"
TRANSFORMER_DIR = "./function_3_transformer"
WEBHOOK_HANDLER_NAME = "github-webhook-handler"
WEBHOOK_HANDLER_DIR = "./function_4_webhook_handler"

# --- 트리거 리소스 ---
DISPATCHER_TRIGGER_TOPIC = "github-collection-scheduler"

# ==============================================================================
# 명령어 정의
# ==============================================================================

# 1. Dispatcher 함수 배포
deploy-dispatcher:
	@echo ">>> Deploying Dispatcher: $(DISPATCHER_NAME)"
	gcloud functions deploy $(DISPATCHER_NAME) \
	   --gen2 --runtime $(RUNTIME) --region $(GCP_REGION) \
	   --source $(DISPATCHER_DIR) --entry-point run \
	   --trigger-topic $(DISPATCHER_TRIGGER_TOPIC) \
	   --service-account $(SERVICE_ACCOUNT) \
	   --set-env-vars="GCP_PROJECT_ID=$(GCP_PROJECT_ID),GCP_REGION=$(GCP_REGION),REPO_OWNER=$(REPO_OWNER),SECRET_ID=$(SECRET_ID),TASK_QUEUE_ID=$(TASK_QUEUE_ID),WORKER_FUNCTION_URL=$(WORKER_FUNCTION_URL),WORKER_SERVICE_ACCOUNT=$(WORKER_SERVICE_ACCOUNT)"

# 2. Worker 함수 배포
deploy-worker:
	@echo ">>> Deploying Worker: $(WORKER_NAME)"
	gcloud functions deploy $(WORKER_NAME) \
	   --gen2 --runtime $(RUNTIME) --region $(GCP_REGION) \
	   --source $(WORKER_DIR) --entry-point run \
	   --trigger-http --no-allow-unauthenticated \
	   --service-account $(SERVICE_ACCOUNT) \
	   --set-env-vars="GCP_PROJECT_ID=$(GCP_PROJECT_ID),REPO_OWNER=$(REPO_OWNER),GCS_BUCKET_NAME=$(GCS_BUCKET_NAME),SECRET_ID=$(SECRET_ID),BIGQUERY_DATASET_ID=$(BIGQUERY_DATASET_ID),LABEL_MAPPING_TABLE_NAME=$(LABEL_MAPPING_TABLE_NAME),COMMON_TEAM_ID=$(COMMON_TEAM_ID),WORKER_FUNCTION_URL=$(WORKER_FUNCTION_URL)"

# 3. Transformer 함수 배포
deploy-transformer:
	@echo ">>> Deploying Transformer: $(TRANSFORMER_NAME)"
	gcloud functions deploy $(TRANSFORMER_NAME) \
	   --gen2 --runtime $(RUNTIME) --region $(GCP_REGION) \
	   --source $(TRANSFORMER_DIR) --entry-point run \
	   --trigger-resource $(GCS_BUCKET_NAME) \
	   --trigger-event google.storage.object.finalize \
	   --service-account $(SERVICE_ACCOUNT) \
	   --set-env-vars="GCP_PROJECT_ID=$(GCP_PROJECT_ID),BIGQUERY_DATASET_ID=$(BIGQUERY_DATASET_ID)"

# 4. Webhook Handler 함수 배포
deploy-webhook-handler:
	@echo ">>> Deploying Webhook Handler: $(WEBHOOK_HANDLER_NAME)"
	gcloud functions deploy $(WEBHOOK_HANDLER_NAME) \
	   --gen2 --runtime $(RUNTIME) --region $(GCP_REGION) \
	   --source $(WEBHOOK_HANDLER_DIR) --entry-point run \
	   --trigger-http --allow-unauthenticated \
	   --service-account $(SERVICE_ACCOUNT) \
	   --set-env-vars="GCP_PROJECT_ID=$(GCP_PROJECT_ID),GCS_BUCKET_NAME=$(GCS_BUCKET_NAME),WEBHOOK_SECRET_ID=$(WEBHOOK_SECRET_ID),REPO_OWNER=$(REPO_OWNER),SECRET_ID=$(SECRET_ID)"


# --- 전체 배포 명령어 ---
deploy-all: deploy-worker deploy-transformer deploy-webhook-handler deploy-dispatcher
	@echo "All functions have been deployed in order."

.PHONY: deploy-dispatcher deploy-worker deploy-transformer deploy-webhook-handler deploy-all