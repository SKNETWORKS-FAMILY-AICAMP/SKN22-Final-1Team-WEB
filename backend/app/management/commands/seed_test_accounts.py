from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models_django import (
    AdminAccount,
    Client,
    ClientSessionNote,
    ConsultationRequest,
    Designer,
    Style,
    Survey,
)


def _build_valid_business_number(prefix: str) -> str:
    normalized = "".join(char for char in prefix if char.isdigit())[:9].ljust(9, "0")
    digits = [int(char) for char in normalized]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    checksum = sum(digit * weight for digit, weight in zip(digits, weights))
    checksum += (digits[8] * 5) // 10
    check_digit = (10 - (checksum % 10)) % 10
    return f"{normalized}{check_digit}"


class Command(BaseCommand):
    help = "Seed reusable local test accounts for frontend verification."

    def handle(self, *args, **options):
        seeded_at = timezone.now()

        shop = self._upsert_shop()
        designers = self._upsert_designers(shop=shop)
        clients = self._upsert_clients(shop=shop, designers=designers, seeded_at=seeded_at)
        self._upsert_consultations(shop=shop, designers=designers, clients=clients)

        self.stdout.write(self.style.SUCCESS("Local test accounts have been seeded."))
        self.stdout.write("")
        self.stdout.write("[Shop Admin]")
        self.stdout.write("  login page: /partner/login/")
        self.stdout.write(f"  business number: {shop.business_number}")
        self.stdout.write("  password: 1234")
        self.stdout.write("  phone: 010-8000-1000")
        self.stdout.write("  store: MirrAI Test Shop")
        self.stdout.write("")
        self.stdout.write("[Designers]")
        self.stdout.write("  Kim Mina / pin 2468")
        self.stdout.write("  Park Joon / pin 1357")
        self.stdout.write("")
        self.stdout.write("[Sample Customers]")
        self.stdout.write("  Choi Hana / 010-9000-1001 / Kim Mina assigned")
        self.stdout.write("  Lee Dohoon / 010-9000-1002 / Park Joon assigned")
        self.stdout.write("  Yoon Ara / 010-9000-1003 / Kim Mina assigned")
        self.stdout.write("  Han Seo / 010-9000-1004 / assignment pending")

    def _upsert_shop(self) -> AdminAccount:
        business_number = _build_valid_business_number("101234567")
        admin_defaults = {
            "name": "테스트 매장 관리자",
            "store_name": "MirrAI Test Shop",
            "role": "owner",
            "business_number": business_number,
            "password_hash": make_password("1234"),
            "consent_snapshot": {
                "agree_terms": True,
                "agree_privacy": True,
                "agree_third_party_sharing": True,
                "agree_marketing": False,
            },
            "consented_at": timezone.now(),
            "is_active": True,
        }
        shop, _ = AdminAccount.objects.update_or_create(
            phone="01080001000",
            defaults=admin_defaults,
        )
        return shop

    def _upsert_designers(self, *, shop: AdminAccount) -> list[Designer]:
        designer_specs = [
            ("김미나", "010-8111-2001", "2468"),
            ("박준", "010-8111-2002", "1357"),
        ]
        designers: list[Designer] = []
        for name, phone, pin in designer_specs:
            designer, _ = Designer.objects.update_or_create(
                shop=shop,
                name=name,
                defaults={
                    "phone": phone.replace("-", ""),
                    "pin_hash": make_password(pin),
                    "is_active": True,
                },
            )
            designers.append(designer)
        return designers

    def _upsert_clients(
        self,
        *,
        shop: AdminAccount,
        designers: list[Designer],
        seeded_at,
    ) -> dict[str, Client]:
        client_specs = [
            {
                "phone": "01090001001",
                "name": "최하나",
                "gender": "female",
                "age_input": 28,
                "birth_year_estimate": timezone.localdate().year - 28,
                "designer": designers[0],
                "assignment_source": "seeded_designer",
                "survey": {
                    "target_length": "long",
                    "target_vibe": "elegant",
                    "scalp_type": "waved",
                    "hair_colour": "brown",
                    "budget_range": "10_20",
                },
            },
            {
                "phone": "01090001002",
                "name": "이도훈",
                "gender": "male",
                "age_input": 34,
                "birth_year_estimate": timezone.localdate().year - 34,
                "designer": designers[1],
                "assignment_source": "seeded_designer",
                "survey": {
                    "target_length": "short",
                    "target_vibe": "chic",
                    "scalp_type": "straight",
                    "hair_colour": "black",
                    "budget_range": "5_10",
                },
            },
            {
                "phone": "01090001003",
                "name": "윤아라",
                "gender": "female",
                "age_input": 24,
                "birth_year_estimate": timezone.localdate().year - 24,
                "designer": designers[0],
                "assignment_source": "shop_manual_assignment",
                "survey": {
                    "target_length": "medium",
                    "target_vibe": "natural",
                    "scalp_type": "unknown",
                    "hair_colour": "ash",
                    "budget_range": "5_10",
                },
            },
            {
                "phone": "01090001004",
                "name": "한서",
                "gender": "female",
                "age_input": 31,
                "birth_year_estimate": timezone.localdate().year - 31,
                "designer": None,
                "assignment_source": "shop_manual_assignment_pending",
                "survey": {
                    "target_length": "medium",
                    "target_vibe": "clean",
                    "scalp_type": "sensitive",
                    "hair_colour": "dark_brown",
                    "budget_range": "10_20",
                },
            },
        ]

        clients: dict[str, Client] = {}
        for spec in client_specs:
            client, _ = Client.objects.update_or_create(
                phone=spec["phone"],
                defaults={
                    "name": spec["name"],
                    "gender": spec["gender"],
                    "shop": shop,
                    "designer": spec["designer"],
                    "assigned_at": (seeded_at if spec["designer"] is not None else None),
                    "assignment_source": spec["assignment_source"],
                    "age_input": spec["age_input"],
                    "birth_year_estimate": spec["birth_year_estimate"],
                },
            )
            Survey.objects.update_or_create(
                client=client,
                defaults={
                    **spec["survey"],
                    "preference_vector": [],
                },
            )
            clients[spec["phone"]] = client
        return clients

    def _upsert_consultations(
        self,
        *,
        shop: AdminAccount,
        designers: list[Designer],
        clients: dict[str, Client],
    ) -> None:
        style, _ = Style.objects.get_or_create(
            name="테스트 레이어드 컷",
            defaults={
                "vibe": "natural",
                "description": "프론트 확인용 테스트 스타일",
                "image_url": "",
            },
        )

        consultation_specs = [
            (clients["01090001001"], designers[0], "PENDING", False, "고객이 자연스러운 레이어드 컷을 원함."),
            (clients["01090001002"], designers[1], "IN_PROGRESS", True, "옆머리 다운펌과 짧은 기장 선호."),
        ]

        for client, designer, status, is_read, note_content in consultation_specs:
            survey_snapshot = None
            if hasattr(client, "survey"):
                survey_snapshot = {
                    "target_length": client.survey.target_length,
                    "target_vibe": client.survey.target_vibe,
                    "scalp_type": client.survey.scalp_type,
                    "hair_colour": client.survey.hair_colour,
                    "budget_range": client.survey.budget_range,
                }
            consultation, _ = ConsultationRequest.objects.update_or_create(
                client=client,
                is_active=True,
                defaults={
                    "admin": shop,
                    "designer": designer,
                    "selected_style": style,
                    "source": "seed_test_accounts",
                    "survey_snapshot": survey_snapshot,
                    "analysis_data_snapshot": {"seeded": True},
                    "status": status,
                    "is_read": is_read,
                },
            )
            ClientSessionNote.objects.update_or_create(
                consultation=consultation,
                client=client,
                designer=designer,
                defaults={
                    "admin": shop,
                    "content": note_content,
                },
            )
