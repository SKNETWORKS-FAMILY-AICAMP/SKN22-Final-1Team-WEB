# 모델팀 작업 참고 정리

## 문서 목적

이 문서는 모델팀이 백엔드와 연동하거나 RunPod/AI service 결과를 맞출 때
직접 도움이 되는 포인트만 따로 정리한 문서입니다.

핵심 질문:
- 어떤 입력 fixture로 contract test를 돌릴 것인가
- 언제 pass / fail로 판정할 것인가
- smoke test는 어느 환경에서 어떤 순서로 돌릴 것인가
- canary는 무엇을 baseline과 비교할 것인가
- schema diff는 무엇을 fail로 볼 것인가

## 현재 핵심 구조

현재 백엔드는 모델을 직접 호출하지 않고
`app/services/ai_facade.py`를 통해 아래 provider 중 하나를 사용합니다.

- `local`
- `service`
- `runpod`

현재 기준 smoke test 결과는 아래 보고서를 참고합니다.

- `front_feedback/to_model/runpod_validation_report_ver3.md`
- `front_feedback/to_model/runpod_ep1_detailed_report_ver3.md`
- `front_feedback/to_model/runpod_ep2_detailed_report_ver3.md`

현재 해석:
- `health_check` 정상
- `EP1` 정상
- `EP2` 정상

## 핵심 응답 계약 요약

### EP0

```json
{
  "status": "ok",
  "cuda": {
    "available": true,
    "device": "..."
  }
}
```

### EP1

```json
{
  "results": [
    {
      "rank": 0,
      "seed": 42,
      "clip_score": 0.31,
      "mask_used": "sam2"
    }
  ],
  "elapsed_seconds": 12.3
}
```

### EP2

```json
{
  "results": [...],
  "recommendations": [...],
  "elapsed_seconds": 58.7
}
```

핵심 해석:
- `results`가 가장 중요
- `recommendations`는 EP2에서 권장
- `build_tag`는 배포 추적용으로 매우 유용

## 운영 및 배포 기준

- `results empty`는 partial 또는 실패
- timeout 기준은 backend read timeout `120초`
- health check만 성공해도 충분하지 않음
- EP0 / EP1 / EP2가 함께 안정적이어야 배포본을 정상으로 봄
- `build_tag` 기반으로 버전 추적이 가능해야 함

## CI/CD 및 자동 판정 명세

### 1. contract test 입력 fixture 정의

현재 코드상 시작점:
- `app/tests/test_ai_facade_runpod.py`

권장 최소 fixture:

#### EP0 health_check fixture

```json
{
  "input": {
    "action": "health_check"
  }
}
```

#### EP1 최소 입력 fixture

```json
{
  "input": {
    "image": "<fixture image or stable URL>",
    "hairstyle_text": "wolf cut, layered bangs",
    "color_text": "ash brown",
    "top_k": 1,
    "return_base64": false
  }
}
```

#### EP2 최소 입력 fixture

```json
{
  "input": {
    "image": "<fixture image or stable URL>",
    "face_ratios": {
      "cheekbone_to_height": 0.72,
      "jaw_to_height": 0.60,
      "temple_to_height": 0.70,
      "jaw_to_cheekbone": 0.83
    },
    "preference_text": "자연스러운 웨이브 미디엄 길이, 따뜻한 톤",
    "age": 28,
    "top_k": 1,
    "return_base64": false
  }
}
```

### 2. pass / fail 판정 기준

#### 공통 pass 기준
- HTTP 200 또는 RunPod `COMPLETED`
- JSON parse 성공
- body 구조 파싱 가능

#### EP0 pass 기준
- `status` 존재
- `cuda.available` 존재

#### EP1 / EP2 pass 기준
- `results` 필드 존재
- `results`가 빈 배열이 아님
- `elapsed_seconds`가 있으면 수치형으로 파싱 가능

#### 즉시 fail 기준
- HTTP 실패
- JSON parse 실패
- timeout
- `results` 필드 누락
- `results=[]`

#### 경고(warning) 기준
- `build_tag` 없음
- `clip_score` 없음
- `mask_used` 없음

### 3. smoke test 실행 환경 정의

권장 환경:

#### 1단계: local mock
- 파싱 로직과 facade 분기 검증

#### 2단계: staging RunPod 또는 별도 검증 endpoint
- 실제 handler 동작 검증

#### 3단계: production-like endpoint
- 운영 배포본 최종 확인

권장 게이트:
- local mock 통과
- staging RunPod smoke test 통과
- production-like EP0 / EP1 / EP2 통과 후 승격

### 4. canary baseline 비교 기준

권장 baseline:
- 직전 안정판 `build_tag`

권장 비교 지표:
- timeout 증가율
- `results empty` 증가율
- fallback 증가율
- `generation_error` 비율

권장 rollback trigger 예시:
- `results empty` 비율 유의미 증가
- timeout 비율 유의미 증가
- EP1 또는 EP2 hard failure 재현

### 5. schema diff 판정 규칙

#### pass
- additive change
- 선택 필드 추가
- 부가 메타 추가

#### warning
- optional field removal
- 권장 필드 제거

#### fail
- required field removal
- key rename
- type change
- `results` item 핵심 구조 변경

## 자동 감지 지표

운영 중 자동 감지 대상으로 볼 만한 핵심 지표:
- `results empty` 비율
- timeout 비율
- fallback 발생 비율
- `generation_error` 비율
- EP1/EP2 평균 응답 시간

## 참고 파일

- `app/services/ai_facade.py`
- `app/tests/test_ai_facade_runpod.py`
- `app/api/v1/services_django.py`

