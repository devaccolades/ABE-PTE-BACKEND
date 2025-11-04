# urls.py
from django.urls import path
from .views import StartMockTestAPIView,GetQuestionAPIView

urlpatterns = [
   
    path('start-test/', StartMockTestAPIView.as_view(), name='start-test'),
    path('get-question/', GetQuestionAPIView.as_view(), name='get-question'),


]
