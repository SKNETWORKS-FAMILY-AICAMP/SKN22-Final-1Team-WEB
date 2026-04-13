from __future__ import annotations

from rest_framework import serializers
from rest_framework.response import Response

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

from app.api.v1.response_helpers import CompatEnvelopeAPIView
from app.trend_pipeline.latest_feed import get_latest_crawled_trends


class LatestTrendItemSerializer(serializers.Serializer):
    title = serializers.CharField()
    title_ko = serializers.CharField(required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)
    summary_ko = serializers.CharField(required=False, allow_blank=True)
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    article_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source = serializers.CharField(required=False, allow_blank=True)
    source_name = serializers.CharField(required=False, allow_blank=True)
    published_at = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    crawled_at = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True)
    keywords = serializers.ListField(child=serializers.CharField(), required=False)


class LatestTrendListSerializer(serializers.Serializer):
    status = serializers.CharField()
    source = serializers.CharField()
    count = serializers.IntegerField()
    items = LatestTrendItemSerializer(many=True)


class LatestTrendView(CompatEnvelopeAPIView):
    @extend_schema(
        summary="Get latest crawled trend cards",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: LatestTrendListSerializer},
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        payload = get_latest_crawled_trends(limit=limit)
        return Response(payload)
