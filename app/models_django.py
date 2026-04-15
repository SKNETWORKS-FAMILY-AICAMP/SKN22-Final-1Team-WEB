from django.contrib.auth.hashers import make_password
from django.db import models
import uuid
from app.services.age_profile import build_age_profile


def default_admin_pin_hash() -> str:
    return make_password("0000")


class AdminAccount(models.Model):
    id = models.UUIDField(primary_key=True, db_column='shop_id', default=uuid.uuid4)
    login_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    shop_name = models.CharField(max_length=100, null=True, blank=True)
    biz_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    owner_phone = models.CharField(max_length=20, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    admin_pin = models.CharField(max_length=255, default=default_admin_pin_hash)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    backend_admin_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    store_name = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=20, default="owner", null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    business_number = models.CharField(max_length=30, null=True, blank=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True, null=True, blank=True)
    consent_snapshot = models.JSONField(default=dict, blank=True, null=True)
    consented_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "shop"

    def __str__(self):
        return f"{self.store_name or self.shop_name} - {self.name}"

class Designer(models.Model):
    id = models.UUIDField(primary_key=True, db_column='designer_id', default=uuid.uuid4)
    shop = models.ForeignKey(AdminAccount, on_delete=models.CASCADE, db_column='shop_id')
    designer_name = models.CharField(max_length=50)
    login_id = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    backend_designer_id = models.BigIntegerField(null=True, blank=True)
    backend_shop_ref_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    pin_hash = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "designer"

    def __str__(self):
        return f"{self.name or self.designer_name}"

class Client(models.Model):
    id = models.UUIDField(primary_key=True, db_column='client_id', default=uuid.uuid4)
    shop = models.ForeignKey(AdminAccount, on_delete=models.CASCADE, db_column='shop_id')
    client_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    gender = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    backend_client_id = models.BigIntegerField(null=True, blank=True)
    backend_shop_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_designer_ref_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    assignment_source = models.CharField(max_length=30, null=True, blank=True)
    age_input = models.SmallIntegerField(null=True, blank=True)
    birth_year_estimate = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "client"

    def __str__(self):
        return f"{self.name or self.client_name} ({self.phone})"

    @property
    def age_profile(self) -> dict | None:
        return build_age_profile(birth_year_estimate=self.birth_year_estimate)

class Style(models.Model):
    id = models.AutoField(primary_key=True, db_column='hairstyle_id')
    chroma_id = models.CharField(max_length=100, unique=True)
    style_name = models.CharField(max_length=100)
    image_url = models.CharField(max_length=500)
    created_at = models.DateTimeField(null=True, blank=True)
    backend_style_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    vibe = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "hairstyle"

    def __str__(self):
        return self.name or self.style_name

class Survey(models.Model):
    id = models.AutoField(primary_key=True, db_column='survey_id')
    client = models.OneToOneField(Client, on_delete=models.CASCADE, db_column='client_id')
    hair_length = models.CharField(max_length=20, null=True, blank=True)
    hair_mood = models.CharField(max_length=20, null=True, blank=True)
    hair_condition = models.CharField(max_length=20, null=True, blank=True)
    hair_color = models.CharField(max_length=20, null=True, blank=True)
    budget = models.CharField(max_length=20, null=True, blank=True)
    preference_vector = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    backend_survey_id = models.BigIntegerField(null=True, blank=True)
    backend_client_ref_id = models.BigIntegerField(null=True, blank=True)
    target_length = models.CharField(max_length=50, null=True, blank=True)
    target_vibe = models.CharField(max_length=50, null=True, blank=True)
    scalp_type = models.CharField(max_length=50, null=True, blank=True)
    hair_colour = models.CharField(max_length=50, null=True, blank=True)
    budget_range = models.CharField(max_length=50, null=True, blank=True)
    preference_vector_json = models.JSONField(null=True, blank=True)
    created_at_ts = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "client_survey"


class DesignerDiagnosisCard(models.Model):
    id = models.BigAutoField(primary_key=True)
    admin_ref_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    designer_ref_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    hair_texture = models.CharField(max_length=20, blank=True, default="")
    damage_level = models.CharField(max_length=20, blank=True, default="")
    special_notes = models.JSONField(default=list, blank=True)
    special_memo = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    client_ref_id = models.BigIntegerField(unique=True, db_index=True)
    legacy_client_ref_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    class Meta:
        db_table = "designer_diagnosis_cards"


class ClientProfileNote(models.Model):
    id = models.BigAutoField(primary_key=True)
    client_ref_id = models.BigIntegerField(unique=True, db_index=True)
    legacy_client_ref_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    admin_ref_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    designer_ref_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    content = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_profile_notes"

# 기존에 사용하던 나머지 모델들(CaptureRecord, FaceAnalysis 등)도 필요시 동일한 방식으로 실제 DB에 맞춰 업데이트할 수 있습니다.
