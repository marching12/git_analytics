# Git Analytics 프로젝트

## 1. 프로젝트 개요

본 프로젝트는 GitHub 저장소의 데이터를 수집, 분석, 처리하기 위한 이벤트 기반의 분산 파이프라인 시스템입니다. 각 기능은 독립적인 서버리스 함수(Serverless Function)로 구현되어 있으며, Google Cloud Pub/Sub과 같은 메시징 큐를 통해 비동기적으로 통신합니다.

이 아키텍처는 높은 확장성, 유연성, 그리고 복원력을 가지며, 대규모 데이터 처리에도 효율적으로 대응할 수 있도록 설계되었습니다.

## 2. 아키텍처 및 함수 설명

프로젝트는 여러 개의 독립적인 함수로 구성된 마이크로서비스 아키텍처를 따릅니다. 각 함수는 명확하게 정의된 단일 책임을 가집니다.

| 함수 이름 | 주 역할 | 설명 |
| :--- | :--- | :--- |
| **`function_1_dispatcher`** | 분석 파이프라인 시작 | 분석할 GitHub 저장소 정보를 받아 초기 작업을 생성하고 Worker에게 작업을 분배합니다. |
| **`function_2_worker`** | 기본 데이터 수집 | Dispatcher로부터 작업을 받아 GitHub API를 통해 기본적인 데이터(커밋, PR 목록 등)를 수집합니다. |
| **`function_3_transformer`** | 데이터 변환 | 수집된 원본 데이터를 분석에 용이한 형태로 가공하고 정제합니다. |
| **`function_4_webhook_handler`**| 실시간 이벤트 처리 | GitHub Webhook(Push, PR 생성 등)을 수신하여 실시간으로 분석 파이프라인을 트리거합니다. |
| **`function_5_detail_collector`**| 상세 데이터 수집 | 기본 데이터(예: 커밋 목록)를 기반으로 각 항목의 상세 정보(예: 커밋 별 변경 파일)를 추가 수집합니다. |
| **`function_6_merger`** | 데이터 병합 | 여러 파이프라인에서 수집되고 처리된 데이터를 최종적으로 하나의 완성된 데이터 모델로 병합합니다. |
| **`function_7_validator`** | 데이터 검증 | 병합된 데이터가 최종 저장소(예: BigQuery)의 스키마와 일치하는지, 누락된 값은 없는지 검증합니다. |
| **`libs`** | 공통 라이브러리 | 모든 함수에서 공통으로 사용하는 데이터 모델, GitHub API 클라이언트 등을 포함합니다. |

---

### 세부 동작 원리 및 설계 사상

#### `function_1_dispatcher`
*   **동작 방식**: HTTP 요청 등으로 저장소 URL과 분석 범위를 입력받습니다. 이 정보를 바탕으로 작업 메시지를 생성하여 Pub/Sub 토픽(예: `dispatch-topic`)에 발행(Publish)합니다.
*   **설계 이유**: 전체 프로세스를 시작하는 진입점(Entry Point)을 단일화하고, 실제 데이터 수집을 담당하는 Worker와 분리(Decoupling)하기 위함입니다.
*   **장점**: Dispatcher는 Worker의 동작 방식이나 개수에 대해 알 필요가 없습니다. 이로 인해 Worker를 독립적으로 확장하거나 교체하기 용이해집니다. (예: Worker 부하가 많아지면 Worker 함수 인스턴스만 늘리면 됨)

#### `function_2_worker`
*   **동작 방식**: `dispatch-topic`을 구독(Subscribe)하고 있다가 메시지를 받으면, `libs/github_client.py`를 사용해 해당 저장소의 기본 정보를 수집합니다. 수집된 데이터는 다음 단계(Transformer)로 전달하기 위해 또 다른 Pub/Sub 토픽에 발행합니다.
*   **설계 이유**: 시간이 오래 걸릴 수 있는 데이터 수집 작업을 별도의 함수로 분리하여 병렬로 처리하기 위함입니다.
*   **장점**: 여러 저장소에 대한 분석 요청이 들어와도 다수의 Worker가 동시에 작업을 처리하므로 전체 분석 시간을 크게 단축할 수 있습니다.

#### `function_4_webhook_handler`
*   **동작 방식**: GitHub 저장소에 Webhook으로 등록되어, 특정 이벤트(예: `git push`)가 발생할 때마다 GitHub으로부터 HTTP POST 요청을 받습니다. 요청 본문(payload)을 파싱하여 필요한 정보를 추출하고, 이를 기반으로 분석 파이프라인(주로 Worker나 Detail Collector)을 트리거하는 메시지를 발행합니다.
*   **설계 이유**: 정기적인 분석 외에, 코드 변경과 같은 이벤트에 실시간으로 반응하는 분석 시스템을 구축하기 위함입니다.
*   **장점**: 데이터 변경이 발생했을 때만 시스템이 동작하므로 리소스를 효율적으로 사용할 수 있으며, 거의 실시간에 가까운 데이터 분석이 가능해집니다.

#### `libs/data_models.py` & `pydantic`
*   **구현 방식**: `pydantic` 라이브러리를 사용하여 각 데이터(예: Commit, PullRequest)의 구조를 클래스로 명확하게 정의합니다. 각 함수는 이 데이터 모델을 기준으로 데이터를 주고받습니다.
*   **설계 이유**: 함수 간에 전달되는 데이터의 형식을 강제하고, 데이터의 유효성을 보장하기 위함입니다.
*   **장점**:
    *   **데이터 정합성**: 잘못된 타입이나 누락된 필드가 있는 데이터가 파이프라인에 유입되는 것을 원천적으로 차단하여 데이터 오염을 방지합니다.
    *   **개발 편의성**: IDE의 자동완성 지원을 받을 수 있고, 데이터 구조를 명확히 알 수 있어 개발 및 유지보수가 쉬워집니다.

---

## 3. 라이브러리 의존성

본 프로젝트는 각 함수의 `requirements.txt`에 명시된 라이브러리들을 사용합니다. 주요 공통 라이브러리는 다음과 같습니다.

| 라이브러리 | 사용 이유 |
| :--- | :--- |
| **`google-cloud-pubsub`** | 각 함수 간의 비동기 메시지 통신을 위해 사용합니다. 이를 통해 시스템 전체가 느슨하게 결합(Loosely Coupled)됩니다. |
| **`google-cloud-storage`** | 함수 간에 대용량 데이터를 전달하거나, 처리 중간 결과를 임시 저장하는 용도로 사용될 수 있습니다. |
| **`google-cloud-bigquery`** | 분석이 완료된 최종 데이터를 저장하고 쿼리하기 위한 데이터 웨어하우스로 사용됩니다. |
| **`requests` / `httpx`** | `libs/github_client.py` 내부에서 GitHub REST API를 호출하기 위해 사용됩니다. |
| **`pydantic`** | `libs/data_models.py`에서 데이터 모델을 정의하고 유효성을 검증하기 위해 사용됩니다. |

---

## 4. 환경변수

이 프로젝트를 실행하기 위해서는 다음과 같은 환경변수 설정이 필요합니다.

```bash
# Google Cloud Platform 관련
export GCP_PROJECT="your-gcp-project-id"
export GCP_REGION="your-gcp-region"

# GitHub API 접근 토큰
export GITHUB_TOKEN="your-personal-access-token"

# Pub/Sub 토픽 및 구독 이름
export DISPATCH_TOPIC="dispatch-topic-name"
export WORKER_TOPIC="worker-topic-name"
export TRANSFORM_TOPIC="transform-topic-name"
# ... (각 파이프라인 단계에 맞는 토픽들)

# 최종 데이터 저장소 정보
export BIGQUERY_DATASET_ID="analytics_dataset"
export BIGQUERY_TABLE_ID="git_stats_table"

# Webhook 보안을 위한 Secret
export WEBHOOK_SECRET="your-github-webhook-secret"
```

---

## 5. 확장성

이 아키텍처는 다음과 같은 방향으로 쉽게 확장할 수 있습니다.

1.  **새로운 분석 기능 추가**:
    *   예를 들어, "코드 복잡도 분석" 기능을 추가하고 싶다면, 새로운 `function_8_complexity_analyzer` 함수를 만듭니다.
    *   이 함수가 `transform-topic`을 구독하도록 설정하면, 기존 파이프라인에 영향을 주지 않고 새로운 분석 파이프를 간단하게 추가할 수 있습니다.

2.  **다른 데이터 소스 연동 (예: GitLab, Bitbucket)**:
    *   `libs`에 `gitlab_client.py`를 추가합니다.
    *   GitLab API의 데이터 구조에 맞는 새로운 `Worker`와 `Transformer` 함수를 구현하여 기존 Dispatcher에 연결하면, 여러 Git 호스팅 서비스의 데이터를 동일한 파이프라인으로 처리할 수 있습니다.

3.  **데이터 시각화 대시보드 연동**:
    *   최종 데이터가 저장된 BigQuery에 Google Looker Studio나 Grafana와 같은 시각화 도구를 연결하여 분석 결과를 실시간으로 모니터링하는 대시보드를 구축할 수 있습니다.