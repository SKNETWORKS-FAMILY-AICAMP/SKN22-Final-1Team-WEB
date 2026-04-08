from __future__ import annotations

from rest_framework import serializers

from app.services.age_profile import (
    build_age_profile,
    build_client_age_profile,
    estimate_birth_year_from_age,
    normalize_age_input,
)
from app.services.model_team_bridge import (
    get_client_by_identifier,
    get_legacy_client_id,
    get_legacy_designer_id,
    upsert_client_record,
)


def _payload_value(instance, key: str, default=None):
    if isinstance(instance, dict):
        return instance.get(key, default)
    return getattr(instance, key, default)


class ClientSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    legacy_client_id = serializers.SerializerMethodField()
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    age_input = serializers.IntegerField(required=False, allow_null=True)
    birth_year_estimate = serializers.IntegerField(required=False, allow_null=True)
    current_age = serializers.SerializerMethodField()
    age_decade = serializers.SerializerMethodField()
    age_segment = serializers.SerializerMethodField()
    age_group = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def _profile(self, obj):
        if isinstance(obj, dict) or not hasattr(obj, "_meta"):
            return build_age_profile(
                age=_payload_value(obj, "age_input"),
                birth_year_estimate=_payload_value(obj, "birth_year_estimate"),
            ) or {}
        return build_client_age_profile(obj) or {}

    def get_legacy_client_id(self, obj):
        if isinstance(obj, dict):
            return obj.get("legacy_client_id")
        return get_legacy_client_id(client=obj)

    def get_current_age(self, obj):
        return self._profile(obj).get("current_age")

    def get_age_decade(self, obj):
        return self._profile(obj).get("age_decade")

    def get_age_segment(self, obj):
        return self._profile(obj).get("age_segment")

    def get_age_group(self, obj):
        return self._profile(obj).get("age_group")

    def to_representation(self, instance):
        if isinstance(instance, dict) or not hasattr(instance, "_meta"):
            profile = self._profile(instance)
            return {
                "id": _payload_value(instance, "id") or _payload_value(instance, "client_id"),
                "legacy_client_id": self.get_legacy_client_id(instance),
                "name": _payload_value(instance, "name") or _payload_value(instance, "client_name"),
                "gender": _payload_value(instance, "gender"),
                "phone": _payload_value(instance, "phone"),
                "age_input": _payload_value(instance, "age_input"),
                "birth_year_estimate": _payload_value(instance, "birth_year_estimate"),
                "current_age": profile.get("current_age"),
                "age_decade": profile.get("age_decade"),
                "age_segment": profile.get("age_segment"),
                "age_group": profile.get("age_group"),
                "created_at": _payload_value(instance, "created_at"),
            }
        return {
            "id": getattr(instance, "id", None),
            "legacy_client_id": self.get_legacy_client_id(instance),
            "name": getattr(instance, "name", None),
            "gender": getattr(instance, "gender", None),
            "phone": getattr(instance, "phone", None),
            "age_input": getattr(instance, "age_input", None),
            "birth_year_estimate": getattr(instance, "birth_year_estimate", None),
            "current_age": self.get_current_age(instance),
            "age_decade": self.get_age_decade(instance),
            "age_segment": self.get_age_segment(instance),
            "age_group": self.get_age_group(instance),
            "created_at": getattr(instance, "created_at", None),
        }


class StyleSerializer(serializers.Serializer):
    style_id = serializers.IntegerField(required=False, allow_null=True)
    hairstyle_id = serializers.IntegerField(required=False, allow_null=True)
    backend_style_id = serializers.IntegerField(required=False, allow_null=True)
    chroma_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    style_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    vibe = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def to_representation(self, instance):
        return {
            "style_id": _payload_value(instance, "style_id") or _payload_value(instance, "backend_style_id"),
            "hairstyle_id": _payload_value(instance, "hairstyle_id"),
            "backend_style_id": _payload_value(instance, "backend_style_id"),
            "chroma_id": _payload_value(instance, "chroma_id"),
            "name": _payload_value(instance, "name"),
            "style_name": _payload_value(instance, "style_name") or _payload_value(instance, "name"),
            "image_url": _payload_value(instance, "image_url"),
            "description": _payload_value(instance, "description") or "",
            "keywords": list(_payload_value(instance, "keywords", []) or []),
            "vibe": _payload_value(instance, "vibe"),
            "created_at": _payload_value(instance, "created_at"),
        }


class SurveySerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    client = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    q1 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    q2 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    q3 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    q4 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    q5 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    q6 = serializers.CharField(required=False, allow_blank=True, write_only=True)
    target_length = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    target_vibe = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    scalp_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hair_colour = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    budget_range = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    preference_vector = serializers.ListField(
        child=serializers.FloatField(),
        required=False,
        allow_empty=True,
    )
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def to_representation(self, instance):
        if isinstance(instance, dict) or not hasattr(instance, "_meta"):
            return {
                "id": _payload_value(instance, "id") or _payload_value(instance, "survey_id"),
                "client": _payload_value(instance, "client") or _payload_value(instance, "client_id"),
                "target_length": _payload_value(instance, "target_length") or _payload_value(instance, "hair_length"),
                "target_vibe": _payload_value(instance, "target_vibe") or _payload_value(instance, "hair_mood"),
                "scalp_type": _payload_value(instance, "scalp_type") or _payload_value(instance, "hair_condition"),
                "hair_colour": _payload_value(instance, "hair_colour") or _payload_value(instance, "hair_color"),
                "budget_range": _payload_value(instance, "budget_range") or _payload_value(instance, "budget"),
                "preference_vector": _payload_value(instance, "preference_vector") or _payload_value(instance, "preference_vector_json") or [],
                "created_at": _payload_value(instance, "created_at") or _payload_value(instance, "created_at_ts"),
            }
        return {
            "id": getattr(instance, "id", None),
            "client": getattr(instance, "client_id", None),
            "target_length": getattr(instance, "target_length", None),
            "target_vibe": getattr(instance, "target_vibe", None),
            "scalp_type": getattr(instance, "scalp_type", None),
            "hair_colour": getattr(instance, "hair_colour", None),
            "budget_range": getattr(instance, "budget_range", None),
            "preference_vector": getattr(instance, "preference_vector", None) or [],
            "created_at": getattr(instance, "created_at", None),
        }


class FaceAnalysisSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    client = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    face_shape = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    golden_ratio_score = serializers.FloatField(required=False, allow_null=True)
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    landmark_snapshot = serializers.JSONField(required=False)
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def to_representation(self, instance):
        return {
            "id": _payload_value(instance, "id"),
            "client": _payload_value(instance, "client_id"),
            "face_shape": _payload_value(instance, "face_shape") or _payload_value(instance, "face_type"),
            "golden_ratio_score": _payload_value(instance, "golden_ratio_score"),
            "image_url": (
                _payload_value(instance, "image_url")
                or _payload_value(instance, "processed_path")
                or _payload_value(instance, "original_image_url")
            ),
            "landmark_snapshot": (
                _payload_value(instance, "landmark_snapshot")
                or _payload_value(instance, "analysis_landmark_snapshot")
                or {}
            ),
            "created_at": _payload_value(instance, "created_at"),
        }


class StyleSelectionSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    client = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    legacy_client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    style_id = serializers.IntegerField(required=False, allow_null=True)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    match_score = serializers.FloatField(required=False, allow_null=True)
    is_sent_to_admin = serializers.BooleanField(required=False)
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def to_representation(self, instance):
        return {
            "id": _payload_value(instance, "selection_id") or _payload_value(instance, "id") or _payload_value(instance, "result_id"),
            "client": _payload_value(instance, "client_id"),
            "legacy_client_id": _payload_value(instance, "legacy_client_id"),
            "style_id": _payload_value(instance, "style_id"),
            "source": _payload_value(instance, "source"),
            "match_score": _payload_value(instance, "match_score"),
            "is_sent_to_admin": bool(
                _payload_value(instance, "is_sent_to_admin")
                or _payload_value(instance, "is_active")
                or _payload_value(instance, "is_confirmed")
            ),
            "created_at": _payload_value(instance, "created_at") or _payload_value(instance, "last_activity_at"),
        }


class FormerRecommendationSerializer(serializers.Serializer):
    recommendation_id = serializers.IntegerField(required=False)
    legacy_client_id = serializers.SerializerMethodField()
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    style_id = serializers.IntegerField(required=False, allow_null=True)
    style_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    style_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    sample_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    simulation_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    synthetic_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    llm_explanation = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    reasoning = serializers.SerializerMethodField()
    reasoning_snapshot = serializers.JSONField(required=False)
    image_policy = serializers.SerializerMethodField()
    can_regenerate_simulation = serializers.SerializerMethodField()
    regeneration_remaining_count = serializers.SerializerMethodField()
    regeneration_policy = serializers.SerializerMethodField()
    match_score = serializers.FloatField(required=False, allow_null=True)
    rank = serializers.IntegerField(required=False, allow_null=True)
    is_chosen = serializers.BooleanField(required=False)
    created_at = serializers.DateTimeField(required=False, allow_null=True)

    def get_reasoning(self, obj):
        snapshot = _payload_value(obj, "reasoning_snapshot", {}) or {}
        return snapshot.get("summary") or _payload_value(obj, "llm_explanation") or ""

    def get_legacy_client_id(self, obj):
        def _from_client_value(client_value):
            if hasattr(client_value, "_meta") and hasattr(client_value, "id") and hasattr(client_value, "phone"):
                return get_legacy_client_id(client=client_value)
            if isinstance(client_value, str) and client_value and not client_value.isdigit():
                return client_value
            try:
                client_pk = int(client_value)
            except (TypeError, ValueError):
                return None
            client = get_client_by_identifier(identifier=client_pk)
            return get_legacy_client_id(client=client) if client is not None else None

        if isinstance(obj, dict):
            legacy_client_id = obj.get("legacy_client_id")
            if legacy_client_id:
                return legacy_client_id
            return _from_client_value(obj.get("client") or obj.get("client_id"))
        if not hasattr(obj, "_meta"):
            legacy_client_id = getattr(obj, "legacy_client_id", None)
            if legacy_client_id:
                return legacy_client_id
            return _from_client_value(getattr(obj, "client", None) or getattr(obj, "client_id", None))
        return get_legacy_client_id(client=obj.client)

    def get_image_policy(self, obj):
        return "vector_only" if _payload_value(obj, "regeneration_snapshot") else "legacy_asset_store"

    def get_can_regenerate_simulation(self, obj):
        attempts_used = int((_payload_value(obj, "reasoning_snapshot", {}) or {}).get("regeneration_attempts_used") or 0)
        return bool(_payload_value(obj, "regeneration_snapshot")) and attempts_used < 1

    def get_regeneration_remaining_count(self, obj):
        attempts_used = int((_payload_value(obj, "reasoning_snapshot", {}) or {}).get("regeneration_attempts_used") or 0)
        return max(0, 1 - attempts_used) if _payload_value(obj, "regeneration_snapshot") else 0

    def get_regeneration_policy(self, obj):
        if not _payload_value(obj, "regeneration_snapshot"):
            return None
        attempts_used = int((_payload_value(obj, "reasoning_snapshot", {}) or {}).get("regeneration_attempts_used") or 0)
        return {
            "mode": "single_retry",
            "seed_strategy": "vary_seed",
            "selection_bias": "face_ratio_preference_boost",
            "trend_bias": "reduced",
            "attempts_allowed": 1,
            "attempts_used": attempts_used,
        }

    def to_representation(self, instance):
        payload = dict(instance) if isinstance(instance, dict) else {}
        payload.setdefault("recommendation_id", _payload_value(instance, "recommendation_id") or _payload_value(instance, "id"))
        payload.setdefault("legacy_client_id", self.get_legacy_client_id(instance))
        payload.setdefault("style_id", _payload_value(instance, "style_id") or _payload_value(instance, "style_id_snapshot"))
        payload.setdefault("style_name", _payload_value(instance, "style_name") or _payload_value(instance, "style_name_snapshot"))
        payload.setdefault("style_description", _payload_value(instance, "style_description") or _payload_value(instance, "style_description_snapshot") or "")
        payload.setdefault("synthetic_image_url", _payload_value(instance, "synthetic_image_url") or _payload_value(instance, "simulation_image_url"))
        payload.setdefault("keywords", list(_payload_value(instance, "keywords", []) or []))
        payload.setdefault("reasoning_snapshot", _payload_value(instance, "reasoning_snapshot", {}) or {})
        payload.setdefault("reasoning", self.get_reasoning(payload))
        payload.setdefault("image_policy", self.get_image_policy(payload))
        payload.setdefault("can_regenerate_simulation", self.get_can_regenerate_simulation(payload))
        payload.setdefault("regeneration_remaining_count", self.get_regeneration_remaining_count(payload))
        payload.setdefault("regeneration_policy", self.get_regeneration_policy(payload))
        payload.setdefault("created_at", _payload_value(instance, "created_at"))
        return payload


class RecommendationCardSerializer(serializers.Serializer):
    recommendation_id = serializers.IntegerField(required=False)
    legacy_client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    source = serializers.CharField()
    style_id = serializers.IntegerField()
    style_name = serializers.CharField()
    style_description = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)
    sample_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    display_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    simulation_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    synthetic_image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    has_displayable_simulation = serializers.BooleanField(required=False)
    simulation_source = serializers.CharField(required=False)
    simulation_status = serializers.CharField(required=False)
    simulation_status_reason = serializers.CharField(required=False)
    llm_explanation = serializers.CharField(required=False, allow_blank=True)
    reasoning = serializers.CharField(required=False, allow_blank=True)
    reasoning_snapshot = serializers.JSONField(required=False)
    image_policy = serializers.CharField(required=False)
    can_regenerate_simulation = serializers.BooleanField(required=False)
    regeneration_remaining_count = serializers.IntegerField(required=False)
    regeneration_policy = serializers.JSONField(required=False)
    match_score = serializers.FloatField(required=False)
    rank = serializers.IntegerField(required=False)
    is_chosen = serializers.BooleanField(required=False)
    created_at = serializers.DateTimeField(required=False)


class RecommendationListResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    client_id = serializers.IntegerField(required=False)
    legacy_client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source = serializers.CharField(required=False)
    response_kind = serializers.CharField(required=False)
    response_contract_version = serializers.IntegerField(required=False)
    canonical_display_image_field = serializers.CharField(required=False)
    primary_simulation_image_field = serializers.CharField(required=False)
    legacy_simulation_image_field = serializers.CharField(required=False)
    display_gate_target_field = serializers.CharField(required=False)
    display_gate_status = serializers.CharField(required=False)
    display_gate_reason = serializers.CharField(required=False)
    display_gate_ready_count = serializers.IntegerField(required=False)
    display_gate_target_count = serializers.IntegerField(required=False)
    batch_id = serializers.UUIDField(required=False, allow_null=True)
    days = serializers.IntegerField(required=False)
    trend_scope = serializers.CharField(required=False)
    age_profile = serializers.JSONField(required=False)
    message = serializers.CharField(required=False)
    recommendation_stage = serializers.CharField(required=False)
    can_retry_recommendations = serializers.BooleanField(required=False)
    retry_recommendations_remaining_count = serializers.IntegerField(required=False)
    retry_recommendations_policy = serializers.JSONField(required=False)
    recommendation_item_count = serializers.IntegerField(required=False)
    has_displayable_simulation = serializers.BooleanField(required=False)
    simulation_ready = serializers.BooleanField(required=False)
    displayable_simulation_count = serializers.IntegerField(required=False)
    primary_simulation_count = serializers.IntegerField(required=False)
    sample_reference_count = serializers.IntegerField(required=False)
    local_mock_count = serializers.IntegerField(required=False)
    simulation_status_reason = serializers.CharField(required=False)
    current_capture_id = serializers.IntegerField(required=False, allow_null=True)
    current_analysis_id = serializers.IntegerField(required=False, allow_null=True)
    next_action = serializers.CharField(required=False)
    next_actions = serializers.ListField(child=serializers.CharField(), required=False)
    items = RecommendationCardSerializer(many=True)


class RetryRecommendationRequestSerializer(serializers.Serializer):
    client_id = serializers.CharField(required=False)
    customer_id = serializers.CharField(required=False)
    customer = serializers.CharField(required=False)


class RegenerateSimulationRequestSerializer(serializers.Serializer):
    recommendation_id = serializers.IntegerField(required=False)
    regeneration_snapshot = serializers.JSONField(required=False)
    style_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        recommendation_id = attrs.get("recommendation_id")
        regeneration_snapshot = attrs.get("regeneration_snapshot")
        style_id = attrs.get("style_id")
        if recommendation_id is None and regeneration_snapshot is None:
            raise serializers.ValidationError(
                {"recommendation_id": "Provide recommendation_id or regeneration_snapshot."}
            )
        if recommendation_id is None and style_id is None:
            raise serializers.ValidationError(
                {"style_id": "style_id is required when regeneration_snapshot is provided directly."}
            )
        return attrs


class TokenRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class ConsultationRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    client = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    legacy_client_id = serializers.SerializerMethodField()
    designer = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    legacy_designer_id = serializers.SerializerMethodField()
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    is_read = serializers.BooleanField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    closed_at = serializers.DateTimeField(required=False, allow_null=True)

    def get_legacy_client_id(self, obj):
        if isinstance(obj, dict):
            return obj.get("legacy_client_id")
        return get_legacy_client_id(client=obj.client)

    def get_legacy_designer_id(self, obj):
        if isinstance(obj, dict):
            return obj.get("legacy_designer_id")
        if getattr(obj, "designer_id", None) and getattr(obj, "designer", None):
            return get_legacy_designer_id(designer=obj.designer)
        client = getattr(obj, "client", None)
        if getattr(client, "designer_id", None) and getattr(client, "designer", None):
            return get_legacy_designer_id(designer=client.designer)
        return None

    def to_representation(self, instance):
        if isinstance(instance, dict) or not hasattr(instance, "_meta"):
            return {
                "id": _payload_value(instance, "consultation_id") or _payload_value(instance, "id"),
                "client": _payload_value(instance, "client_id"),
                "legacy_client_id": self.get_legacy_client_id(instance),
                "designer": _payload_value(instance, "designer_id"),
                "legacy_designer_id": self.get_legacy_designer_id(instance),
                "status": _payload_value(instance, "status"),
                "is_active": bool(_payload_value(instance, "is_active")),
                "is_read": not bool(_payload_value(instance, "has_unread_consultation")),
                "source": _payload_value(instance, "source"),
                "created_at": _payload_value(instance, "created_at") or _payload_value(instance, "last_activity_at"),
                "closed_at": _payload_value(instance, "closed_at"),
            }
        return {
            "id": getattr(instance, "id", None),
            "client": getattr(instance, "client_id", None),
            "legacy_client_id": self.get_legacy_client_id(instance),
            "designer": getattr(instance, "designer_id", None),
            "legacy_designer_id": self.get_legacy_designer_id(instance),
            "status": getattr(instance, "status", None),
            "is_active": bool(getattr(instance, "is_active", False)),
            "is_read": bool(getattr(instance, "is_read", False)),
            "source": getattr(instance, "source", None),
            "created_at": getattr(instance, "created_at", None),
            "closed_at": getattr(instance, "closed_at", None),
        }


class ClientCheckSerializer(serializers.Serializer):
    phone = serializers.CharField()


class ClientRegisterSerializer(serializers.Serializer):
    name = serializers.CharField()
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField()
    age = serializers.IntegerField(required=False)
    ages = serializers.IntegerField(required=False)

    def validate(self, attrs):
        raw_age = attrs.pop("age", None)
        if raw_age is None:
            raw_age = attrs.pop("ages", None)
        try:
            age = normalize_age_input(raw_age)
        except ValueError as exc:
            raise serializers.ValidationError({"age": str(exc)}) from exc

        attrs["age_input"] = age
        attrs["birth_year_estimate"] = estimate_birth_year_from_age(age)
        return attrs

    def create(self, validated_data):
        return upsert_client_record(
            phone=validated_data["phone"],
            name=validated_data["name"],
            gender=validated_data.get("gender"),
            age_input=validated_data.get("age_input"),
            birth_year_estimate=validated_data.get("birth_year_estimate"),
        )
