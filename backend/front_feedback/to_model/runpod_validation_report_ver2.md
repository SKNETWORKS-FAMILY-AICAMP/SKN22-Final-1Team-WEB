# RunPod 검증 보고서 `ver2`

## 목적

PM 확인 후 RunPod 수정 반영 여부를 다시 점검하기 위해,
동일한 endpoint 주소로 `health_check`, `EP1 직접 생성`, `EP2 추천 기반 생성`을 재검증한 결과를 정리합니다.

대상 endpoint:
- `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`

## 결론 요약

- `health_check`는 정상입니다.
- 이전에 확인된 `EP1 NameError`는 더 이상 재현되지 않았습니다.
- 다만 생성 파이프라인에는 새로운 런타임 오류가 남아 있습니다.
- 현재 핵심 오류는 `_refine_with_sam2()` 반환값 처리 과정의
  `ValueError: too many values to unpack (expected 2)` 입니다.

즉, 헬스체크는 해결되었지만 생성 경로는 아직 정상 완료 상태가 아닙니다.

## 검증 결과

### 1. EP0 `health_check`

요청:
```json
{
  "input": {
    "action": "health_check"
  }
}
```

결과:
- 정상
- `status: COMPLETED`
- `output.status: ok`
- CUDA 정보 정상 반환
- 확인된 GPU: `NVIDIA GeForce RTX 5090`
- `build_tag: dev`

정리:
- 이전 health check 계약 불일치는 해소된 것으로 판단됩니다.

### 2. EP1 직접 생성

테스트 조건:
- 공개 이미지 URL 사용
- `hairstyle_text`: `wolf cut, layered bangs`
- `color_text`: `ash brown`
- `top_k=1`
- `return_base64=false`

결과:
- 실패
- 최종 `status: FAILED`
- 오류:
  - `ValueError: too many values to unpack (expected 2)`

traceback 핵심:
- `/app/pipeline_sd_inpainting.py`
- `hair_mask, mask_source = self._refine_with_sam2(...)`

정리:
- 이전 `NameError: effective_hairstyle_text is not defined`는 재현되지 않았습니다.
- 하지만 생성 파이프라인 내부에서 다른 런타임 오류가 발생하고 있습니다.

### 3. EP2 추천 기반 생성

테스트 조건:
- 공개 이미지 URL 사용
- `face_ratios` 제공
- `preference_text` 제공
- `age=28`
- `top_k=1`
- `return_base64=false`

결과:
- `status: COMPLETED`
- `recommendations`는 정상 반환
- `results`는 빈 배열
- 추천 항목 내부에 다음 오류가 함께 기록됨:
  - `generation_error: ValueError: too many values to unpack (expected 2)`

정리:
- 추천 로직 자체는 동작합니다.
- 하지만 실제 생성 단계가 실패하여 최종 이미지 결과는 비어 있습니다.

## 장애 수준 평가

### EP1
- 수준: `높음`
- 이유:
  - 직접 생성 기능이 현재 정상 완료되지 않습니다.
  - 사용자가 스타일/색상을 직접 지정하는 경로가 있다면 바로 실패합니다.

### EP2
- 수준: `중간 이상`
- 이유:
  - 추천 metadata는 정상 반환되지만, 실제 생성 이미지가 없습니다.
  - 서비스의 핵심 가치가 `추천 + 시뮬레이션 이미지`라면 실사용 품질에 의미 있는 결손입니다.

### 전체 서비스 관점
- 백엔드와 RunPod의 네트워크 연결 문제는 아닙니다.
- 인증이나 endpoint 주소 문제도 아닙니다.
- 현재 문제는 배포된 생성 runtime 내부 동작 문제로 보는 것이 타당합니다.

## 이번 재검증으로 달라진 점

- 해결된 점:
  - `health_check` 정상화
  - 이전 `EP1 NameError` 미재현

- 아직 남은 점:
  - 생성 경로 공통 `ValueError`
  - EP1 직접 생성 실패
  - EP2 생성 결과 누락

## 백엔드 관점 판단

- `#135`는 아직 `in review`로 올리기 어렵습니다.
- 현재 상태는 `in progress` 유지가 적절합니다.
- 이유는 헬스체크만이 아니라 실제 생성 기능까지 정상 동작해야 하기 때문입니다.

## 모델팀 확인 요청

- `_refine_with_sam2()`의 현재 반환값 개수와 호출부 unpack 개수가 일치하는지 확인 부탁드립니다.
- 로컬에서는 정상인데 RunPod 배포본에서만 문제가 난다면, 배포된 이미지 버전과 로컬 실행 버전 차이를 점검 부탁드립니다.
- EP2에서 `recommendations`는 정상인데 `results`가 비는 원인이 동일 생성 오류 전파 때문인지 확인 부탁드립니다.
