# RunPod EP1 상세 보고서 `ver2`

## 대상

- Endpoint: `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`
- 경로: EP1 직접 생성

## 테스트 목적

- PM 확인 후 수정된 배포본에서 EP1 직접 생성이 정상 동작하는지 재검증
- 이전 `NameError`가 해결되었는지 확인
- 새로 남아 있는 런타임 오류가 있는지 확인

## 테스트 조건

- `image`: 공개 이미지 URL
- `hairstyle_text`: `wolf cut, layered bangs`
- `color_text`: `ash brown`
- `top_k`: `1`
- `return_base64`: `false`
- `return_intermediates`: `false`
- `mask_debug_only`: `false`
- `bg_fill_mode`: `cv2`

## 요청 본문

```json
{
  "input": {
    "image": "https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg",
    "hairstyle_text": "wolf cut, layered bangs",
    "color_text": "ash brown",
    "top_k": 1,
    "return_base64": false,
    "return_intermediates": false,
    "mask_debug_only": false,
    "bg_fill_mode": "cv2"
  }
}
```

## 응답 요약

최종 결과:
- HTTP `200`
- `status: FAILED`
- `executionTime: 11467`
- `build_tag: dev`

오류:
- `ValueError: too many values to unpack (expected 2)`

traceback 핵심:
```text
File "/app/pipeline_sd_inpainting.py", line 449, in run
    hair_mask, mask_source = self._refine_with_sam2(...)
ValueError: too many values to unpack (expected 2)
```

## 확인된 사실

- RunPod endpoint 주소, 인증, 요청 형식 자체는 정상입니다.
- `health_check`는 별도로 정상 동작합니다.
- 이전에 보였던 `NameError: effective_hairstyle_text is not defined`는 이번에는 재현되지 않았습니다.
- 현재 EP1 실패 원인은 생성 파이프라인 내부의 새로운 런타임 오류입니다.

## 원인 해석

현재 증상으로 보면 아래 가능성이 큽니다.

- `_refine_with_sam2()`의 반환값 개수가 변경되었는데 호출부 unpack 코드가 갱신되지 않았을 가능성
- 로컬 작업본과 RunPod 배포본 사이에 함수 시그니처 차이가 남아 있을 가능성
- 특정 분기에서만 반환값 구조가 달라지는 경우가 있을 가능성

즉, 현재 문제는 입력 형식 오류나 백엔드 연동 오류가 아니라
배포된 생성 runtime 내부 구현 차이로 보는 것이 타당합니다.

## 장애 수준 평가

- 수준: `높음`

이유:
- EP1은 직접 생성의 핵심 경로입니다.
- 현재는 정상 요청에도 내부 예외로 실패합니다.
- 실서비스에서 EP1을 노출하는 화면이 있다면 기능 자체가 unusable 상태입니다.

## 실서비스 영향

- 사용자가 스타일/색상을 직접 지정하는 생성 기능은 현재 바로 실패합니다.
- 헬스체크가 정상이더라도 실제 생성 기능은 정상이라고 볼 수 없습니다.
- 운영 관점에서는 부분 장애가 아니라, EP1 기능 단위로는 명확한 장애입니다.

## 백엔드 관점 결론

- 백엔드와 RunPod 연결은 정상입니다.
- EP1 실패 원인은 model runtime 내부에 있습니다.
- `#135`를 완료로 올리기에는 아직 이 경로가 막혀 있습니다.

## 모델팀 확인 요청

- `_refine_with_sam2()`의 반환값 구조를 확인 부탁드립니다.
- `/app/pipeline_sd_inpainting.py`의 해당 unpack 코드가 현재 배포본과 최신 작업본에서 동일한지 확인 부탁드립니다.
- 동일 payload로 로컬과 RunPod에서 결과가 달라지는지 재현 확인 부탁드립니다.
