# 백엔드 메커니즘 개요

## 문서 목적

이 문서는 현재 MirrAI 백엔드가 어떤 흐름으로 동작하는지,
그리고 그 흐름을 운영 단계에서 어떤 규칙으로 통제하고
구현 명세로 어떻게 연결해야 하는지를 함께 설명하는 문서입니다.

핵심 질문:
- validator는 어디에 들어가야 하는가
- 상태 전이는 어떤 표로 고정해야 하는가
- observability 이벤트는 어떤 필드로 남겨야 하는가
- 자동 복구는 언제 실행하고, 언제 alert만 낼 것인가
- SLA / SLO는 무엇을 시작점과 종료점으로 측정해야 하는가

## 현재 핵심 구조

현재 백엔드는 크게 아래 4개 축으로 움직입니다.

1. 고객 입력 처리
- 고객 기본정보 입력
- 설문 입력
- 사진 업로드

2. 분석 및 추천 생성
- 얼굴 분석
- 추천 Top-5 생성
- 추천 이력 저장

3. 관리자 상담 흐름
- 관리자 계정 생성/로그인
- 고객 리스트/상세/추천 확인
- 상담 요청, 상담 메모, 상담 종료

4. 외부 AI 연동
- 로컬 fallback
- 내부 AI service
- RunPod

핵심 흐름:
- 업로드 검증
- `CaptureRecord` 생성
- `run_mirrai_analysis_pipeline()`
- `FaceAnalysis` 생성
- 추천 batch 저장
- `CaptureRecord.status = DONE`

## 상태 전이

현재 `CaptureRecord` 기준 핵심 상태는 아래입니다.

- `PENDING`
- `PROCESSING`
- `DONE`
- `FAILED`
- `NEEDS_RETAKE`

운영 해석 기준:
- `DONE`
  - 상태 문자열만이 아니라 `FaceAnalysis` 존재 + 추천 batch 존재까지 같이 확인해야 함
- `FAILED`
  - 파이프라인 실패 또는 정합성 이상 의심
- `NEEDS_RETAKE`
  - 사용자 입력 품질 문제

## 운영 규칙

현재 운영 기준으로 가장 중요한 규칙은 아래입니다.

1. `DONE` 최소 조건
- `CaptureRecord.status = DONE`
- 대응하는 `FaceAnalysis` 존재
- 대응하는 추천 batch 존재

2. `DONE`인데 추천 없음
- 정상 완료로 보지 않음
- 운영상 invalid completion으로 해석

3. `PROCESSING`
- recommendations API만 보고 실패 확정 금지
- capture status와 함께 해석

4. race condition 리스크
- 동일 `Client`의 짧은 시간 내 다중 capture 업로드 시 latest 기준 연결이 어긋날 수 있음

## 구현 명세 연결

### 1. validator 삽입 지점

가장 자연스러운 삽입 지점은
`app/api/v1/services_django.py`의 `run_mirrai_analysis_pipeline()` 내부입니다.

현재 코드 흐름:
1. `PROCESSING` 전환
2. `FaceAnalysis.objects.create(...)`
3. `persist_generated_batch(...)`
4. `record.status = "DONE"`

권장 validator 위치:
- `persist_generated_batch(...)` 직후
- `record.status = "DONE"` 직전

권장 검증 항목:
- `FaceAnalysis`가 실제 생성되었는지
- 추천 batch row가 실제로 1개 이상 저장되었는지
- 저장된 추천 batch가 현재 흐름과 논리적으로 연결 가능한지

검증 실패 시 권장 처리:
- `DONE`으로 전이하지 않음
- `CaptureRecord.status = FAILED`
- `error_note`에 정합성 검증 실패 메시지 기록

### 2. 상태 전이 표

#### 허용 전이

- `PENDING -> PROCESSING`
  - trigger: `run_mirrai_analysis_pipeline()` 시작
  - guard: 업로드 검증 통과, 현재 상태가 `PENDING`

- `PROCESSING -> DONE`
  - trigger: 얼굴 분석 + 추천 batch 저장 완료
  - guard: `FaceAnalysis` 존재, 추천 batch 존재, validator 통과

- `PROCESSING -> FAILED`
  - trigger: 파이프라인 예외 또는 정합성 validator 실패

- `PENDING -> NEEDS_RETAKE`
  - trigger: 업로드 검증 실패

#### 금지 전이

- `FAILED -> DONE`
  - 자동 전이 금지
- `DONE -> PROCESSING`
  - 금지

### 3. observability 이벤트 스키마

권장 이벤트명:
- `capture_uploaded`
- `pipeline_started`
- `face_analysis_saved`
- `recommendation_batch_saved`
- `pipeline_failed`
- `pipeline_completed`

공통 필드 권장안:
- `event_name`
- `request_id`
- `trace_id`
- `client_id`
- `capture_record_id`
- `analysis_id`
- `batch_id`
- `provider`
- `status`
- `duration_ms`
- `build_tag`
- `error_type`
- `error_message`

현재 코드 기준 사실:
- `request_id`, `trace_id`는 아직 전반에 일관되게 반영돼 있지 않음
- `record_id` 중심 추적은 가능

### 4. 자동 복구 실행 조건

현재 상태:
- 자동 복구 없음
- 실패/이상 상태는 운영 해석과 수동 조치에 의존

권장 방향:
- `DONE`인데 recommendation 없음
  - 즉시 alert
  - 운영상 정상 완료로 간주하지 않음
- 초기 단계에서는 자동 즉시 재처리보다 alert + 재처리 후보 등록이 더 안전

### 5. SLA / SLO 측정 정의

#### 처리 시간 측정

시작 시점:
- `CaptureRecord`가 `PROCESSING`으로 전환되는 시점

종료 시점:
- `CaptureRecord.status = DONE` 저장 시점

#### 성공률 정의

분모:
- `PROCESSING`에 진입한 capture 수

분자:
- validator 기준을 만족하고 `DONE`까지 도달한 capture 수

제외 대상:
- 업로드 검증 단계에서 바로 `NEEDS_RETAKE`가 된 건

## 모니터링 기준

운영에서 우선 추적할 지표:
- `FAILED` 비율
- `NEEDS_RETAKE` 비율
- `PROCESSING -> DONE` p95 시간
- `DONE인데 추천 없음` 건수

## 인증 구조

현재 인증은 `Bearer` 토큰 기준입니다.

- 고객
  - access token
  - refresh token
- 관리자
  - access token
  - refresh token

현재 반영된 방향:
- refresh token 지원
- refresh 기준 `24시간`

## AI 연동 구조

백엔드가 모델 쪽과 연결되는 핵심 파일:

- `app/services/ai_facade.py`

현재 provider 분기:
- `local`
- `service`
- `runpod`

## 참고 파일

- `app/models_django.py`
- `app/api/v1/services_django.py`
- `app/services/ai_facade.py`

