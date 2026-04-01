# 프론트 기준 화면 정합성 #188

## 어떤 기능인가요?

> partner 화면과 dashboard 화면의 기준 UI를 프론트 화면에 맞춰 정리하고, 백엔드 템플릿과 프론트 기준 화면의 불일치를 줄이는 작업입니다.

## 작업 상세 내용

- [ ] `partner` 로그인/대시보드/직원 화면의 최종 기준 화면을 확정한다
- [ ] `보안 가이드`, 챗봇, 트렌드 리포트, 고객 목록 등 핵심 요소의 노출 위치를 프론트 기준에 맞춘다
- [ ] `shop owner`와 `designer`가 보는 화면과 접근 가능한 기능을 구분해 정리한다
- [ ] 로그인 후 이동 경로와 CTA 문구를 프론트 기준과 동일하게 맞춘다
- [ ] 화면 비교 체크리스트를 기준으로 누락 요소를 확인하고 수정한다

## 참고할만한 자료(선택)

- `templates/admin/index.html`
- `templates/admin/signup.html`
- `templates/layouts/base_site.html`

---

# 과거의 추천 내역 분리 #189

## 어떤 기능인가요?

> 현재 추천 결과와 과거 추천 이력을 분리해, 신규 추천 흐름과 이전 추천 조회 흐름이 서로 섞이지 않도록 정리하는 작업입니다.

## 작업 상세 내용

- [ ] `과거의 추천 내역`을 `/customer/history/` 기준으로 별도 화면으로 분리한다
- [ ] 신규 촬영 후 출력되는 추천 결과는 `/customer/recommendations/`에서만 표시되도록 고정한다
- [ ] 과거 추천 이력 화면에서 선택한 스타일을 상담사에게 전송하는 버튼을 제공한다
- [ ] `이전으로`, `새로운 스타일 추천(촬영)`, `이 스타일 선택(상담사 전송)` 버튼 흐름을 명확히 구분한다
- [ ] `result`와 `history` 간 라우트/문구/테스트를 함께 정리한다

## 참고할만한 자료(선택)

- `templates/customer/menu.html`
- `templates/customer/history.html`
- `templates/customer/result.html`
- `app/urls_front.py`
- `app/front_views.py`
