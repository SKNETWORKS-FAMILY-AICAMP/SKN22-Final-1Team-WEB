from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=50)
    gender = models.CharField(max_length=10, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customers'

    def __str__(self):
        return f"{self.name} ({self.phone})"

class Style(models.Model):
    name = models.CharField(max_length=100)
    vibe = models.CharField(max_length=50) # Trendy, Chic, etc.
    description = models.TextField(null=True, blank=True)
    image_url = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'styles'

    def __str__(self):
        return self.name

class Survey(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='survey', db_index=True)
    
    # Survey fields (Enums based)
    target_length = models.CharField(max_length=50) # From CurrentLength enum
    target_vibe = models.CharField(max_length=50)
    scalp_type = models.CharField(max_length=50)
    hair_colour = models.CharField(max_length=50)
    budget_range = models.CharField(max_length=50)

    preference_vector = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'surveys'

class CaptureRecord(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='captures', db_index=True)
    
    original_path = models.CharField(max_length=500)
    processed_path = models.CharField(max_length=500)
    filename = models.CharField(max_length=255)
    
    status = models.CharField(max_length=50, default='PENDING', db_index=True)
    face_count = models.IntegerField(null=True, blank=True)
    
    error_note = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'capture_records'

class FaceAnalysis(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='face_analyses', db_index=True)
    face_shape = models.CharField(max_length=50, null=True, blank=True)
    golden_ratio_score = models.FloatField(null=True, blank=True)
    image_url = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'face_analyses'

class StyleSelection(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='style_selections', db_index=True)
    style_id = models.IntegerField()
    match_score = models.FloatField(null=True, blank=True)
    is_sent_to_designer = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'style_selections'

class ConsultationRequest(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='consultations', db_index=True)
    selected_style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, blank=True)
    
    # 분석 데이터 요약 (전송용)
    analysis_data_snapshot = models.JSONField(null=True, blank=True)
    
    status = models.CharField(max_length=20, default='SENT') # SENT, RECEIVED, COMPLETED
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'consultation_requests'
