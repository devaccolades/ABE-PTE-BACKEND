from django.urls import path
from .views import dummy_pte_data
urlpatterns = [
    path('',dummy_pte_data, name="dummy"),
]

