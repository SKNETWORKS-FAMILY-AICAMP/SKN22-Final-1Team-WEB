# [Report] MirrAI 서비스 플로우 및 API 연동 동기화 가이드

작성일: 2026-03-30  
재검토 반영: 0331  
기준 환경: Supabase 원격 DB

## 1. 목적

현재 코드 기준 사용자 여정과 페이지 이동, 주요 API 연결 구조를 최신 상태로 정리한 문서입니다.

## 2. 고객 흐름

1. `/customer/`
   - 고객 정보 입력
   - `POST /customer/`
2. `/customer/camera/`
   - 사진 촬영 및 업로드
   - `POST /api/v1/capture/upload/`
3. `/customer/survey/`
   - 취향 설문
   - `POST /api/v1/survey/`
4. `/customer/result/`
   - 추천 결과 확인
   - 결과 조회 및 후속 액션

즉, 현재 기준 고객 흐름은 **정보 입력 -> 촬영 -> 설문 -> 결과**입니다.

## 3. 파트너 흐름

### 3-1. shop owner 진입

1. `/partner/login/`
   - 사업자등록번호 + 비밀번호 로그인
   - `POST /partner/verify/`
2. 디자이너 선택 화면 노출
3. owner가 바로 매장 전체 대시보드로 이동 시
   - `/partner/dashboard/`

### 3-2. designer 진입

1. shop 로그인 완료
2. 디자이너 선택
3. PIN 입력
   - `POST /partner/verify/`
4. `/partner/staff/`

## 4. 주요 API

- `POST /partner/verify/`
  - shop 로그인 또는 디자이너 PIN 로그인 처리
- `GET /api/v1/designers/`
  - 현재 shop 기준 디자이너 목록 조회
- `GET /api/v1/customers/`
  - owner 또는 designer 세션 기준 고객 목록 조회
- `GET /api/v1/analysis/report/`
  - owner 전용 매장 전체 트렌드 리포트
- `POST /api/v1/admin/auth/register/`
  - 파트너 회원가입

## 5. 주의사항

- 현재 인증 구조는 예전의 `PIN 단일 로그인` 기준이 아닙니다.
- 프론트 화면과 문서도 `shop 로그인 -> 디자이너 선택 -> PIN` 구조로 맞춰서 해석해야 합니다.
- 수동 검증은 Supabase 원격 DB 기준으로 보는 편이 정확합니다.
