# RunPod EP2 상세 보고서 `ver1`

## 대상

- Endpoint: `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`
- 경로: EP2 추천 기반 생성

## 테스트 목적

- 추천 기반 생성 경로에서
  1. 추천 metadata가 정상 생성되는지
  2. 실제 생성 결과(`results`)까지 내려오는지
를 분리해서 확인

## 테스트 조건

- `image`: 공개 이미지 URL
- `face_ratios`: 고정 샘플 비율
- `preference_text`: `natural medium length, warm tone`
- `age`: `28`
- `top_k`: `1`
- `return_base64`: `false`, 이후 `true`로 재확인

## 요청 본문

```json
{
  "input": {
    "image": "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama.jpg",
    "face_ratios": {
      "cheekbone_to_height": 0.72,
      "jaw_to_height": 0.60,
      "temple_to_height": 0.70,
      "jaw_to_cheekbone": 0.83
    },
    "preference_text": "natural medium length, warm tone",
    "age": 28,
    "top_k": 1,
    "return_base64": true
  }
}
```

## 응답 요약

응답 상태:
- `status: COMPLETED`

정상 반환된 것:
- `recommendations` 배열
- 추천 스타일 정보
  - `style_id`
  - `style_name`
  - `score`
  - `face_shape_detected`
  - `golden_ratio_score`
  - 기타 추천 metadata

비정상인 것:
- `results` 배열이 비어 있음
- `return_base64=false`일 때도 비어 있음
- `return_base64=true`일 때도 비어 있음

## 확인된 사실

- 추천 엔진 또는 추천 metadata 생성 단계는 정상 동작하는 것으로 보입니다.
- 그러나 실제 생성 결과를 담아야 하는 `results`가 비어 있어,
  README에서 기대하는 "추천 + 생성 결과" 계약과는 아직 다릅니다.
- 즉, EP2는 완전 실패는 아니지만 완전 성공도 아닙니다.

## 원인 해석

현재 확인 가능한 수준의 해석:
- 추천 단계는 통과했지만, 이미지 생성 단계가 생략되거나
  생성 결과를 `results`로 적재하는 후처리 단계가 빠진 것으로 보입니다.

가능한 원인:
- 추천 only 경로로 조기 종료
- 생성 단계 예외가 내부에서 삼켜짐
- `results` 구성 로직이 특정 옵션 조합에서 누락
- README 최신 계약과 배포본 구현 차이

## 장애 수준 평가

판단: **중간 이상**

이유:
- 추천 정보 자체는 나오므로 기능이 완전히 죽은 것은 아닙니다.
- 하지만 EP2의 사용자 기대치는 추천 목록만이 아니라 생성 결과 이미지까지 포함됩니다.
- 현재 `results`가 비어 있으므로, 핵심 가치 중 "시뮬레이션 결과 확인"이 빠져 있습니다.

서비스 영향:
- 추천 텍스트/메타데이터만으로도 일부 fallback은 가능
- 그러나 생성 이미지를 보여줘야 하는 실제 사용자 경험 기준으로는
  **부분 장애이지만 영향도가 큰 편**입니다.

정리:
- 시스템 전체 중단은 아님
- 다만 실서비스 품질 기준에서는 무시하기 어려운 결손

## 백엔드 관점 결론

- backend -> RunPod 연결 정상
- EP2 추천 metadata 정상
- 그러나 생성 결과가 비어 있어, EP2는 아직 "완료"로 보기 어려움

## 모델팀 확인 요청

- `recommendations`는 정상인데 `results`가 비는 이유 확인
- 생성 단계가 실제로 실행되는지, 실행 후 결과 적재가 누락되는지 확인
- `return_base64` 여부와 무관하게 `results`가 비는 원인 확인
- 수정 후 동일 payload로 재검증 필요
