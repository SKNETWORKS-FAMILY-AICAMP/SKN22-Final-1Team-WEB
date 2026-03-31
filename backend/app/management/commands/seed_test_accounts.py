from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone

from app.api.v1.recommendation_logic import build_preference_vector
from app.api.v1.services_django import build_survey_snapshot, persist_generated_batch
from app.models_django import (
    AdminAccount,
    CaptureRecord,
    Client,
    ClientSessionNote,
    ConsultationRequest,
    Designer,
    FaceAnalysis,
    FormerRecommendation,
    Style,
    StyleSelection,
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


@dataclass(frozen=True)
class SeededClientSpec:
    phone: str
    name: str
    gender: str
    age_input: int
    designer_index: int | None
    assignment_source: str
    survey: dict


@dataclass(frozen=True)
class DownstreamSeedSpec:
    phone: str
    face_shape: str
    golden_ratio_score: float
    choose_rank: int | None


CLIENT_SPECS: tuple[SeededClientSpec, ...] = (
    SeededClientSpec(
        phone="01090001001",
        name="최하나",
        gender="female",
        age_input=28,
        designer_index=0,
        assignment_source="seeded_designer",
        survey={
            "target_length": "long",
            "target_vibe": "elegant",
            "scalp_type": "waved",
            "hair_colour": "brown",
            "budget_range": "10_20",
        },
    ),
    SeededClientSpec(
        phone="01090001002",
        name="이도훈",
        gender="male",
        age_input=34,
        designer_index=1,
        assignment_source="seeded_designer",
        survey={
            "target_length": "short",
            "target_vibe": "chic",
            "scalp_type": "straight",
            "hair_colour": "black",
            "budget_range": "5_10",
        },
    ),
    SeededClientSpec(
        phone="01090001003",
        name="윤아라",
        gender="female",
        age_input=24,
        designer_index=0,
        assignment_source="shop_manual_assignment",
        survey={
            "target_length": "medium",
            "target_vibe": "natural",
            "scalp_type": "unknown",
            "hair_colour": "ash",
            "budget_range": "5_10",
        },
    ),
    SeededClientSpec(
        phone="01090001004",
        name="한서",
        gender="female",
        age_input=31,
        designer_index=None,
        assignment_source="shop_manual_assignment_pending",
        survey={
            "target_length": "medium",
            "target_vibe": "clean",
            "scalp_type": "sensitive",
            "hair_colour": "dark_brown",
            "budget_range": "10_20",
        },
    ),
)

DOWNSTREAM_SPECS: tuple[DownstreamSeedSpec, ...] = (
    DownstreamSeedSpec(
        phone="01090001001",
        face_shape="oval",
        golden_ratio_score=0.92,
        choose_rank=1,
    ),
    DownstreamSeedSpec(
        phone="01090001002",
        face_shape="square",
        golden_ratio_score=0.88,
        choose_rank=2,
    ),
    DownstreamSeedSpec(
        phone="01090001003",
        face_shape="round",
        golden_ratio_score=0.9,
        choose_rank=None,
    ),
)


class Command(BaseCommand):
    help = "Seed reusable partner/customer verification accounts and downstream test data."

    def handle(self, *args, **options):
        seeded_at = timezone.now()

        shop = self._upsert_shop()
        designers = self._upsert_designers(shop=shop)
        clients = self._upsert_clients(shop=shop, designers=designers, seeded_at=seeded_at)
        self._upsert_downstream_data(shop=shop, clients=clients)
        self._upsert_consultation_notes(shop=shop, designers=designers, clients=clients)

        self.stdout.write(self.style.SUCCESS("Reusable test accounts have been seeded."))
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
        self.stdout.write("  Choi Hana / 010-9000-1001 / Kim Mina assigned / seeded recommendations ready")
        self.stdout.write("  Lee Dohoon / 010-9000-1002 / Park Joon assigned / seeded recommendations ready")
        self.stdout.write("  Yoon Ara / 010-9000-1003 / Kim Mina assigned / current recommendations ready")
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
        designer_specs = (
            ("김미나", "010-8111-2001", "2468"),
            ("박준", "010-8111-2002", "1357"),
        )
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
        clients: dict[str, Client] = {}
        current_year = timezone.localdate().year

        for spec in CLIENT_SPECS:
            assigned_designer = designers[spec.designer_index] if spec.designer_index is not None else None
            client, _ = Client.objects.update_or_create(
                phone=spec.phone,
                defaults={
                    "name": spec.name,
                    "gender": spec.gender,
                    "shop": shop,
                    "designer": assigned_designer,
                    "assigned_at": (seeded_at if assigned_designer is not None else None),
                    "assignment_source": spec.assignment_source,
                    "age_input": spec.age_input,
                    "birth_year_estimate": current_year - spec.age_input,
                },
            )
            Survey.objects.update_or_create(
                client=client,
                defaults={
                    **spec.survey,
                    "preference_vector": build_preference_vector(**spec.survey),
                },
            )
            clients[spec.phone] = client
        return clients

    def _upsert_downstream_data(
        self,
        *,
        shop: AdminAccount,
        clients: dict[str, Client],
    ) -> None:
        for spec in DOWNSTREAM_SPECS:
            client = clients[spec.phone]
            survey = Survey.objects.get(client=client)
            capture = self._upsert_capture(client=client)
            analysis = self._upsert_analysis(client=client, spec=spec)

            StyleSelection.objects.filter(client=client, source="seed_test_accounts").delete()
            ConsultationRequest.objects.filter(client=client, source="seed_test_accounts").delete()
            FormerRecommendation.objects.filter(client=client, source="generated").delete()

            _, rows = persist_generated_batch(
                client=client,
                capture_record=capture,
                survey=survey,
                analysis=analysis,
            )

            chosen_row = None
            if spec.choose_rank is not None:
                chosen_row = next((row for row in rows if row.rank == spec.choose_rank), None)
                if chosen_row is not None:
                    chosen_row.is_chosen = True
                    chosen_row.chosen_at = timezone.now()
                    chosen_row.is_sent_to_admin = True
                    chosen_row.sent_at = timezone.now()
                    chosen_row.save(
                        update_fields=["is_chosen", "chosen_at", "is_sent_to_admin", "sent_at"]
                    )

                    StyleSelection.objects.create(
                        client=client,
                        selected_recommendation=chosen_row,
                        style_id=chosen_row.style_id_snapshot,
                        source="seed_test_accounts",
                        survey_snapshot=build_survey_snapshot(client),
                        match_score=chosen_row.match_score,
                        is_sent_to_admin=True,
                    )

                    ConsultationRequest.objects.create(
                        client=client,
                        admin=shop,
                        designer=client.designer,
                        selected_style=chosen_row.style,
                        selected_recommendation=chosen_row,
                        source="seed_test_accounts",
                        survey_snapshot=build_survey_snapshot(client),
                        analysis_data_snapshot={
                            "seeded": True,
                            "face_shape": analysis.face_shape,
                            "golden_ratio": analysis.golden_ratio_score,
                        },
                        status="PENDING",
                        is_active=True,
                        is_read=False,
                    )

    def _upsert_capture(self, *, client: Client) -> CaptureRecord:
        capture, _ = CaptureRecord.objects.update_or_create(
            client=client,
            filename=f"seed-client-{client.phone}.jpg",
            defaults={
                "original_path": f"seed/captures/{client.phone}/original.jpg",
                "processed_path": f"seed/captures/{client.phone}/processed.jpg",
                "status": "DONE",
                "face_count": 1,
                "landmark_snapshot": {
                    "left_eye": {"point": {"x": 0.35, "y": 0.38}},
                    "right_eye": {"point": {"x": 0.65, "y": 0.38}},
                    "mouth_center": {"point": {"x": 0.5, "y": 0.68}},
                    "chin_center": {"point": {"x": 0.5, "y": 0.88}},
                },
                "deidentified_path": f"seed/captures/{client.phone}/deidentified.jpg",
                "privacy_snapshot": {
                    "retention": "seed_test_accounts",
                    "consent_verified": True,
                },
                "error_note": "",
            },
        )
        return capture

    def _upsert_analysis(self, *, client: Client, spec: DownstreamSeedSpec) -> FaceAnalysis:
        analysis, _ = FaceAnalysis.objects.update_or_create(
            client=client,
            image_url=f"seed/analysis/{client.phone}/front.jpg",
            defaults={
                "face_shape": spec.face_shape,
                "golden_ratio_score": spec.golden_ratio_score,
                "landmark_snapshot": {
                    "seeded": True,
                    "face_shape": spec.face_shape,
                    "client_phone": client.phone,
                },
            },
        )
        return analysis

    def _upsert_consultation_notes(
        self,
        *,
        shop: AdminAccount,
        designers: list[Designer],
        clients: dict[str, Client],
    ) -> None:
        note_specs = (
            (
                clients["01090001001"],
                designers[0],
                "고객은 자연스러운 레이어드 컷과 부드러운 컬감을 선호한다고 전달했습니다.",
            ),
            (
                clients["01090001002"],
                designers[1],
                "옆머리는 깔끔하게 정리하고, 전체 길이는 짧고 단정한 느낌을 원합니다.",
            ),
        )

        for client, designer, note_content in note_specs:
            consultation = (
                ConsultationRequest.objects.filter(client=client, is_active=True)
                .order_by("-created_at")
                .first()
            )
            if consultation is None:
                continue
            ClientSessionNote.objects.update_or_create(
                consultation=consultation,
                client=client,
                designer=designer,
                defaults={
                    "admin": shop,
                    "content": note_content,
                },
            )
