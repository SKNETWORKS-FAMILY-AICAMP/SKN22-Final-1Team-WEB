import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mirrai_project.settings')
django.setup()

from api.models import Customer, Style, StyleSelection, FaceAnalysis

def seed():
    print("Seeding database...")
    
    # 1. 테스트 고객 생성
    customer, created = Customer.objects.get_or_create(
        phone="01099998888",
        defaults={"name": "홍길동", "gender": "남성"}
    )
    if created:
        print(f"Created customer: {customer.name}")
    else:
        print(f"Customer already exists: {customer.name}")

    # 2. 기본 스타일 데이터 생성
    styles = [
        {"id": 101, "name": "시크 레이어드 컷", "vibe": "Chic", "description": "베스트셀러 스타일"},
        {"id": 102, "name": "내추럴 볼륨 펌", "vibe": "Natural", "description": "가장 많이 선호되는 펌"},
        {"id": 103, "name": "엣지 있는 크롭 컷", "vibe": "Trendy", "description": "트렌디한 남성 스타일"},
        {"id": 104, "name": "클래식 포마드", "vibe": "Classic", "description": "깔끔한 비즈니스 스타일"},
    ]
    
    for s_data in styles:
        style, created = Style.objects.get_or_create(
            id=s_data["id"],
            defaults={
                "name": s_data["name"],
                "vibe": s_data["vibe"],
                "description": s_data["description"]
            }
        )
        if created:
            print(f"Created style: {style.name}")

    # 3. 더미 분석 데이터 생성 (추천 테스트용)
    if not FaceAnalysis.objects.filter(customer=customer).exists():
        FaceAnalysis.objects.create(
            customer=customer,
            face_shape="계란형",
            golden_ratio_score=92.0,
            image_url="/media/captures/test_face.jpg"
        )
        print("Created dummy face analysis for recommendation test.")

    # 4. 더미 선택 이력 생성 (Trend 테스트용)
    if not StyleSelection.objects.exists():
        StyleSelection.objects.create(customer=customer, style_id=101, match_score=95.0)
        StyleSelection.objects.create(customer=customer, style_id=101, match_score=90.0)
        StyleSelection.objects.create(customer=customer, style_id=102, match_score=88.0)
        print("Created dummy style selections for Trend aggregation.")

if __name__ == "__main__":
    seed()
