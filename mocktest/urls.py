from django.urls import path
from .views import SpeakingSectionQuestionsAPIView
urlpatterns = [
    path('mocktestsections/<uuid:mocktest_section_id>/speaking/', SpeakingSectionQuestionsAPIView.as_view(), name='speaking-section-questions'),
]

