# urls.py
from django.urls import path
from .views import SectionsAPIView,QuestionsAPIView

urlpatterns = [
    path('test/sections/', SectionsAPIView.as_view(), name='mocktest-all-sections'),
    path('test/questions/', QuestionsAPIView.as_view(), name='mocktest-questions'),
]
