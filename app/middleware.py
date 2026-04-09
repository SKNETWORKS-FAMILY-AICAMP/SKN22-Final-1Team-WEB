from django.utils.deprecation import MiddlewareMixin
from app.session_state import clear_customer_session, clear_designer_session

class BrowserSessionCleanupMiddleware(MiddlewareMixin):
    """
    브라우저 종료 시 고객 및 디자이너 세션만 초기화하고, 
    매장(Admin) 세션은 유지하는 미들웨어.
    """
    def process_request(self, request):
        # 'browser_active' 쿠키가 없으면 브라우저가 새로 열린 것으로 간주
        if not request.COOKIES.get('browser_active'):
            # 매장 세션은 유지하되, 고객과 디자이너 세션만 삭제
            # (clear_customer_session 등은 세션 키만 삭제함)
            clear_customer_session(request=request)
            clear_designer_session(request=request)

    def process_response(self, request, response):
        # 브라우저 종료 시 만료되는 쿠키 설정 (max_age=None)
        if not request.COOKIES.get('browser_active'):
            response.set_cookie('browser_active', '1', max_age=None, httponly=True)
        return response
