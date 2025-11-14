from django.urls import path
from .views import TestManualEvaluationAPIView

urlpatterns = [
    path("test/", TestManualEvaluationAPIView.as_view()),
]