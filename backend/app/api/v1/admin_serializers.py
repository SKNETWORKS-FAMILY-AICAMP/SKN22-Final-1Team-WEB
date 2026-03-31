from rest_framework import serializers


class AdminRegisterSerializer(serializers.Serializer):
    name = serializers.CharField()
    store_name = serializers.CharField()
    role = serializers.CharField(required=False, default="owner")
    phone = serializers.CharField()
    business_number = serializers.CharField()
    password = serializers.CharField(write_only=True)
    agree_terms = serializers.BooleanField()
    agree_privacy = serializers.BooleanField()
    agree_third_party_sharing = serializers.BooleanField()
    agree_marketing = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        required_flags = {
            "agree_terms": "이용약관 동의가 필요합니다.",
            "agree_privacy": "개인정보 수집 및 이용 동의가 필요합니다.",
            "agree_third_party_sharing": "제3자 제공 동의가 필요합니다.",
        }
        for key, message in required_flags.items():
            if not attrs.get(key):
                raise serializers.ValidationError({key: message})
        return attrs


class AdminLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class AdminClientSearchSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)


class ConsultationNoteCreateSerializer(serializers.Serializer):
    client_id = serializers.IntegerField()
    consultation_id = serializers.IntegerField()
    content = serializers.CharField()
    admin_id = serializers.IntegerField(required=False)


class ConsultationCloseSerializer(serializers.Serializer):
    consultation_id = serializers.IntegerField()


class ChatbotAskSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AdminTrendFilterSerializer(serializers.Serializer):
    days = serializers.IntegerField(required=False, default=7)
    target_length = serializers.CharField(required=False, allow_blank=True)
    target_vibe = serializers.CharField(required=False, allow_blank=True)
    scalp_type = serializers.CharField(required=False, allow_blank=True)
    hair_colour = serializers.CharField(required=False, allow_blank=True)
    budget_range = serializers.CharField(required=False, allow_blank=True)
    age_decade = serializers.CharField(required=False, allow_blank=True)
    age_segment = serializers.CharField(required=False, allow_blank=True)
    age_group = serializers.CharField(required=False, allow_blank=True)

