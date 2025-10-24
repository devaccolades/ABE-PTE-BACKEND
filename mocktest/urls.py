# urls.py
from django.urls import path
from .views import MockTestAllSectionsAPIView,Questions

urlpatterns = [
    path('test/sections/', MockTestAllSectionsAPIView.as_view(), name='mocktest-all-sections'),
    path('test/questions/', Questions.as_view(), name='mocktest-all-sections'),
]
