# 백엔드 develop 재머지 체크리스트

작성일: 0331  
버전: ver1

## 1. 목적

`feature/180-partner-auth-local-test`의 후속 작업을 최신 `develop` 위에 다시 올릴 때,
백엔드 기준으로 먼저 확인해야 하는 충돌 포인트와 회귀 검증 순서를 정리한 문서입니다.

## 2. 현재 전제

- 최신 `develop`에는 프론트 동기화 머지(`#183`)가 반영되어 있습니다.
- 최근 재머지 확인 결과, 실제 핵심 충돌 포인트는 `templates/admin/index.html`에 집중되었습니다.
- 텍스트 충돌보다 **권한 분기와 버튼 노출 회귀**가 더 큰 리스크였습니다.

## 3. 가장 먼저 볼 파일

### 3-1. 템플릿

- `templates/admin/index.html`
- `templates/admin/signup.html`
- `templates/layouts/base_site.html`

### 3-2. 라우팅/권한

- `app/front_views.py`
- `app/api/v1/admin_views.py`
- `app/api/v1/admin_services.py`
- `app/api/v1/urls_django.py`
- `app/urls_front.py`

### 3-3. 시드/검증

- `app/management/commands/seed_test_accounts.py`
- `app/management/commands/verify_seed_integrity.py`
- `app/tests/test_front_compatibility.py`
- `app/tests/test_seed_test_accounts.py`

## 4. 재머지 직후 체크포인트

### 4-1. partner 화면 권한 분기

- [ ] shop 로그인 후 디자이너 선택 화면에서 `매장 전체 대시보드로 이동` 버튼이 보이는지 확인
- [ ] owner는 `/partner/dashboard/`로 들어가고 designer는 `/partner/staff/`로 분기되는지 확인
- [ ] designer가 `/partner/dashboard/`를 직접 치면 `/partner/staff/`로 이동하는지 확인

### 4-2. 버튼/기능 노출 회귀

- [ ] `showReportBtn`이 owner 화면에서만 보이는지 확인
- [ ] designer 화면에서는 `트렌드 리포트` 버튼이 다시 나타나지 않는지 확인
- [ ] 고객 배정/재배정 UI가 owner 화면에서 유지되는지 확인

### 4-3. 데이터/API 연결

- [ ] `/api/v1/designers/`가 shop 세션 기준으로만 디자이너 목록을 반환하는지 확인
- [ ] `/api/v1/customers/` 응답에 `assignment_source`, `is_assignment_pending`, `designer_name`이 유지되는지 확인
- [ ] `/api/v1/analysis/report/`가 owner에게만 열리고 designer에게는 403인지 확인

## 5. 백엔드 즉시 검증 명령

재머지 후에는 아래 순서대로 바로 확인합니다.

```powershell
python manage.py check
python manage.py test --keepdb app.tests.test_front_compatibility app.tests.test_seed_test_accounts
python manage.py verify_seed_integrity --strict
```

## 6. 최근 실제 회귀 사례

최신 `develop` 머지 확인 시 아래 두 문제가 재현된 적이 있습니다.

- `shopDashboardShortcut` 누락
- designer 화면에도 `showReportBtn` 노출

따라서 재머지 시 가장 먼저 `templates/admin/index.html`을 확인해야 합니다.

## 7. 판단 기준

아래 3개를 모두 만족하면 백엔드 기준 재머지는 정상으로 봅니다.

- [ ] 권한 분기 회귀 없음
- [ ] 핵심 테스트 통과
- [ ] Supabase 시드 무결성 검증 통과
