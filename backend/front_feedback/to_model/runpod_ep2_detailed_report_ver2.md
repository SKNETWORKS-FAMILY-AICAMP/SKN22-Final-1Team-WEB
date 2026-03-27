# RunPod EP2 상세 보고서 `ver2`

## 대상

- Endpoint: `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`
- 경로: EP2 추천 기반 생성

## 테스트 목적

- PM 확인 후 수정된 배포본에서 EP2 추천 기반 생성이 정상 동작하는지 재검증
- 추천 metadata와 실제 생성 결과가 모두 정상인지 확인
- 생성 결과 누락이 여전히 남아 있는지 확인

## 테스트 조건

- `image`: 공개 이미지 URL
- `face_ratios`:
  - `cheekbone_to_height`: `0.72`
  - `jaw_to_height`: `0.60`
  - `temple_to_height`: `0.70`
  - `jaw_to_cheekbone`: `0.83`
- `preference_text`: `자연스러운 웨이브 미디엄 길이, 따뜻한 톤`
- `age`: `28`
- `top_k`: `1`
- `return_base64`: `false`

## 요청 본문

```json
{
  "input": {
    "image": "https://upload.wikimedia.org/wikipedia/commons/8/8d/President_Barack_Obama.jpg",
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

## 응답 요약

최종 결과:
- HTTP `200`
- `status: COMPLETED`
- `executionTime: 12070`
- `build_tag: dev`

정상 반환된 항목:
- `recommendations`
- 추천 스타일 metadata

비정상 항목:
- `results: []`
- 추천 항목 내부 `generation_error` 존재

확인된 오류:
- `generation_error: ValueError: too many values to unpack (expected 2)`

## 확인된 사실

- 추천 로직은 동작합니다.
- 스타일 추천 metadata는 실제로 반환됩니다.
- 그러나 생성 단계가 실패하여 최종 시뮬레이션 이미지는 만들어지지 않습니다.
- EP1과 같은 오류가 EP2 생성 단계에도 영향을 주는 것으로 보입니다.

## 원인 해석

현재 증상으로 볼 때 EP2는 다음처럼 해석하는 것이 타당합니다.

- 추천 단계: 정상
- 생성 단계: 실패
- 실패 원인: EP1과 동일한 생성 runtime 오류 전파 가능성 높음

즉 EP2 전체가 완전히 죽은 것은 아니지만,
사용자가 기대하는 최종 결과인 생성 이미지까지는 도달하지 못하고 있습니다.

## 장애 수준 평가

- 수준: `중간 이상`

이유:
- 추천 metadata만 보면 일부 기능은 살아 있습니다.
- 하지만 실제 서비스의 핵심 결과물은 생성 이미지입니다.
- `results`가 비어 있으면 사용자 입장에서는 추천만 받고 결과 이미지를 보지 못합니다.
- 따라서 단순 cosmetic 이슈가 아니라, 서비스 체감 품질에 직접 영향을 주는 결손입니다.

## 실서비스 영향

- 추천 리스트나 추천 설명은 표시할 수 있습니다.
- 그러나 시뮬레이션 이미지를 함께 보여줘야 하는 화면에서는 기능 가치가 크게 떨어집니다.
- 추천 결과를 카드로만 보여주는 임시 fallback은 가능할 수 있어도, 본래 기대 기능은 충족하지 못합니다.

## 백엔드 관점 결론

- 백엔드와 RunPod 연결은 정상입니다.
- EP2의 추천 단계는 정상입니다.
- 다만 생성 결과가 비어 있으므로 EP2를 정상 완료로 볼 수 없습니다.
- `#135`는 아직 계속 `in progress`가 적절합니다.

## 모델팀 확인 요청

- EP2 내부에서 추천 후 생성 단계로 넘어가는 흐름이 실제로 실행되는지 확인 부탁드립니다.
- `generation_error`가 EP1과 동일한 `_refine_with_sam2()` 오류 전파인지 확인 부탁드립니다.
- `recommendations`는 정상인데 `results`가 비는 현재 응답을 README 기준 정상 응답으로 볼 수 있는지 확인 부탁드립니다.
