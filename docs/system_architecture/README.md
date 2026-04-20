# MirrAI 시스템 아키텍처

## 개요

MirrAI는 Django 서버 렌더링 UI와 DRF API, Supabase PostgreSQL, Redis, ChromaDB, OpenAI를 조합한 구조다.  
고객 추천 흐름, 디자이너 상담 보조, 매장 리포트, 트렌드 갱신 파이프라인이 한 저장소 안에서 함께 동작한다.

## 상위 구성도

```mermaid
flowchart TB
    subgraph Client[Client Layer]
        C1[고객 화면]
        C2[디자이너 / 매장 화면]
    end

    subgraph Web[Web Layer]
        U[URL Router<br/>mirrai_project/urls.py<br/>app/urls_front.py]
        T[Template / Front View<br/>app/front_views.py<br/>templates/*]
        A[DRF API<br/>app/api/v1/*]
    end

    subgraph Domain[Domain / Service Layer]
        S1[추천 / 상담 서비스<br/>services_django.py<br/>admin_services.py]
        S2[챗봇 서비스<br/>app/services/chatbot/*]
        S3[트렌드 파이프라인<br/>app/trend_pipeline/*]
        S4[캐시 / 스토리지 / 세션<br/>runtime_cache.py<br/>storage_service.py<br/>settings_helpers.py]
    end

    subgraph Data[Data Layer]
        D1[(Supabase PostgreSQL)]
        D2[(Redis)]
        D3[(Supabase Storage / Local Media)]
        D4[(ChromaDB Trends / NCS)]
        D5[(ChromaDB Chatbot)]
    end

    Ext[OpenAI Responses API]
    RP[RunPod optional]
    Sch[Trend Scheduler]

    C1 --> U --> T
    C2 --> U --> T
    T --> A
    A --> S1
    A --> S2
    S1 --> S4
    S1 --> D1
    S1 --> D2
    S1 --> D3
    S2 --> D5
    S2 --> Ext
    Sch --> S3
    S3 --> D4
    S3 -. optional .-> RP
```

## 핵심 요청 흐름

### 1. 고객 추천 흐름

```mermaid
sequenceDiagram
    actor Customer as 고객
    participant View as Django Front View
    participant API as Recommendation Service
    participant DB as Supabase PostgreSQL
    participant Storage as Storage Service

    Customer->>View: 설문 / 촬영 / 추천 요청
    View->>API: 고객 정보, 설문, 캡처 전달
    API->>Storage: 얼굴 이미지 저장 또는 참조
    API->>DB: 고객, 설문, 분석, 추천 결과 저장
    API-->>View: 추천 결과 payload
    View-->>Customer: 추천 결과 / 상담 요청 화면 렌더링
```

- 주요 파일
  - `app/front_views.py`
  - `app/api/v1/services_django.py`
  - `app/models_django.py`
  - `app/services/storage_service.py`

### 2. 디자이너 / 매장 운영 흐름

```mermaid
sequenceDiagram
    actor Staff as 디자이너 / 매장 관리자
    participant UI as admin templates
    participant API as admin_views + admin_services
    participant Cache as Redis / runtime_cache
    participant DB as Supabase PostgreSQL

    Staff->>UI: 대시보드 / 고객상세 / 리포트 진입
    UI->>API: 고객 목록, 상세, 리포트 API 호출
    API->>Cache: 캐시 조회
    alt cache hit
        Cache-->>API: 캐시 payload 반환
    else cache miss
        API->>DB: 집계 / 조회
        API->>Cache: 결과 캐시 저장
    end
    API-->>UI: 고객/리포트 데이터 반환
    UI-->>Staff: 대시보드 렌더링
```

- 주요 파일
  - `app/api/v1/admin_views.py`
  - `app/api/v1/admin_services.py`
  - `app/services/runtime_cache.py`
  - `templates/admin/index.html`
  - `templates/admin/customer_detail.html`

### 3. 디자이너 챗봇 흐름

```mermaid
sequenceDiagram
    actor Designer as 디자이너
    participant UI as 챗봇 UI
    participant Service as chatbot/service.py
    participant RAG as chatbot/rag.py
    participant Chroma as chromadb_chatbot
    participant LLM as OpenAI Responses API

    Designer->>UI: 질문 입력
    UI->>Service: 메시지 전송
    Service->>Service: 인젝션 / 역할 변경 시도 검사
    alt 공격 패턴 감지
        Service-->>UI: 차단 응답 반환
    else 정상 질문
        Service->>RAG: 검색 컨텍스트 생성
        RAG->>Chroma: 유사도 검색
        Chroma-->>RAG: 참고 문서 조각 반환
        RAG-->>Service: 안전 필터링된 source_context 반환
        Service->>LLM: system prompt + untrusted blocks 전달
        LLM-->>Service: 응답 반환
        Service->>Service: 세션 이름/내부지침 누출 후검사
        Service-->>UI: 최종 응답 반환
    end
```

- 주요 파일
  - `app/services/chatbot/service.py`
  - `app/services/chatbot/rag.py`
  - `templates/components/chatbot.html`
  - `app/tests/test_chatbot_service.py`

### 4. 최신 트렌드 갱신 흐름

```mermaid
sequenceDiagram
    participant Scheduler as apps.py / trend_scheduler.py
    participant Refresh as trend_refresh.py
    participant Pipeline as trend_pipeline/*
    participant Chroma as chromadb_trends
    participant UI as customer/trend + admin report

    Scheduler->>Refresh: 정기 실행 또는 수동 실행
    Refresh->>Pipeline: crawl / refine / llm_refine / vectorize / rebuild_ncs
    Pipeline->>Chroma: 최신 트렌드 컬렉션 재생성
    Chroma-->>UI: 고객 트렌드 피드 / 매장 리포트에서 조회
```

- 주요 파일
  - `app/apps.py`
  - `app/services/trend_scheduler.py`
  - `app/services/trend_refresh.py`
  - `app/trend_pipeline/vectorize_chromadb.py`
  - `templates/customer/trend.html`

## 저장소와 역할

| 저장소 | 역할 | 대표 경로 |
| --- | --- | --- |
| Supabase PostgreSQL | 고객, 디자이너, 설문, 추천, 상담, 리포트 집계 | `mirrai_project/settings.py`, `app/models_django.py` |
| Redis | 세션, 파트너 리포트 캐시, 목록 캐시 | `mirrai_project/settings.py`, `app/services/runtime_cache.py` |
| Supabase Storage / Local Media | 캡처 이미지 및 미디어 참조 | `app/services/storage_service.py` |
| ChromaDB Trends / NCS | 최신 트렌드, 리포트, 일부 추천 보조 | `data/rag/stores/chromadb_trends`, `data/rag/stores/chromadb_ncs` |
| ChromaDB Chatbot | 디자이너 챗봇 검색 인덱스 | `data/rag/stores/chromadb_chatbot` |

## 함께 볼 문서

- 시연 시나리오: [`../demo_video_scenario.md`](../demo_video_scenario.md)
- 프롬프트 인젝션 방어: [`../prompt_injection_defense/README.md`](../prompt_injection_defense/README.md)
