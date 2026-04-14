from django.db import models


class LegacyShop(models.Model):
    shop_id = models.CharField(primary_key=True, max_length=255)
    login_id = models.CharField(max_length=255)
    shop_name = models.CharField(max_length=255)
    biz_number = models.CharField(max_length=255, null=True, blank=True)
    owner_phone = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255)
    admin_pin = models.CharField(max_length=255)
    created_at = models.TextField()
    updated_at = models.TextField()
    backend_admin_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    store_name = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=20, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    business_number = models.CharField(max_length=30, null=True, blank=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(null=True, blank=True)
    consent_snapshot = models.JSONField(null=True, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "shop"


class LegacyDesigner(models.Model):
    designer_id = models.CharField(primary_key=True, max_length=255)
    shop_id = models.CharField(max_length=255)
    designer_name = models.CharField(max_length=255)
    login_id = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    is_active = models.BooleanField()
    created_at = models.TextField()
    updated_at = models.TextField()
    backend_designer_id = models.BigIntegerField(null=True, blank=True)
    backend_shop_ref_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    pin_hash = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "designer"


class LegacyClient(models.Model):
    client_id = models.CharField(primary_key=True, max_length=255)
    shop_id = models.CharField(max_length=255)
    client_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)
    gender = models.CharField(max_length=50)
    created_at = models.TextField()
    updated_at = models.TextField()
    backend_client_id = models.BigIntegerField(null=True, blank=True)
    backend_shop_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_designer_ref_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    assignment_source = models.CharField(max_length=30, null=True, blank=True)
    age_input = models.SmallIntegerField(null=True, blank=True)
    birth_year_estimate = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "client"


class LegacyClientSurvey(models.Model):
    survey_id = models.IntegerField(primary_key=True)
    client_id = models.CharField(max_length=255)
    hair_length = models.CharField(max_length=255, null=True, blank=True)
    hair_mood = models.CharField(max_length=255, null=True, blank=True)
    hair_condition = models.CharField(max_length=255, null=True, blank=True)
    hair_color = models.CharField(max_length=255, null=True, blank=True)
    budget = models.CharField(max_length=255, null=True, blank=True)
    preference_vector = models.TextField()
    updated_at = models.TextField()
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
        managed = False
        db_table = "client_survey"


class LegacyClientAnalysis(models.Model):
    analysis_id = models.IntegerField(primary_key=True)
    client_id = models.CharField(max_length=255)
    designer_id = models.CharField(max_length=255, null=True, blank=True)
    original_image_url = models.TextField(null=True, blank=True)
    face_type = models.CharField(max_length=255, null=True, blank=True)
    face_ratio_vector = models.TextField()
    golden_ratio_score = models.FloatField(null=True, blank=True)
    landmark_data = models.TextField(null=True, blank=True)
    created_at = models.TextField()
    backend_analysis_id = models.BigIntegerField(null=True, blank=True)
    backend_client_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_designer_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_capture_record_id = models.BigIntegerField(null=True, blank=True)
    processed_path = models.CharField(max_length=500, null=True, blank=True)
    filename = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, null=True, blank=True)
    face_count = models.IntegerField(null=True, blank=True)
    error_note = models.TextField(null=True, blank=True)
    updated_at_ts = models.DateTimeField(null=True, blank=True)
    deidentified_path = models.CharField(max_length=500, null=True, blank=True)
    capture_landmark_snapshot = models.JSONField(null=True, blank=True)
    privacy_snapshot = models.JSONField(null=True, blank=True)
    analysis_image_url = models.CharField(max_length=500, null=True, blank=True)
    analysis_landmark_snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "client_analysis"


class LegacyClientResult(models.Model):
    result_id = models.AutoField(primary_key=True)
    analysis_id = models.IntegerField()
    client_id = models.CharField(max_length=255)
    selected_hairstyle_id = models.IntegerField(null=True, blank=True)
    selected_image_url = models.TextField(null=True, blank=True)
    is_confirmed = models.BooleanField()
    created_at = models.TextField()
    updated_at = models.TextField()
    backend_selection_id = models.BigIntegerField(null=True, blank=True)
    backend_consultation_id = models.BigIntegerField(null=True, blank=True)
    backend_client_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_admin_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_designer_ref_id = models.BigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=30, null=True, blank=True)
    survey_snapshot = models.JSONField(null=True, blank=True)
    analysis_data_snapshot = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, null=True, blank=True)
    is_active = models.BooleanField(null=True, blank=True)
    is_read = models.BooleanField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    selected_recommendation_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "client_result"


class LegacyClientResultDetail(models.Model):
    detail_id = models.AutoField(primary_key=True)
    result_id = models.IntegerField()
    hairstyle_id = models.IntegerField()
    rank = models.IntegerField()
    similarity_score = models.FloatField()
    final_score = models.FloatField(null=True, blank=True)
    simulated_image_url = models.TextField(null=True, blank=True)
    recommendation_reason = models.TextField(null=True, blank=True)
    backend_recommendation_id = models.BigIntegerField(null=True, blank=True)
    backend_client_ref_id = models.BigIntegerField(null=True, blank=True)
    backend_capture_record_id = models.BigIntegerField(null=True, blank=True)
    batch_id = models.UUIDField(null=True, blank=True)
    source = models.CharField(max_length=20, null=True, blank=True)
    style_name_snapshot = models.CharField(max_length=100, null=True, blank=True)
    style_description_snapshot = models.TextField(null=True, blank=True)
    keywords_json = models.JSONField(null=True, blank=True)
    sample_image_url = models.CharField(max_length=500, null=True, blank=True)
    regeneration_snapshot = models.JSONField(null=True, blank=True)
    reasoning_snapshot = models.JSONField(null=True, blank=True)
    is_chosen = models.BooleanField(null=True, blank=True)
    chosen_at = models.DateTimeField(null=True, blank=True)
    is_sent_to_admin = models.BooleanField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at_ts = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "client_result_detail"


class LegacyHairstyle(models.Model):
    hairstyle_id = models.IntegerField(primary_key=True)
    chroma_id = models.CharField(max_length=255)
    style_name = models.CharField(max_length=255)
    image_url = models.TextField()
    created_at = models.TextField()
    backend_style_id = models.BigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    vibe = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "hairstyle"
