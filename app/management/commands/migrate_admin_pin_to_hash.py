"""
management command: migrate_admin_pin_to_hash
=============================================
Supabase DB(shop 테이블)에 저장된 평문 admin_pin을
Django pbkdf2_sha256 해시로 일괄 업그레이드합니다.

사용법:
    python manage.py migrate_admin_pin_to_hash            # 실제 변경
    python manage.py migrate_admin_pin_to_hash --dry-run  # 변경 없이 대상만 출력

결과:
    - 이미 해시된 레코드: 건드리지 않음 (safe)
    - 평문으로 저장된 레코드: make_password() 로 해시 후 저장
    - NULL / 빈값: 기본값 "0000" 으로 해시 후 저장
"""
from __future__ import annotations

from django.contrib.auth.hashers import identify_hasher, make_password
from django.core.management.base import BaseCommand, CommandError

from app.models_django import AdminAccount


def _is_hashed(value: str | None) -> bool:
    """Django hasher 식별자가 있으면 True."""
    normalized = (value or "").strip()
    if not normalized:
        return False
    try:
        identify_hasher(normalized)
        return True
    except ValueError:
        return False


class Command(BaseCommand):
    help = (
        "Supabase shop 테이블의 평문 admin_pin을 pbkdf2_sha256 해시로 일괄 업그레이드합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="실제 DB를 변경하지 않고 마이그레이션 대상만 출력합니다.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        mode_label = "[DRY-RUN] " if dry_run else ""

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{mode_label}admin_pin 해시 마이그레이션 시작 (shop 테이블 / Supabase)"
            )
        )

        all_accounts = AdminAccount.objects.all().only("id", "admin_pin", "phone", "store_name", "name")
        total = all_accounts.count()
        self.stdout.write(f"  전체 shop 레코드: {total}건")

        already_hashed = 0
        migrated = 0
        defaulted = 0
        errors = 0

        for account in all_accounts:
            stored = (account.admin_pin or "").strip()

            if _is_hashed(stored):
                already_hashed += 1
                continue

            # 평문 또는 NULL/빈값
            raw_pin = stored if stored else "0000"
            is_default = (raw_pin == "0000")

            label = (
                f"shop_id={account.id} | "
                f"phone={account.phone or '-'} | "
                f"store={account.store_name or account.name or '-'}"
            )

            if dry_run:
                action = "기본값(0000)으로 해시 예정" if is_default else f"평문 '{raw_pin}' → 해시 예정"
                self.stdout.write(f"  [DRY] {label} | {action}")
            else:
                try:
                    account.admin_pin = make_password(raw_pin)
                    account.save(update_fields=["admin_pin"])
                    action = "기본값(0000) 해시 완료" if is_default else f"평문 '{raw_pin}' → 해시 완료"
                    self.stdout.write(f"  [OK]  {label} | {action}")
                except Exception as exc:
                    errors += 1
                    self.stderr.write(
                        self.style.ERROR(f"  [ERR] {label} | {exc}")
                    )
                    continue

            migrated += 1
            if is_default:
                defaulted += 1

        # ──────────────────────────────────────────
        # 요약
        # ──────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"{mode_label}마이그레이션 완료 요약"))
        self.stdout.write(f"  전체 레코드       : {total}")
        self.stdout.write(f"  이미 해시됨 (skip): {already_hashed}")
        self.stdout.write(f"  마이그레이션 대상 : {migrated}")
        self.stdout.write(f"    +- 기본값(0000)  : {defaulted}")
        self.stdout.write(f"    +- 기존 평문 PIN : {migrated - defaulted}")
        if errors:
            self.stdout.write(
                self.style.ERROR(f"  오류 발생         : {errors}")
            )
            raise CommandError(f"마이그레이션 중 {errors}건 오류가 발생했습니다.")
        else:
            self.stdout.write(self.style.SUCCESS("  오류 없이 완료되었습니다."))

        if dry_run:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN 모드: 실제 DB는 변경되지 않았습니다. "
                    "--dry-run 없이 다시 실행하면 적용됩니다."
                )
            )
