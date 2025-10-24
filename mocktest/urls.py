# urls.py
from django.urls import path
from .views import MockTestAllSectionsAPIView

urlpatterns = [
    path('test/sections/', MockTestAllSectionsAPIView.as_view(), name='mocktest-all-sections'),
]
