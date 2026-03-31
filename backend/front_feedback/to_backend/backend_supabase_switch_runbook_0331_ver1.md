# Supabase 전환 실행절차 보고서

작성일: 0331  
버전: ver1

## 1. 목적

현재 로컬 SQLite 기준으로 동작 중인 backend를 Supabase DB 기준으로 전환하고,
전환 직후 발생할 수 있는 충돌을 사전 점검하기 위한 실행절차 및 결과 기록 문서입니다.

## 2. 전환 전 확인 항목

- [ ] `.env`에 Supabase DB URL이 설정되어 있는지 확인
- [ ] 기존 로컬 실행 스크립트가 `SUPABASE_USE_REMOTE_DB=False`를 강제로 넣고 있는지 확인
- [ ] 로컬 테스트 계정/샘플 데이터는 Supabase에 없을 수 있음을 인지
- [ ] 접속 실패 시 SQLite로 즉시 롤백 가능한지 확인

## 3. 적용 원칙

- 이번 전환은 우선 `DB 기준 전환`만 수행합니다.
- storage는 로컬 유지 (`SUPABASE_USE_REMOTE_STORAGE=False`)
- `DEBUG=True` 상태에서 먼저 접속, 렌더, 권한 흐름을 점검합니다.
- 로컬 UX 검증을 위해 mock result fallback은 유지하되, 운영 기본값은 변경하지 않습니다.

## 4. 실행 절차

### 4-1. 설정 분리

- [ ] 로컬 SQLite 실행 스크립트는 유지
- [ ] Supabase 전용 실행 스크립트 별도 생성
- [ ] Supabase 실행 시 아래 환경값 사용
  - `SUPABASE_USE_REMOTE_DB=True`
  - `SUPABASE_USE_REMOTE_STORAGE=False`
  - `DEBUG=True`
  - `MIRRAI_LOCAL_MOCK_RESULTS=True`

### 4-2. 원격 접속 확인

- [ ] `manage.py check`
- [ ] 실제 DB 연결 확인
- [ ] 접속 실패 시 에러 메시지 기록

### 4-3. 사전 충돌 테스트

- [ ] `/partner/` 렌더 확인
- [ ] shop 로그인 확인
- [ ] `/partner/dashboard/` 진입 확인
- [ ] `/partner/staff/` 진입 확인
- [ ] `/api/v1/customers/` 응답 확인
- [ ] `/api/v1/analysis/report/` 응답 확인
- [ ] `/customer/` 렌더 확인

### 4-4. 충돌 판단 기준

아래 중 하나라도 발생하면 Supabase 전환 충돌로 판단합니다.

- [ ] Supabase 접속 실패
- [ ] 원격 DB에 현재 backend 스키마가 없어 ORM 조회 실패
- [ ] 테스트 계정이 없어 인증 실패
- [ ] 세션/권한 흐름이 SQLite와 다르게 깨짐
- [ ] 템플릿은 열리지만 DB 조회 API가 500 또는 예상 밖 401/403을 반환

### 4-5. 롤백

- [ ] Supabase 실행 스크립트 종료
- [ ] 기존 SQLite 실행 스크립트로 복귀
- [ ] `SUPABASE_USE_REMOTE_DB=False` 상태 재확인

## 5. 이번 작업에서 기록할 항목

- 사용한 실행 스크립트 경로
- 접속 성공/실패 여부
- 마이그레이션 적용 여부
- 테스트 계정 시드 여부
- 핵심 URL 응답 결과
- 브라우저 수동 UX 검증에 필요한 계정/경로

## 6. 예상 리스크

- Supabase 네트워크/포트 이슈로 접속 실패 가능
- 원격 DB 스키마 누락으로 ORM 조회 실패 가능
- 로컬 시드 계정이 없어 인증 실패 가능
- 테스트 중 생성된 데이터가 원격 DB에 반영될 수 있음

## 7. 실행 결과

- [x] `SUPABASE_USE_REMOTE_DB=True` 기준 `manage.py check` 통과
- [x] Supabase 원격 DB 접속 확인
- [x] 원격 DB 마이그레이션 적용
- [x] `seed_test_accounts`를 Supabase DB에 실행
- [x] shop 로그인, 디자이너 선택, 디자이너 PIN 로그인까지 확인
- [x] `/partner/dashboard/`, `/partner/staff/`, `/api/v1/customers/`, `/api/v1/analysis/report/`, `/customer/` 기본 응답 확인

확인된 주요 결과:

- Supabase DB에는 테스트용 shop 1개, 디자이너 2명, 샘플 고객 4명이 반영된 상태입니다.
- shop owner 세션에서는 매장 전체 고객 목록과 트렌드 리포트 접근이 가능합니다.
- designer 세션에서는 본인 고객 목록만 조회되고, 매장 전체 트렌드 리포트는 403으로 차단됩니다.
- 원격 DB 기준 치명적 충돌은 확인되지 않았고, 전환 자체는 성공 상태입니다.

## 8. Supabase 수동 검증용 계정

- shop 로그인
  - 사업자등록번호: `1012345672`
  - 비밀번호: `1234`
- designer 로그인
  - 김미나: `2468`
  - 박준: `1357`

## 9. 실행 스크립트

- PowerShell: `scripts/run_supabase_server.ps1`
- CMD: `scripts/run_supabase_server.cmd`

## 10. 빠른 무결성 점검

Supabase 전환 후 DB 연결과 적재 상태를 다시 확인할 때는 아래 스크립트를 사용합니다.

- PowerShell: `scripts/check_supabase_integrity.ps1`
- CMD: `scripts/check_supabase_integrity.cmd`

실행 내용:

- `python manage.py check`
- `python manage.py verify_seed_integrity --strict`

즉, 팀원이 바로 봐야 하는 핵심은 `연결이 되는가`와 `필수 데이터가 실제로 적재되어 있는가`입니다.
