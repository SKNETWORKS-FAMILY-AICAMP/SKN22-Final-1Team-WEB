# RunPod EP2 상세 보고서 `ver3`

## 대상

- Endpoint: `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`
- 경로: EP2 추천 기반 생성

## 테스트 목적

- 수정된 배포본에서 EP2 추천 기반 생성이 정상 동작하는지 재검증
- 추천 metadata와 실제 생성 결과가 함께 반환되는지 확인
- 이전 partial success 상태가 해소되었는지 확인

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
- `recommendations_count: 1`
- `results_count: 1`
- `elapsed_seconds: 122.8`
- `build_tag: dev`
- 오류 없음

추천 결과 예시:
- `style_id: soft-wolf-cut`
- `style_name: Soft Wolf Cut`
- `score: 0.9286`
- `face_shape_detected: oval`

생성 결과 특징:
- 첫 번째 결과 항목에 아래 키 확인
  - `clip_score`
  - `mask_refine_mode`
  - `mask_used`
  - `rank`
  - `recommended_style`
  - `seed`
- 이번 요청은 `return_base64=false`라 `image_base64`는 포함되지 않음

## 확인된 사실

- 추천 단계는 정상 동작합니다.
- 생성 단계도 이번에는 정상 완료되었습니다.
- 이전에 확인됐던 `results=[]` 문제는 재현되지 않았습니다.
- 추천 metadata와 생성 결과가 함께 반환되었습니다.

## 원인 해석

이번 결과 기준으로 보면,
이전 EP2 문제는 생성 runtime 수정 이후 해소된 것으로 보는 것이 타당합니다.

즉 현재 EP2는
- 추천 성공
- 생성 성공
- 결과 반환 성공
상태입니다.

## 장애 수준 평가

- 수준: `해소`

이유:
- 이전에는 추천 metadata만 오고 생성 결과가 비어 있었지만,
  이번에는 생성 결과까지 정상적으로 반환되었습니다.
- 현재 기준으로는 실서비스 blocker 수준의 증상이 보이지 않습니다.

## 실서비스 영향

- 추천과 생성 이미지를 함께 제공하는 흐름이 현재는 가능하다고 판단됩니다.
- 다만 이번 테스트는 `return_base64=false` 기준이므로, 실제 이미지 본문이 필요한 화면은 추가 확인 여지가 있습니다.

## 백엔드 관점 결론

- 백엔드와 RunPod 연결은 정상입니다.
- EP2는 현재 기준으로 정상 성공 케이스가 확인되었습니다.
- 이전 partial success 판단은 해소 방향으로 갱신할 수 있습니다.

## 모델팀 공유 메모

- EP2 재검증 성공
- `recommendations`와 `results` 모두 반환 확인
- 이전 `results=[]` 문제 미재현
