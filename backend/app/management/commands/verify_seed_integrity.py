from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from app.api.v1.services_django import (
    get_current_recommendations,
    get_trend_recommendations,
)
from app.models_django import (
    AdminAccount,
    CaptureRecord,
    Client,
    ConsultationRequest,
    Designer,
    FaceAnalysis,
    FormerRecommendation,
    StyleSelection,
    Survey,
)


TEST_SHOP_PHONE = "01080001000"
EXPECTED_BUSINESS_NUMBER = "1012345672"
EXPECTED_CLIENT_PHONES = ("01090001001", "01090001002", "01090001003", "01090001004")
EXPECTED_COUNTS = {
    "designers": 2,
    "clients": 4,
    "surveys": 4,
    "captures": 3,
    "analyses": 3,
    "generated_recommendations": 15,
    "chosen_recommendations": 2,
    "style_selections": 2,
    "active_consultations": 2,
}


@dataclass(frozen=True)
class ClientExpectation:
    phone: str
    captures: int
    analyses: int
    generated_recommendations: int
    chosen_recommendations: int
    style_selections: int
    active_consultations: int
    has_current_recommendations: bool


EXPECTED_CLIENTS = (
    ClientExpectation("01090001001", 1, 1, 5, 1, 1, 1, True),
    ClientExpectation("01090001002", 1, 1, 5, 1, 1, 1, True),
    ClientExpectation("01090001003", 1, 1, 5, 0, 0, 0, True),
    ClientExpectation("01090001004", 0, 0, 0, 0, 0, 0, False),
)


class Command(BaseCommand):
    help = "Verify that the reusable seed data is present and internally consistent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if any expected count or per-client expectation is missing.",
        )

    def handle(self, *args, **options):
        strict = bool(options["strict"])
        problems: list[str] = []

        shop = AdminAccount.objects.filter(phone=TEST_SHOP_PHONE).select_related().first()
        if not shop:
            problems.append("shop account is missing")
        else:
            if shop.business_number != EXPECTED_BUSINESS_NUMBER:
                problems.append(
                    f"shop business number mismatch: expected {EXPECTED_BUSINESS_NUMBER}, got {shop.business_number}"
                )
            if not shop.is_active:
                problems.append("shop account is inactive")

        counts = {
            "designers": Designer.objects.filter(shop__phone=TEST_SHOP_PHONE, is_active=True).count(),
            "clients": Client.objects.filter(shop__phone=TEST_SHOP_PHONE).count(),
            "surveys": Survey.objects.filter(client__shop__phone=TEST_SHOP_PHONE).count(),
            "captures": CaptureRecord.objects.filter(client__shop__phone=TEST_SHOP_PHONE).count(),
            "analyses": FaceAnalysis.objects.filter(client__shop__phone=TEST_SHOP_PHONE).count(),
            "generated_recommendations": FormerRecommendation.objects.filter(
                client__shop__phone=TEST_SHOP_PHONE,
                source="generated",
            ).count(),
            "chosen_recommendations": FormerRecommendation.objects.filter(
                client__shop__phone=TEST_SHOP_PHONE,
                is_chosen=True,
            ).count(),
            "style_selections": StyleSelection.objects.filter(client__shop__phone=TEST_SHOP_PHONE).count(),
            "active_consultations": ConsultationRequest.objects.filter(
                client__shop__phone=TEST_SHOP_PHONE,
                is_active=True,
            ).count(),
        }

        for label, expected in EXPECTED_COUNTS.items():
            actual = counts.get(label, 0)
            if actual != expected:
                problems.append(f"{label} mismatch: expected {expected}, got {actual}")

        if shop:
            for phone in EXPECTED_CLIENT_PHONES:
                if not Client.objects.filter(phone=phone, shop=shop).exists():
                    problems.append(f"client is missing: {phone}")

        for expectation in EXPECTED_CLIENTS:
            client = Client.objects.filter(phone=expectation.phone, shop__phone=TEST_SHOP_PHONE).first()
            if not client:
                continue

            actual_counts = {
                "captures": CaptureRecord.objects.filter(client=client).count(),
                "analyses": FaceAnalysis.objects.filter(client=client).count(),
                "generated_recommendations": FormerRecommendation.objects.filter(
                    client=client,
                    source="generated",
                ).count(),
                "chosen_recommendations": FormerRecommendation.objects.filter(
                    client=client,
                    is_chosen=True,
                ).count(),
                "style_selections": StyleSelection.objects.filter(client=client).count(),
                "active_consultations": ConsultationRequest.objects.filter(
                    client=client,
                    is_active=True,
                ).count(),
            }

            if actual_counts["captures"] != expectation.captures:
                problems.append(
                    f"{client.phone} capture mismatch: expected {expectation.captures}, got {actual_counts['captures']}"
                )
            if actual_counts["analyses"] != expectation.analyses:
                problems.append(
                    f"{client.phone} analysis mismatch: expected {expectation.analyses}, got {actual_counts['analyses']}"
                )
            if actual_counts["generated_recommendations"] != expectation.generated_recommendations:
                problems.append(
                    f"{client.phone} generated recommendation mismatch: expected {expectation.generated_recommendations}, got {actual_counts['generated_recommendations']}"
                )
            if actual_counts["chosen_recommendations"] != expectation.chosen_recommendations:
                problems.append(
                    f"{client.phone} chosen recommendation mismatch: expected {expectation.chosen_recommendations}, got {actual_counts['chosen_recommendations']}"
                )
            if actual_counts["style_selections"] != expectation.style_selections:
                problems.append(
                    f"{client.phone} style selection mismatch: expected {expectation.style_selections}, got {actual_counts['style_selections']}"
                )
            if actual_counts["active_consultations"] != expectation.active_consultations:
                problems.append(
                    f"{client.phone} active consultation mismatch: expected {expectation.active_consultations}, got {actual_counts['active_consultations']}"
                )

            if expectation.has_current_recommendations:
                payload = get_current_recommendations(client)
                if not payload.get("items"):
                    problems.append(f"{client.phone} current recommendations are empty")
            else:
                payload = get_current_recommendations(client)
                if payload.get("items"):
                    problems.append(f"{client.phone} should not have current recommendations yet")

        trend_payload = get_trend_recommendations(days=30, client=Client.objects.filter(shop__phone=TEST_SHOP_PHONE).first())
        if not trend_payload.get("items"):
            problems.append("trend recommendations are empty")

        self.stdout.write(f"seed integrity summary: counts={counts}")
        self.stdout.write(
            "seed integrity trend items: "
            f"{len(trend_payload.get('items', []))} / scope={trend_payload.get('trend_scope')}"
        )

        if problems:
            for problem in problems:
                self.stderr.write(f"seed integrity issue: {problem}")
            if strict:
                raise CommandError("Seed integrity check failed.")
            self.stdout.write(self.style.WARNING("Seed integrity check completed with warnings."))
            return

        self.stdout.write(self.style.SUCCESS("Seed integrity check passed."))
