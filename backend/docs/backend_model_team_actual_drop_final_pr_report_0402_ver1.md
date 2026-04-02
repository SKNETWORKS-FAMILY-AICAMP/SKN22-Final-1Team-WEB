## 개요

이번 작업은 model-team 테이블을 backend의 최종 source of truth로 고정한 뒤, 원격 Supabase에서 backend canonical 후보 테이블을 실제로 제거하고 drop 이후 무결성을 재검토한 정리 작업이다.

배경으로는 backend가 한동안 model-team 원본 테이블과 별도로 canonical 테이블을 운용하면서, 동일 개념에 대한 이중 참조와 매핑 해석 충돌이 누적된 문제가 있었다. 이번 정리는 그 과도기 구조를 끝내고 source of truth를 model-team 테이블로 단일화하는 데 목적이 있다.

이번 문서는 아래 세 문서를 하나로 통합한 최종 PR용 보고서다.

- `backend_model_team_actual_drop_runbook_0402_ver1.md`
- `backend_model_team_actual_drop_review_0402_ver1.md`
- `backend_model_team_actual_drop_pr_note_0402_ver1.md`

## 1. drop 대상과 전제

actual drop 대상은 아래 10개 canonical 후보 테이블이다.

- `admin_accounts`
- `designers`
- `clients`
- `surveys`
- `capture_records`
- `face_analyses`
- `former_recommendations`
- `style_selections`
- `consultation_requests`
- `styles`

유지 예외는 아래 1개다.

- `client_session_notes`

drop 실행 전 전제는 다음과 같았다.

- remote canonical 후보 row가 모두 `0`
- `python manage.py check` 통과
- `python manage.py verify_seed_integrity --strict` 통과
- `python manage.py audit_model_team_cutover --strict` 통과
- canonical 백업 파일 생성 완료

관련 백업:

- [remote_canonical_backup_0402_ver1.json](/c:/Workspaces/Teamwork/Final/backend/data/backups/remote_canonical_backup_0402_ver1.json)
- [remote_test_shop_legacy_backup_0402_ver1.json](/c:/Workspaces/Teamwork/Final/backend/data/backups/remote_test_shop_legacy_backup_0402_ver1.json)
- [canonical_drop_backup_0402_ver1.json](/c:/Workspaces/Teamwork/Final/backend/data/backups/canonical_drop_backup_0402_ver1.json)

## 2. 실제 수행 내용

원격 Supabase에서 backend canonical 후보 10개 테이블에 대해 `DROP TABLE IF EXISTS ... CASCADE`를 실행했다.

실제 삭제한 테이블:

- `admin_accounts`
- `designers`
- `clients`
- `surveys`
- `capture_records`
- `face_analyses`
- `former_recommendations`
- `style_selections`
- `consultation_requests`
- `styles`

보존한 테이블:

- `client_session_notes`

즉, 이번 단계에서 row cleanup이 아니라 actual drop까지 완료했다.

## 3. drop 이후 원격 재검토

drop 직후 아래 검증을 다시 수행했다.

```powershell
$env:SUPABASE_USE_REMOTE_DB='True'
python manage.py check
python manage.py verify_seed_integrity --strict
python manage.py audit_model_team_cutover --strict
```

검증 결과:

- `python manage.py check` 통과
- `python manage.py verify_seed_integrity --strict` 통과
- `python manage.py audit_model_team_cutover --strict` 통과

추가 확인 결과:

- canonical 후보 10개 테이블 모두 `exists=False`
- `client_session_notes`만 `exists=True`
- `legacy tables present: 8/8`
- `legacy strict integrity: passed`
- `code blockers: none`

즉, canonical 후보는 실제로 제거되었고 model-team 기준 strict 무결성도 유지됐다.

## 4. 영향 범위

이번 작업 이후 상태는 다음과 같다.

- backend 기준 source of truth는 model-team 테이블로 확정
- backend canonical 후보 테이블은 원격 Supabase에서 실제 제거됨
- `client_session_notes`만 backend 전용 유지 예외로 남음
- front/model 팀 소스 파일은 수정하지 않음

즉, 이번 작업은 backend와 원격 DB 기준 정리 작업이며, front/model 팀 작업물 수정 없이 완료됐다.

## 5. 결론

원격 Supabase에서 backend canonical 후보 테이블 actual drop를 완료했고, drop 이후에도 backend 무결성 검사는 정상 통과했다.

현재 기준으로:

- canonical 후보 테이블은 실제 제거된 상태
- `client_session_notes`만 유지
- model-team 테이블이 backend의 최종 원본 기준으로 동작

즉, model-team 원본 기준 Supabase DB table 정리는 actual drop 단계까지 완료된 상태다.
