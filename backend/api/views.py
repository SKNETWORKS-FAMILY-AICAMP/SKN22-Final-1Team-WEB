from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, parsers
from django.shortcuts import get_object_or_404
from .models import Customer, Survey, CaptureRecord, FaceAnalysis, Style, StyleSelection, ConsultationRequest
from .serializers import (
    CustomerSerializer, SurveySerializer, CaptureRecordSerializer, 
    FaceAnalysisSerializer, StyleSerializer, StyleSelectionSerializer,
    ConsultationRequestSerializer, RecommendationSerializer
)
from .services import run_mirrai_analysis_pipeline
import threading
import uuid
import os
from django.conf import settings
from PIL import Image, ImageOps
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, OpenApiExample

class LoginView(APIView):
    @extend_schema(
        summary="사용자 로그인",
        description="전화번호를 입력하여 로그인하고 토큰을 발급받습니다. (테스트용: 010-9999-8888)",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'phone': {'type': 'string', 'example': '010-9999-8888', 'description': '사용자 전화번호 (하이픈 포함 가능)'}
                }
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "테스트 로그인 예시",
                value={"phone": "010-9999-8888"}
            )
        ]
    )
    def post(self, request):
        phone = request.data.get('phone', '').replace('-', '').strip()
        if not phone:
            return Response({"detail": "전화번호가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)
        
        customer = Customer.objects.filter(phone=phone).first()
        if not customer:
            return Response({"detail": "사용자를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        
        # 간단한 토큰 시뮬레이션 (실제 프로젝트에서는 JWT 사용 권장)
        token = f"mock-token-{customer.id}"
        
        return Response({
            "access_token": token,
            "token_type": "bearer",
            "customer_id": customer.id
        })

class SurveyView(APIView):
    @extend_schema(
        summary="스타일 설문 제출",
        description="고객의 스타일 선호도를 저장합니다. (로그인 후 받은 customer_id를 필수 입력하세요.)",
        request=SurveySerializer,
        responses={200: SurveySerializer},
        examples=[
            OpenApiExample(
                "설문 데이터 예시",
                value={
                    "customer": 1,
                    "target_length": "보브",
                    "target_vibe": "시크함",
                    "scalp_type": "직모",
                    "hair_colour": "블랙",
                    "budget_range": "3만 ~ 5만"
                }
            )
        ]
    )
    def post(self, request):
        customer_id = request.data.get('customer') or request.data.get('customer_id')
        customer = get_object_or_404(Customer, id=customer_id)
        
        # 기존 설문이 있으면 업데이트, 없으면 생성
        survey, created = Survey.objects.update_or_create(
            customer=customer,
            defaults={
                'target_length': request.data.get('target_length'),
                'target_vibe': request.data.get('target_vibe'),
                'scalp_type': request.data.get('scalp_type'),
                'hair_colour': request.data.get('hair_colour'),
                'budget_range': request.data.get('budget_range'),
                'preference_vector': [0.5] * 20  # 시뮬레이션용 벡터
            }
        )
        return Response(SurveySerializer(survey).data)

class CaptureUploadView(APIView):
    parser_classes = (parsers.MultiPartParser, parsers.FormParser)

    @extend_schema(
        summary="Capture Process (사진 업로드)",
        description="고객의 얼굴 사진을 업로드하고 AI 분석을 시작합니다. 추천 결과 페이지의 'Capture' 버튼과 연결됩니다.",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'customer_id': {'type': 'integer', 'description': '고객 ID'},
                    'file': {'type': 'string', 'format': 'binary', 'description': '분석할 얼굴 이미지 파일'}
                },
                'required': ['customer_id', 'file']
            }
        },
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        customer_id = request.data.get('customer_id') # 실제로는 토큰에서 가져와야 함
        customer = get_object_or_404(Customer, id=customer_id)
        file_obj = request.FILES.get('file')
        
        if not file_obj:
            return Response({"detail": "파일이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 이미지 저장 로직
        ext = os.path.splitext(file_obj.name)[1]
        filename = f"{uuid.uuid4()}{ext}"
        upload_path = os.path.join(settings.MEDIA_ROOT, 'captures', filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        
        with open(upload_path, 'wb+') as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)

        # 전처리 이미지 생성 시뮬레이션
        processed_path = upload_path + ".processed.jpg"
        with Image.open(upload_path) as img:
            img = ImageOps.exif_transpose(img)
            img.convert('RGB').save(processed_path, "JPEG")

        record = CaptureRecord.objects.create(
            customer=customer,
            original_path=upload_path,
            processed_path=processed_path,
            filename=file_obj.name,
            status='PENDING'
        )

        # 백그라운드 태스크 실행 (Celery 대신 Threading 시뮬레이션)
        threading.Thread(target=run_mirrai_analysis_pipeline, args=(record.id,)).start()

        return Response({"status": "success", "record_id": record.id})

class RecommendationView(APIView):
    @extend_schema(
        summary="Load Former Recommendations (과거 추천 내역 포함 조회)",
        description="가장 최근의 분석 결과와 설문 데이터를 바탕으로 맞춤 스타일을 추천합니다. 과거 내역이 있는 경우 이를 우선 로드합니다. (이후 사용자가 새 사진 촬영을 원할 경우 'Capture Process'로 이동할 수 있습니다.)",
        parameters=[
            OpenApiParameter("customer_id", OpenApiTypes.INT, OpenApiParameter.QUERY, description="고객 ID", required=True)
        ],
        responses={200: RecommendationSerializer(many=True)}
    )
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        customer = get_object_or_404(Customer, id=customer_id)
        
        latest_analysis = FaceAnalysis.objects.filter(customer=customer).order_by('-created_at').first()
        latest_survey = Survey.objects.filter(customer=customer).order_by('-created_at').first()
        
        # 분석 데이터가 없더라도 시뮬레이션을 위해 기본 결과 반환
        face_shape = latest_analysis.face_shape if latest_analysis else "계란형"
        
        mock_results = [
            {
                "style_id": 201,
                "style_name": "시크 보브",
                "match_score": 95.5,
                "reasoning": f"고객님의 {face_shape} 얼굴형에 가장 잘 어울리는 스타일입니다.",
                "synthetic_image_url": f"/media/synthetic/{customer_id}_201.jpg"
            },
            {
                "style_id": 202,
                "style_name": "내추럴 볼륨 펌",
                "match_score": 88.0,
                "reasoning": "설문조사에서 선택하신 분위기에 적합한 스타일입니다.",
                "synthetic_image_url": f"/media/synthetic/{customer_id}_202.jpg"
            }
        ]
        
        return Response(mock_results)

class TrendView(APIView):
    @extend_schema(
        summary="Load Trend Datas (매장 인기 트렌드 조회)",
        description="매장 내 최근 인기 스타일 Top-10 리스트를 반환합니다. 추천 결과 페이지의 'Trend' 버튼과 연결됩니다. (이후 사용자가 추천 결과에 만족하지 못할 경우 'Capture Process'로 이동할 수 있습니다.)",
        responses={200: StyleSerializer(many=True)}
    )
    def get(self, request):
        """
        매장 내 최근 인기 스타일 Top-10 조회
        """
        from django.db.models import Count
        from .models import StyleSelection, Style
        
        # 실제 데이터 집계 (StyleSelection 기반)
        popular_style_ids = StyleSelection.objects.values('style_id') \
            .annotate(selection_count=Count('id')) \
            .order_by('-selection_count')[:10]
        
        results = []
        for item in popular_style_ids:
            sid = item['style_id']
            # Style 테이블에 정보가 있으면 가져오고, 없으면 Mock 데이터 생성
            style = Style.objects.filter(id=sid).first()
            if style:
                results.append(StyleSerializer(style).data)
            else:
                # 초기 데이터를 위한 Mock 리스트 (Style 테이블이 비어있을 경우 대비)
                results.append({
                    "id": sid,
                    "name": f"인기 스타일 {sid}",
                    "vibe": "Trendy",
                    "description": "매장에서 최근 가장 많이 선택된 스타일입니다.",
                    "match_score": 90.0
                })
        
        # 데이터가 아예 없는 경우를 위한 최소 Mock
        if not results:
            results = [
                {"id": 101, "name": "시크 레이어드 컷", "vibe": "Chic", "description": "베스트셀러 스타일"},
                {"id": 102, "name": "내추럴 볼륨 펌", "vibe": "Natural", "description": "가장 많이 선호되는 펌"}
            ]
            
        return Response(results)

class ConsultView(APIView):
    @extend_schema(
        summary="상담 정보 전송",
        description="디자이너에게 분석 결과와 선택된 스타일 정보를 전송합니다.",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'customer_id': {'type': 'integer', 'example': 1},
                    'style_id': {'type': 'integer', 'example': 201}
                },
                'required': ['customer_id', 'style_id']
            }
        },
        responses={200: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "상담 전송 예시",
                value={"customer_id": 1, "style_id": 201}
            )
        ]
    )
    def post(self, request):
        """
        디자이너에게 분석 결과 및 선택 스타일 전송
        """
        customer_id = request.data.get('customer_id')
        style_id = request.data.get('style_id')
        
        customer = get_object_or_404(Customer, id=customer_id)
        
        # 분석 데이터 스냅샷 생성 (최신 얼굴 분석 결과)
        latest_analysis = FaceAnalysis.objects.filter(customer=customer).order_by('-created_at').first()
        snapshot = {}
        if latest_analysis:
            snapshot = {
                "face_shape": latest_analysis.face_shape,
                "golden_ratio": latest_analysis.golden_ratio_score,
                "image_url": latest_analysis.image_url
            }

        consultation = ConsultationRequest.objects.create(
            customer=customer,
            analysis_data_snapshot=snapshot,
            status='SENT'
        )
        
        return Response({
            "status": "success",
            "consultation_id": consultation.id,
            "message": "디자이너에게 고객님의 데이터가 안전하게 전송되었습니다."
        })
