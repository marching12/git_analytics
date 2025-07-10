# ==============================================================================
# GCP Cloud Functions 배포 자동화 Makefile (최종)
# ==============================================================================

# --- 공용 변수 설정 ---
# ### 중요 ###: 이 부분의 값들을 자신의 환경에 맞게 수정하세요.
GCP_PROJECT_ID = "bcsd-github"
GCP_REGION = "asia-northeast3"
SERVICE_ACCOUNT = "bcsd-github-analytics-debug@bcsd-github.iam.gserviceaccount.com"

# --- 함수 1 (Dispatcher) 설정 ---
DISPATCHER_NAME = "github-repo-dispatcher"
DISPATCHER_DIR = "./function_1_dispatcher"
DISPATCHER_TRIGGER_TOPIC = "github-collection-scheduler"
DISPATCHER_TASK_QUEUE = "github-collector-queue"
WORKER_FUNCTION_URL = "https://asia-northeast3-bcsd-github.cloudfunctions.net/github-pr-collector-worker"

# --- 함수 2 (Worker) 설정 ---
WORKER_NAME = "github-pr-collector-worker"
WORKER_DIR = "./function_2_worker"

# --- 함수 3 (Transformer) 설정 ---
TRANSFORMER_NAME = "github-data-transformer"
TRANSFORMER_DIR = "./function_3_transformer"
GCS_BUCKET_NAME = "bcsd-github-analytics-row-data"# Transformer와 Worker가 공통으로 사용

# --- 함수 4 (State Updater) 설정 ---
STATE_UPDATER_NAME = "github-state-updater"
STATE_UPDATER_DIR = "./function_4_state_updater"
STATE_UPDATER_TRIGGER_TOPIC = "github-update-state-scheduler"

# --- 공통 환경 변수 ---
REPO_OWNER = "BCSDLab"
SECRET_ID = "bcsd-github-analytics-pta"
DATASET_ID = "github_analytics"
TABLE_ID = "temp_pull_requests"


# ==============================================================================
# 명령어 정의
# ==============================================================================

# 1. Dispatcher 함수 배포
deploy-dispatcher:
	@echo ">>> Deploying Dispatcher: $(DISPATCHER_NAME)"
	gcloud functions deploy $(DISPATCHER_NAME) \
		--gen2 --runtime python311 --region $(GCP_REGION) \
		--source $(DISPATCHER_DIR) --entry-point run \
		--trigger-topic $(DISPATCHER_TRIGGER_TOPIC) \
		--service-account $(SERVICE_ACCOUNT) \
		--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID),GCP_REGION=$(GCP_REGION),TASK_QUEUE_ID=$(DISPATCHER_TASK_QUEUE),WORKER_FUNCTION_URL=$(WORKER_FUNCTION_URL),WORKER_SERVICE_ACCOUNT=$(SERVICE_ACCOUNT)

# 2. Worker 함수 배포
deploy-worker:
	@echo ">>> Deploying Worker: $(WORKER_NAME)"
	gcloud functions deploy $(WORKER_NAME) \
		--gen2 --runtime python311 --region $(GCP_REGION) \
		--source $(WORKER_DIR) --entry-point run \
		--trigger-http --no-allow-unauthenticated \
		--service-account $(SERVICE_ACCOUNT) \
		--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID),REPO_OWNER=$(REPO_OWNER),GCS_BUCKET_NAME=$(GCS_BUCKET_NAME),SECRET_ID=$(SECRET_ID)

# 3. Transformer 함수 배포
deploy-transformer:
	@echo ">>> Deploying Transformer: $(TRANSFORMER_NAME)"
	gcloud functions deploy $(TRANSFORMER_NAME) \
		--gen2 --runtime python311 --region $(GCP_REGION) \
		--source $(TRANSFORMER_DIR) --entry-point run \
		--trigger-resource $(GCS_BUCKET_NAME) \
		--trigger-event google.storage.object.finalize \
		--service-account $(SERVICE_ACCOUNT) \
		--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID),DATASET_ID=$(DATASET_ID),TABLE_ID=$(TABLE_ID)

# 4. State Updater 함수 배포
deploy-state-updater:
	@echo ">>> Deploying State Updater: $(STATE_UPDATER_NAME)"
	gcloud functions deploy $(STATE_UPDATER_NAME) \
		--gen2 --runtime python311 --region $(GCP_REGION) \
		--source $(STATE_UPDATER_DIR) --entry-point run \
		--trigger-topic $(STATE_UPDATER_TRIGGER_TOPIC) \
		--service-account $(SERVICE_ACCOUNT) \
		--set-env-vars GCP_PROJECT_ID=$(GCP_PROJECT_ID),GCS_BUCKET_NAME=$(GCS_BUCKET_NAME),REPO_OWNER=$(REPO_OWNER)


# --- 전체 배포 명령어 ---
deploy-all:
	@echo "Deploying all functions... Note: This may not work on the first run."
	@echo "Run 'make deploy-worker' first, then update WORKER_FUNCTION_URL in this Makefile, then run 'make deploy-all' again."
	make deploy-worker
	make deploy-transformer
	make deploy-state-updater
	make deploy-dispatcher

.PHONY: deploy-dispatcher deploy-worker deploy-transformer deploy-state-updater deploy-all