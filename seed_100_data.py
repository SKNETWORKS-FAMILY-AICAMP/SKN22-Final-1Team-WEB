import os
import random
import django
from django.utils import timezone
from django.contrib.auth.hashers import make_password
import uuid

# Django 환경 설정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mirrai_project.settings")
django.setup()

from app.models_model_team import LegacyShop, LegacyDesigner, LegacyClient

def generate_test_data():
    print("🚀 레거시 테이블 테스트 데이터 생성을 시작합니다...")

    shops_data = [
        {"name": "수진", "store_name": "수진이네", "phone": "01088881111", "biz": "111-11-11111"},
        {"name": "원빈", "store_name": "원빈이네", "phone": "01099992222", "biz": "222-22-22222"},
    ]
    
    shops = []
    for s_info in shops_data:
        shop = LegacyShop.objects.filter(login_id=s_info["phone"]).first()
        # Always update password to ensure it's "1234" correctly hashed
        hashed_pw = make_password("1234")
        if not shop:
            shop = LegacyShop.objects.create(
                shop_id=str(uuid.uuid4()),
                login_id=s_info["phone"],
                shop_name=s_info["store_name"],
                biz_number=s_info["biz"],
                owner_phone=s_info["phone"],
                password="1234",
                admin_pin="0000",
                created_at=timezone.now().isoformat(),
                updated_at=timezone.now().isoformat(),
                backend_admin_id=random.randint(1, 1000),
                name=s_info["name"],
                store_name=s_info["store_name"],
                phone=s_info["phone"],
                business_number=s_info["biz"],
                password_hash=hashed_pw,
                is_active=True
            )
        else:
            shop.password_hash = hashed_pw
            shop.save(update_fields=["password_hash"])
            
        shops.append(shop)
        print(f"✅ 매장: {shop.shop_name} (비밀번호 1234 설정됨)")

    designers = []
    names = ["민수", "준호", "지훈", "현우", "도윤", "서연", "지아", "하은", "미나", "유진"]
    
    for i in range(5):
        name = random.choice(names)
        target_shop = random.choice(shops)
        login_id = f"des_{uuid.uuid4().hex[:6]}"
        
        designer = LegacyDesigner.objects.create(
            designer_id=str(uuid.uuid4()),
            shop_id=target_shop.shop_id,
            designer_name=name,
            login_id=login_id,
            password="1234",
            is_active=True,
            created_at=timezone.now().isoformat(),
            updated_at=timezone.now().isoformat(),
            backend_designer_id=random.randint(1, 1000),
            backend_shop_ref_id=target_shop.backend_admin_id,
            name=name,
            phone=f"0105555{random.randint(1000, 9999)}",
            pin_hash=make_password("0000")
        )
        designers.append(designer)
        print(f"✅ 디자이너 생성: {designer.designer_name} ({target_shop.shop_name})")

    print(f"✅ 테스트 데이터 생성 완료. 매장 로그인은 비밀번호 '1234'를 사용하세요.")

if __name__ == "__main__":
    generate_test_data()
