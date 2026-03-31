# 파트너 회원가입 400 오류 재검토 메모

작성일: 2026-03-30  
최종 재검토 반영: 0331

## 1. 메모 성격

이 문서는 0330 시점에 파트너 회원가입 400 원인을 분석했던 기록입니다.
다만 0331 기준으로 화면과 인증 구조가 일부 바뀌었기 때문에, 아래처럼 최신 상태를 함께 반영합니다.

## 2. 0330 당시 주요 원인

- `agree_third_party_sharing` 누락
- 전화번호 중복
- 사업자등록번호 유효성 실패

## 3. 0331 기준 최신 판단

- `agree_third_party_sharing`는 현재 화면에 생성된 상태를 확인
- 따라서 최신 기준에서 남는 직접 원인은
  - 전화번호 중복
  - 사업자등록번호 유효성 실패

즉, 이 문서는 현재 기준으로는 **역사적 분석 메모**에 가깝고,
실제 최신 상태 판단은 [backend_front_sync_status_report_0331_ver1.md](/c:/Workspaces/Teamwork/Final/backend/front_feedback/to_pm/backend_front_sync_status_report_0331_ver1.md)를 우선 기준으로 보는 편이 맞습니다.
