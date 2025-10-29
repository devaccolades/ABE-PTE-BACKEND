# urls.py
from django.urls import path
from .views import SectionsAPIView

urlpatterns = [
    path('test/sections/', SectionsAPIView.as_view(), name='mocktest-all-sections'),
    # path('test/questions/', Questions.as_view(), name='mocktest-all-sections'),
]
