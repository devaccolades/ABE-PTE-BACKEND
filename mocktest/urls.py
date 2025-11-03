# urls.py
from django.urls import path
from .views import SectionsAPIView,QuestionsAPIView, MockTestAPIView,StartMockTestAPIView

urlpatterns = [
    path('mocktests/', MockTestAPIView.as_view(), name='all-mocktest'),
    path('sections/', SectionsAPIView.as_view(), name='mocktest-all-sections'),
    path('questions/', QuestionsAPIView.as_view(), name='mocktest-questions'),
    path('start-test/', StartMockTestAPIView.as_view(), name='start-test'),

]
