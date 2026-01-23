# urls.py
from django.urls import path
from .views import StartMockTestAPIView, GetQuestionAPIView, UserResponseAPIView,MockTestListAPIView,APIListingQuestions,SubSectionQuestionListAPIView,SingleAPIView

urlpatterns = [
   
    path('start-test/', StartMockTestAPIView.as_view(), name='start-test'),
    path('get-question/', GetQuestionAPIView.as_view(), name='get-question'),
    path('question/', APIListingQuestions.as_view(), name='question'),
    path('user-response/', UserResponseAPIView.as_view(), name='user-response'),
    path('mocktest-list/', MockTestListAPIView.as_view(), name='mock-test'),

    ## New endpoint for questions by subsection name
    path(
        "all_questions/<str:subsection_name>/",
        SubSectionQuestionListAPIView.as_view(),
        name="questions-by-subsection-name",
    ),
    path('single-response/', SingleAPIView.as_view(), name='user-response')
]
