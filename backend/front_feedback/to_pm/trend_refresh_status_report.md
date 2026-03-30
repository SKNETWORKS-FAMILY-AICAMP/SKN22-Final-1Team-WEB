# 트렌드 갱신 파이프라인 보강 보고서

## 목적

- 기존 trend refresh 골격 위에 운영용 보강을 추가했습니다.
- 이번 범위는 RAG 챗봇이 아니라, backend 운영용 `crawl -> refine -> DB 반영` 흐름 안정화입니다.

## 이번에 보강한 핵심

### 1. scheduler 중복 실행 방지

- PostgreSQL 환경에서 advisory lock을 사용하도록 보강했습니다.
- 같은 스케줄 슬롯에서는 한 인스턴스만 실제 refresh를 실행합니다.
- lock을 얻지 못한 인스턴스는 `skipped` 로그만 남기고 실행을 건너뜁니다.

### 2. backend DB 반영 연결

- `rebuild_styles` 단계에서 trend seed 데이터를 기존 `Style` 테이블에 동기화하도록 연결했습니다.
- 새 모델 추가 없이 기존 DB 구조 안에서 처리합니다.
- 생성/수정 건수는 step 결과에 함께 남깁니다.

### 3. 고객-facing trend fallback 반영

- 최근 선택 데이터가 부족할 때, 하드코딩된 fallback만 쓰지 않고
  현재 sync된 trend seed 스타일을 우선 노출하도록 연결했습니다.
- 즉, 주기적 갱신 결과가 실제 고객 trend 카드 방향에 반영됩니다.

### 4. 기본 scheduler step 보정

- 기본 실행 step에 `rebuild_styles`를 포함시켰습니다.
- 금요일 오전 8시 정기 실행 시 DB 반영 단계가 빠지지 않도록 맞췄습니다.

## 유지한 원칙

- 새 아키텍처를 따로 만들지 않았습니다.
- 기존 `refresh_trends` entrypoint와 `run_trend_scheduler` 흐름을 유지했습니다.
- 새 DB 모델 / versioning / history 구조는 추가하지 않았습니다.

## 검증

- `manage.py check` 통과
- `app.tests.test_trend_refresh_service` 통과
- `app.tests.test_trend_scheduler_service` 통과
- `app.tests.test_client_age_features` 통과

## 현재 판단

- 이전에 미흡했던 `단일 인스턴스 보장`과 `backend DB 반영 연결`은 이번 보강으로 메웠습니다.
- 현재 상태는 upstream PR 검토를 올릴 수 있는 수준으로 판단합니다.
