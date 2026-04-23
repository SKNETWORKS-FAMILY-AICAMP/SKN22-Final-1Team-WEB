"""
Management command: upload_style_images

로컬 이미지 파일을 Supabase Storage 의 styles/ 경로에 업로드하고,
LegacyHairstyle.image_url 을 Supabase 키(styles/xxx.jpg)로 갱신합니다.

사용법:
  # 이미지 디렉토리를 지정해 업로드
  python manage.py upload_style_images --image-dir /path/to/style/images

  # DB 에 /media/styles/... 형식으로 남아있는 기존 레코드만 마이그레이션
  python manage.py upload_style_images --migrate-only

  # 업로드 없이 현재 DB 상태만 확인
  python manage.py upload_style_images --check
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.api.v1.recommendation_logic import STYLE_CATALOG
from app.models_model_team import LegacyHairstyle
from app.services.storage_service import ensure_supabase_bucket
from app.services.supabase_client import get_supabase_client, is_supabase_configured


STYLE_IDS = {p.style_id for p in STYLE_CATALOG}
LEGACY_PREFIX = "/media/styles/"
SUPABASE_SUBDIR = "styles"


def _upload_to_supabase(client, bucket_name: str, key: str, data: bytes, mime: str) -> None:
    bucket = client.storage.from_(bucket_name)
    try:
        bucket.remove([key])
    except Exception:
        pass
    bucket.upload(key, data, file_options={"content-type": mime, "upsert": "true"})


class Command(BaseCommand):
    help = "Supabase Storage 에 스타일 이미지를 업로드하고 DB image_url 을 키 형식으로 갱신합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--image-dir",
            type=str,
            default=None,
            help="업로드할 이미지가 있는 디렉토리 경로 (예: /path/to/images). "
                 "파일명은 <style_id>.jpg 형식이어야 합니다.",
        )
        parser.add_argument(
            "--migrate-only",
            action="store_true",
            default=False,
            help="업로드 없이 DB 의 /media/styles/... 경로를 styles/... 키로만 변환합니다.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            default=False,
            help="현재 DB 상태와 Supabase 설정을 출력하고 종료합니다.",
        )
        parser.add_argument(
            "--bucket",
            type=str,
            default=None,
            help="사용할 Supabase 버킷 이름 (기본값: settings.SUPABASE_BUCKET).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        bucket_name = options["bucket"] or settings.SUPABASE_BUCKET

        # ── --check ────────────────────────────────────────────────────────────
        if options["check"]:
            self._print_status(bucket_name)
            return

        # ── --migrate-only ─────────────────────────────────────────────────────
        if options["migrate_only"]:
            count = self._migrate_legacy_keys()
            self.stdout.write(self.style.SUCCESS(f"[migrate] {count}개 레코드를 키 형식으로 변환했습니다."))
            return

        # ── 업로드 모드 ────────────────────────────────────────────────────────
        image_dir = options["image_dir"]
        if not image_dir:
            raise CommandError(
                "--image-dir, --migrate-only, --check 중 하나를 지정하세요."
            )

        image_dir_path = Path(image_dir)
        if not image_dir_path.is_dir():
            raise CommandError(f"디렉토리를 찾을 수 없습니다: {image_dir}")

        if not is_supabase_configured():
            raise CommandError(
                "Supabase 가 설정되지 않았습니다. "
                "SUPABASE_URL, SUPABASE_SECRET_KEY, SUPABASE_BUCKET 환경변수를 확인하세요."
            )

        client = get_supabase_client()
        if client is None:
            raise CommandError("Supabase 클라이언트를 생성할 수 없습니다.")

        ensure_supabase_bucket()

        # 이미지 파일 수집 (201.jpg, 202.png, … 형식)
        uploaded = 0
        skipped = 0
        for style in STYLE_CATALOG:
            sid = style.style_id
            found = None
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                candidate = image_dir_path / f"{sid}{ext}"
                if candidate.exists():
                    found = candidate
                    break

            if found is None:
                self.stdout.write(
                    self.style.WARNING(f"  [skip] style_id={sid}: {image_dir_path}/{sid}.jpg 없음")
                )
                skipped += 1
                continue

            mime, _ = mimetypes.guess_type(str(found))
            mime = mime or "image/jpeg"
            suffix = found.suffix.lower()
            if suffix == ".jpeg":
                suffix = ".jpg"

            key = f"{SUPABASE_SUBDIR}/{sid}{suffix}"
            data = found.read_bytes()

            self.stdout.write(f"  [upload] {found.name} → {key} ({len(data)//1024}KB) ...", ending="")
            try:
                _upload_to_supabase(client, bucket_name, key, data, mime)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f" 실패: {exc}"))
                continue

            # DB 갱신
            rows = LegacyHairstyle.objects.filter(hairstyle_id=sid)
            rows.update(image_url=key)
            self.stdout.write(self.style.SUCCESS(f" 완료 (DB {rows.count()}행 갱신)"))
            uploaded += 1

        # 기존 /media/styles/... 레코드도 함께 마이그레이션
        migrated = self._migrate_legacy_keys()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 업로드 {uploaded}개, 건너뜀 {skipped}개, 레거시 키 변환 {migrated}개"
            )
        )

    def _migrate_legacy_keys(self) -> int:
        """DB 에 /media/styles/xxx.jpg 형식으로 남아있는 레코드를 styles/xxx.jpg 로 변환."""
        count = 0
        for row in LegacyHairstyle.objects.filter(image_url__startswith=LEGACY_PREFIX):
            old_url = row.image_url or ""
            new_key = old_url[len(LEGACY_PREFIX):]   # "styles/201.jpg"의 파일명 부분
            new_key = f"{SUPABASE_SUBDIR}/{new_key}"  # "styles/201.jpg"
            row.image_url = new_key
            row.save(update_fields=["image_url"])
            self.stdout.write(f"  [migrate] {old_url} → {new_key}")
            count += 1
        return count

    def _print_status(self, bucket_name: str) -> None:
        from django.conf import settings

        self.stdout.write("=== Supabase 설정 ===")
        self.stdout.write(f"  SUPABASE_USE_REMOTE_STORAGE : {settings.SUPABASE_USE_REMOTE_STORAGE}")
        self.stdout.write(f"  SUPABASE_BUCKET             : {bucket_name}")
        self.stdout.write(f"  SUPABASE_BUCKET_PUBLIC      : {settings.SUPABASE_BUCKET_PUBLIC}")
        self.stdout.write(f"  SUPABASE_SIGNED_URL_EXPIRES_IN: {settings.SUPABASE_SIGNED_URL_EXPIRES_IN}s")
        self.stdout.write(f"  is_configured               : {is_supabase_configured()}")
        self.stdout.write("")
        self.stdout.write("=== LegacyHairstyle image_url 현황 ===")
        for row in LegacyHairstyle.objects.order_by("hairstyle_id"):
            status = ""
            url = row.image_url or "(없음)"
            if url.startswith(LEGACY_PREFIX):
                status = "  ← 레거시 경로 (마이그레이션 필요)"
            elif url.startswith(SUPABASE_SUBDIR + "/"):
                status = "  ← Supabase 키"
            elif url.startswith(("http://", "https://")):
                status = "  ← 외부 URL"
            self.stdout.write(f"  style_id={row.hairstyle_id:>4}  {url}{status}")
