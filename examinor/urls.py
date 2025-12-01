from django.urls import path
from .views import evaluate_pte

urlpatterns = [
    path("test/", evaluate_pte, name="evaluate_pte"),
]