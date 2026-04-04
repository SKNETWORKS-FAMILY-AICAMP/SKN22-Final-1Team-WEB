from rest_framework import serializers

from app.services.model_team_bridge import get_legacy_designer_id


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
    client_id = serializers.CharField()
    consultation_id = serializers.CharField()
    content = serializers.CharField()
    admin_id = serializers.CharField(required=False)

    def validate(self, attrs):
        try:
            attrs["consultation_id"] = int(str(attrs["consultation_id"]).strip())
        except (TypeError, ValueError):
            raise serializers.ValidationError({"consultation_id": "A numeric consultation identifier is required."})
        admin_id = attrs.get("admin_id")
        if admin_id not in (None, ""):
            attrs["admin_id"] = str(admin_id).strip()
        return attrs


class ConsultationCloseSerializer(serializers.Serializer):
    consultation_id = serializers.CharField()

    def validate(self, attrs):
        try:
            attrs["consultation_id"] = int(str(attrs["consultation_id"]).strip())
        except (TypeError, ValueError):
            raise serializers.ValidationError({"consultation_id": "A numeric consultation identifier is required."})
        return attrs


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


class DesignerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    legacy_id = serializers.SerializerMethodField()
    name = serializers.CharField()
    phone = serializers.CharField(required=False, allow_null=True)
    is_active = serializers.BooleanField()

    def get_legacy_id(self, obj):
        if isinstance(obj, dict):
            return obj.get("legacy_id") or obj.get("legacy_designer_id") or obj.get("designer_id")
        if not hasattr(obj, "_meta"):
            return (
                getattr(obj, "legacy_id", None)
                or getattr(obj, "legacy_designer_id", None)
                or getattr(obj, "designer_id", None)
            )
        return get_legacy_designer_id(designer=obj)

    def to_representation(self, instance):
        if isinstance(instance, dict) or not hasattr(instance, "_meta"):
            return {
                "id": (
                    getattr(instance, "backend_designer_id", None)
                    or getattr(instance, "id", None)
                    if not isinstance(instance, dict)
                    else instance.get("backend_designer_id") or instance.get("id")
                ),
                "legacy_id": self.get_legacy_id(instance),
                "name": (
                    instance.get("name") if isinstance(instance, dict) else getattr(instance, "name", None)
                ) or (
                    instance.get("designer_name") if isinstance(instance, dict) else getattr(instance, "designer_name", None)
                ),
                "phone": (
                    instance.get("phone") if isinstance(instance, dict) else getattr(instance, "phone", None)
                ) or (
                    instance.get("login_id") if isinstance(instance, dict) else getattr(instance, "login_id", None)
                ),
                "is_active": bool(
                    instance.get("is_active") if isinstance(instance, dict) else getattr(instance, "is_active", False)
                ),
            }
        return super().to_representation(instance)
