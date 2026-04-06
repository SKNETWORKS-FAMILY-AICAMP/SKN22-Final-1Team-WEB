# RunPod Direct B안 개편 보고서 0406 ver_1

## 목적

- A안의 안전한 기준선을 유지한 상태에서, backend가 RunPod direct 응답을 더 적극적으로 활용하도록 개편했다.
- 이번 B안은 독립 얼굴 분석 API를 새로 만들지 않고, 추천 기반 RunPod 응답에 포함된 메타를 backend 추천 결과에 보존하는 방향이다.

## A안과의 차이

- A안
  - RunPod endpoint/env 해석 정리
  - `MIRRAI_AI_PROVIDER=service`라도 service URL이 비어 있으면 runpod fallback
  - health check와 추천 이미지 생성만 보수적으로 활성화
  - 독립 얼굴 분석은 기존 local/internal fallback 유지

- B안
  - AI팀 `handler_sd.py` / `README.md` 기준 RunPod 응답 메타를 backend가 실제로 읽도록 확장
  - `results[]` 외에 `recommendations[]`, `rag_context`, `build_tag`, `runpod` 메타를 reasoning snapshot에 보존
  - backend 추천 카드가 RunPod 추천 근거와 얼굴 메타를 같이 들고 있게 정리

## 반영 내용

### 1. RunPod preference payload를 direct 계약에 맞게 보정

- `app/services/ai_facade.py`
- backend의 canonical 선호값을 RunPod README 기준 preference 구조로 다시 매핑했다.
- 예시:
  - `chic -> trendy`
  - `elegant -> classic`
  - `waved -> wavy`
  - `mid -> medium`

### 2. RunPod 추천 응답 메타를 reasoning snapshot에 적재

- `app/services/ai_facade.py`
- RunPod 응답에서 아래 값을 추출해 각 recommendation item의 `reasoning_snapshot.runpod`에 저장한다.
  - `clip_score`
  - `mask_used`
  - `elapsed_seconds`
  - `recommended_style`
  - `build_tag`
  - `runpod`
  - `rag_context_excerpt`
  - `recommendations[]`에서 찾은 `face_shape_detected`
  - `recommendations[]`에서 찾은 `golden_ratio_score`
  - `recommendations[]`에서 찾은 `face_shapes`

### 3. RunPod 추천 description을 backend 설명값으로 재사용

- `app/services/ai_facade.py`
- RunPod recommendation description이 있으면
  - `llm_explanation`
  - `style_description`
  fallback으로 넣는다.

### 4. 회귀 테스트 추가

- `app/tests/test_ai_facade.py`
- RunPod recommendation 응답을 mock으로 주입해 다음을 검증한다.
  - `simulation_image_url` data URL 변환
  - `build_tag` 보존
  - `face_shape_detected` 보존
  - `golden_ratio_score` 보존
  - `rag_context_excerpt` 보존

## 현재 의미

- backend는 이제 RunPod direct를 단순 이미지 생성 경로로만 쓰지 않는다.
- 추천 결과의 근거 메타와 얼굴 관련 메타 일부를 recommendation snapshot에 함께 남길 수 있다.
- 따라서 이후 고객 상세, 추천 카드, 관리자 검토 로직에서 RunPod 결과를 더 풍부하게 활용할 수 있다.

## 여전히 남는 한계

- 독립 얼굴 분석 전용 RunPod action은 여전히 없다.
- 따라서 `simulate_face_analysis()` 자체는 internal/local fallback 성격을 유지한다.
- 이번 B안은 RunPod 추천 응답 안의 얼굴 메타를 backend가 더 잘 활용하도록 만든 것이지, 독립 얼굴 분석 API를 대체한 것은 아니다.

## 결론

- A안은 안전한 기준선으로 유지한다.
- B안은 RunPod direct를 실제 운영 메타까지 반영하는 방향으로 backend를 한 단계 더 direct-friendly 하게 만든다.
- 독립 얼굴 분석까지 완전히 RunPod direct로 옮기려면, 추후 AI팀 handler에 별도 action이 추가되거나 backend가 분석 단계를 재설계해야 한다.
