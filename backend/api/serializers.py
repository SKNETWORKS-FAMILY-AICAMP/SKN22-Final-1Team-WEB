from rest_framework import serializers
from .models import Customer, Style, Survey, CaptureRecord, FaceAnalysis, StyleSelection, ConsultationRequest

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class StyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Style
        fields = '__all__'

class SurveySerializer(serializers.ModelSerializer):
    target_length = serializers.ChoiceField(choices=["쇼트", "보브", "세미롱", "롱"], help_text="희망하는 머리 길이")
    target_vibe = serializers.ChoiceField(choices=["귀여움", "시크함", "자연스러움", "우아함"], help_text="희망하는 분위기")
    scalp_type = serializers.ChoiceField(choices=["직모", "웨이브", "곱슬", "손상모"], help_text="두피/모발 상태")
    hair_colour = serializers.ChoiceField(choices=["블랙", "브라운", "애쉬", "블리치"], help_text="현재 모발 색상")
    budget_range = serializers.ChoiceField(choices=["3만 이하", "3만 ~ 5만", "5만~ 10만", "10만 이상"], help_text="예상 예산 범위")

    class Meta:
        model = Survey
        fields = ['id', 'customer', 'target_length', 'target_vibe', 'scalp_type', 'hair_colour', 'budget_range', 'preference_vector', 'created_at']
        read_only_fields = ['id', 'preference_vector', 'created_at']

class CaptureRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaptureRecord
        fields = '__all__'

class FaceAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaceAnalysis
        fields = '__all__'

class StyleSelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StyleSelection
        fields = '__all__'

class ConsultationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsultationRequest
        fields = '__all__'

class RecommendationSerializer(serializers.Serializer):
    style_id = serializers.IntegerField()
    style_name = serializers.CharField()
    match_score = serializers.FloatField()
    reasoning = serializers.CharField()
    synthetic_image_url = serializers.CharField(required=False, allow_null=True)
