# RunPod EP1 상세 보고서 `ver1`

## 대상

- Endpoint: `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`
- 경로: EP1 직접 지정 생성

## 테스트 목적

- `health_check` 정상화 이후, 직접 생성 경로가 실제로 동작하는지 확인
- 입력 형식 문제인지, 배포된 런타임 문제인지 구분

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
    "image": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama.jpg",
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

1차 응답:
- `status: IN_PROGRESS`
- 작업이 실제 worker에 정상 전달됨

후속 status 조회:
- 최종 `status: FAILED`
- `executionTime: 197803`
- error:
  - `NameError: name 'effective_hairstyle_text' is not defined`

## 확인된 사실

- RunPod endpoint 주소, 인증, 요청 형식 자체는 정상입니다.
- worker는 실제로 작업을 받았고, 곧바로 입력 검증 단계에서 막힌 것이 아닙니다.
- 실패 지점은 배포된 런타임 코드 내부입니다.
- 즉, 현재 증상은 backend 연동 문제가 아니라 배포본 내부 예외로 보는 것이 타당합니다.

## 원인 해석

현재 확인 가능한 수준의 해석:
- `handler_sd.py` 또는 `pipeline_sd_inpainting.py` 내부에서
  `effective_hairstyle_text` 변수가 초기화되지 않았거나
  특정 분기에서 정의되지 않은 채 참조되고 있습니다.

이 문제는 보통 아래 경우 중 하나입니다.
- 최근 리팩토링 후 변수명 변경 누락
- 특정 입력 조합에서만 타는 분기 미정의
- 로컬 실행본과 RunPod 배포본 버전 차이

## 장애 수준 평가

판단: **높음**

이유:
- EP1의 핵심 기능은 직접 생성입니다.
- 현재는 정상 요청이어도 런타임 예외로 실패합니다.
- 사용자가 직접 스타일/색상을 지정해 생성하는 흐름은 실질적으로 사용 불가 상태입니다.

서비스 영향:
- EP1을 사용하는 화면/기능이 있다면 해당 기능은 사실상 장애 상태입니다.
- health check가 정상이어도 실제 생성이 안 되므로, 운영 관점에서는 부분 장애가 아니라
  **EP1 기능 자체의 명확한 장애**로 봐야 합니다.

## 백엔드 관점 결론

- backend -> RunPod 연결은 정상
- health check도 정상
- 그러나 EP1은 현재 배포본 기준으로 실사용 가능 상태가 아님

## 모델팀 확인 요청

- `effective_hairstyle_text`가 정의되지 않는 분기 확인
- 로컬에서는 재현되지 않는다면, 현재 RunPod 배포본과 로컬 실행본 버전 차이 확인
- 수정 후 동일 payload로 재검증 필요
