# 백엔드-프론트 동기화 상태 보고

작성일: 0331  
버전: ver1

## 1. 현재 판단

현재 backend는 주요 인증 구조, 세션 분리, 고객 배정 구조를 반영했고,
검증 기준 환경도 **로컬 DB가 아니라 Supabase 원격 DB**로 전환한 상태입니다.

핵심적으로 확인된 내용은 아래와 같습니다.

- shop 로그인: `사업자등록번호 + 비밀번호`
- 디자이너 로그인: `shop 로그인 -> 디자이너 선택 -> PIN`
- shop owner: `/partner/dashboard/`
- designer: `/partner/staff/`
- 고객 흐름: `/customer/ -> /customer/camera/ -> /customer/survey/ -> /customer/result/`
- 회원가입 성공 후 `/partner/dashboard/` 즉시 이동
- 테스트 계정은 Supabase DB에도 시드 적용 완료

## 2. 현재 backend에서 반영된 항목

- 관리자 세션 / 디자이너 세션 분리
- owner 전용 대시보드와 designer 전용 화면 분리
- 디자이너 목록 API 제공
- 고객 자동 배정 규칙 정리
- 미배정 고객 수동 배정 / 재배정 기능
- owner 전용 트렌드 리포트 접근
- `errors`, `message`, `error_code` 응답 형식

## 3. 회원가입 400 재검토 결과

이전에는 `agree_third_party_sharing` 누락이 주요 원인이었지만,
현재 최신 화면 기준으로는 그 체크박스가 생성된 상태를 확인했습니다.

지금 남아 있는 주요 원인은 아래 2가지입니다.

1. 전화번호 중복
2. 사업자등록번호 유효성 실패

즉 현재 회원가입 400은 정책 누락보다는 **중복 데이터와 입력값 유효성** 쪽에 가깝습니다.

## 4. Supabase 기준 검증 상태

아래 항목을 Supabase 기준으로 점검했습니다.

- `manage.py check`
- 원격 DB 마이그레이션
- 테스트 계정 시드
- shop 로그인
- 디자이너 선택 및 PIN 로그인
- `/partner/dashboard/`
- `/partner/staff/`
- `/api/v1/customers/`
- `/api/v1/analysis/report/`
- `/customer/`

현재 치명적 충돌은 확인되지 않았습니다.

## 5. 프론트와 계속 맞춰야 하는 부분

- owner 화면과 designer 화면의 UI 차이
- 로그인 이후 선택형 진입 구조 여부
- 회원가입 오류 메시지 표시 방식
- 고객 결과 흐름과 recommendation/result 화면 UX

## 6. 결론

현재 backend blocker는 대부분 해소된 상태입니다.
이제 남은 핵심은 프론트 화면 기준과 Supabase 기준 검증 흐름을 일치시키는 것입니다.
