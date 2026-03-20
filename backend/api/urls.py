from django.urls import path
from .views import LoginView, SurveyView, CaptureUploadView, RecommendationView, TrendView, ConsultView

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('survey/', SurveyView.as_view(), name='survey'),
    path('capture/upload/', CaptureUploadView.as_view(), name='upload'),
    path('analysis/recommendations/', RecommendationView.as_view(), name='recommendations'),
    path('analysis/trend/', TrendView.as_view(), name='trend'),
    path('analysis/consult/', ConsultView.as_view(), name='consult'),
]
