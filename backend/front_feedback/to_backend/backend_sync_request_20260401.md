# 📋 백엔드 기술 요청 사항 (2026-04-01)

## 1. 고객 결과 페이지 접근 권한 로직 수정 요청

### [현상]
- 디자이너 대시보드(`partner/staff/`)에서 고객 성함 클릭 시, AI 분석 결과 페이지(`/customer/result/?id=XX`)로 이동하지 않고 고객 로그인 페이지(`/customer/`)로 강제 리다이렉트됨.

### [원인 분석]
- `backend/app/front_views.py`의 `client_recommendation_page` 함수 내 세션 체크 로직 이슈.
- 현재 코드는 `customer_id` 세션이 있을 때만 접근을 허용하고 있어, 매장 관리자나 디자이너 세션으로 접속 시 권한 없음으로 간주됨.

```python
# 현재 로직 (추정)
def client_recommendation_page(request):
    if not get_session_customer(request=request):
        return redirect("customer_index")  # 이 부분에서 리다이렉트 발생
    return render(request, "customer/result.html")
```

### [요청 사항]
- 매장 관리자(`admin_id`) 또는 디자이너(`designer_id`) 세션이 활성화된 상태에서도 해당 페이지에 접근할 수 있도록 예외 처리를 부탁드립니다.
- URL 파라미터로 전달되는 `id` 값을 우선적으로 참조하여 리포트를 렌더링할 수 있도록 뷰 로직 보완이 필요합니다.

---

**작성자**: 프론트엔드 담당자
**일자**: 2026-04-01
