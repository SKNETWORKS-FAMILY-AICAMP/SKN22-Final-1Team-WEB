# RunPod 검증 보고서 `ver1`

## 목적

백엔드에서 현재 RunPod endpoint를 동일한 주소로 다시 검증한 결과를 정리합니다.

대상 endpoint:
- `https://api.runpod.ai/v2/42giqi5gbhd6qe/runsync`

## 검증 결과

### 1. Health check

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

정리:
- health check는 현재 정상 복구된 것으로 판단됩니다.

### 2. EP1 직접 생성

테스트 조건:
- 최소 생성 요청
- `top_k=1`
- `return_base64=false`

결과:
- 실패
- RunPod 응답 자체는 돌아왔지만, 배포된 코드 내부에서 런타임 에러 발생

에러:
- `NameError: name 'effective_hairstyle_text' is not defined`

정리:
- 입력 형식 문제나 백엔드 연결 문제보다는, 현재 배포된 코드 내부 오류로 보입니다.

### 3. EP2 추천 기반 생성

테스트 조건:
- `face_ratios + preference_text + age + top_k=1`
- `return_base64=false`
- 이어서 `return_base64=true`도 재확인

결과:
- 요청 자체는 성공
- `recommendations`는 정상 반환
- 하지만 실제 생성 결과인 `results` 배열은 비어 있음
- `return_base64` 값을 바꿔도 동일

정리:
- 추천 단계는 일부 정상 동작
- 그러나 실제 생성 결과가 비어 있어 README 기대 동작과 아직 차이가 있습니다.

## 백엔드 관점 해석

- 백엔드 -> RunPod 연결 자체는 정상입니다.
- health check도 이제 정상입니다.
- 현재 blocker는 백엔드 연결이 아니라, 배포된 model runtime의 생성 경로입니다.

## 모델팀 확인 요청

- EP1에서 `effective_hairstyle_text` 런타임 오류가 발생하는 원인 확인 부탁드립니다.
- EP2에서 `recommendations`는 반환되는데 `results`가 비는 원인 확인 부탁드립니다.
- 현재 배포된 handler 기준 응답이 README와 일치하는지 재확인 부탁드립니다.

## 현재 백엔드 판단

- `#135`는 health check만 기준으로 보면 진척이 있지만,
- 생성 경로가 아직 정상 완료 상태가 아니므로 전체 이슈는 계속 `in progress`가 적절합니다.
