import os
import json
import urllib.request
import urllib.parse
import urllib.error

# Django 서버 주소 (로컬 또는 도커)
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")

TEST_CUSTOMER = {
    "name": "홍길동",
    "phone": "01099998888",
    "gender": "남성"
}

TEST_SURVEY = {
    "target_length": "쇼트",
    "target_vibe": "시크함",
    "scalp_type": "건성",
    "hair_colour": "브라우니",
    "budget_range": "10-15만원"
}

def make_request(url, method='GET', data=None, headers=None, is_json=True):
    if headers is None:
        headers = {}
    
    req_data = None
    if data:
        if isinstance(data, dict) and method in ['POST', 'PUT']:
            req_data = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        else:
            # For multipart or other, this simple helper might need enhancement
            # But for our Auth/Survey, it's enough
            pass

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            if is_json:
                return response.status, json.loads(res_body) if res_body else {}
            return response.status, res_body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 500, str(e)

def run_simulation():
    print(f"=== MirrAI 통합 시뮬레이션 (Target: {BASE_URL}) ===")
    
    # 0. 서버 상태 확인
    print("\n[0] 서버 연결 확인")
    try:
        status, res = make_request(BASE_URL + "/", 'GET')
        if status == 200 and isinstance(res, dict) and res.get("framework") == "Django":
            print(f"연결 성공: {res.get('status')} ({res.get('framework')})")
        else:
            print(f"경고: 예상치 못한 서버 응답 (Status: {status}). Django 서버가 맞는지 확인하세요.")
            if status == 404:
                print("서버는 작동 중이나 URL이 맞지 않습니다. (Not Found)")
            return
    except Exception as e:
        print(f"서버 연결 실패: {e}")
        return

    # 1. 로그인
    print("\n[1] 사용자 로그인 또는 생성")
    login_url = f"{BASE_URL}/api/v1/auth/login/"
    status, res = make_request(login_url, 'POST', {"phone": TEST_CUSTOMER["phone"]})
    
    if status == 404:
        print("사용자를 찾을 수 없습니다. (테스트 환경에서는 미리 생성되어 있어야 함)")
        return
    elif status != 200:
        print(f"로그인 실패 ({status}): {res}")
        print("서버가 실행 중인지 확인하세요 (run_server.bat 실행 중 필수)")
        return
        
    token = res.get("access_token")
    customer_id = res.get("customer_id")
    headers = {"Authorization": f"Bearer {token}"}
    print(f"로그인 완료. ID: {customer_id}, 토큰 발급 완료.")
    
    # 2. 설문조사
    print("\n[2] 스타일 설문조사 제출")
    survey_payload = {**TEST_SURVEY, "customer_id": customer_id}
    status, res = make_request(f"{BASE_URL}/api/v1/survey/", 'POST', survey_payload, headers)
    if status == 200:
        print("설문 제출 완료!")
    else:
        print(f"설문 실패 ({status}): {res}")
    
    # 3. 사진 업로드 시뮬레이션 (Multipart는 urllib로 구현이 복잡하므로 API 체크만)
    print("\n[3] (Skip) 사진 업로드 및 분석 - urllib 호환성을 위해 API 체크")
    # 실제 업로드는 multipart/form-data가 필요하여 건너뜁니다.
    
    # 4. 결과 추천
    print("\n[4] 추천 결과 조회")
    recommend_url = f"{BASE_URL}/api/v1/analysis/recommendations/?customer_id={customer_id}"
    status, recs = make_request(recommend_url, 'GET', headers=headers)
    if status == 200:
        print(f"추천 결과 {len(recs)}건 수신 완료!")
        
        # 5. 트렌드 조회
        print("\n[5] 매장 내 인기 트렌드 조회")
        status, trends = make_request(f"{BASE_URL}/api/v1/analysis/trend/", 'GET', headers=headers)
        if status == 200:
            print(f"트렌드 스타일 {len(trends)}건 수신 완료!")
            
        # 6. 디자이너 상담 전송
        print("\n[6] 디자이너에게 스타일 전송")
        if recs:
            consult_payload = {"customer_id": customer_id, "style_id": recs[0].get("style_id")}
            status, res = make_request(f"{BASE_URL}/api/v1/analysis/consult/", 'POST', consult_payload, headers)
            if status == 200:
                print("디자이너 전송 완료:", res.get("message"))
        
        print("\n--- 파이프라인 수신 데이터 요약 ---")
        for idx, rec in enumerate(recs, 1):
            print(f"[추천 {idx}] {rec.get('style_name')} (매칭 점수: {rec.get('match_score')})")
    else:
        print(f"추천 결과 조회 실패 ({status}): {recs}")

if __name__ == "__main__":
    run_simulation()
