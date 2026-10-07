from django.urls import path

from .views import (
    APIListingQuestions,
    AnswerIntegrityTestAPIView,
    CompleteMockTestSessionAPIView,
    GetQuestionAPIView,
    MockTestListAPIView,
    SessionEvaluationStatusAPIView,
    SessionPDFView,
    SingleAPIView,
    SingleResponseStatusAPIView,
    StartMockTestAPIView,
    SubSectionQuestionListAPIView,
    UserResponseAPIView,
)

urlpatterns = [
    path(
        'answer-integrity-test/',
        AnswerIntegrityTestAPIView.as_view(),
        name='answer-integrity-test',
    ),
    path('start-test/', StartMockTestAPIView.as_view(), name='start-test'),
    path('get-question/', GetQuestionAPIView.as_view(), name='get-question'),
    path('question/', APIListingQuestions.as_view(), name='question'),
    path('user-response/', UserResponseAPIView.as_view(), name='user-response'),
    path('session-evaluation-status/', SessionEvaluationStatusAPIView.as_view(), name='session-evaluation-status'),
    path('complete-session/', CompleteMockTestSessionAPIView.as_view(), name='complete-session'),
    path('mocktest-list/', MockTestListAPIView.as_view(), name='mock-test'),

    ## New endpoint for questions by subsection name
    path(
        "all_questions/<str:subsection_name>/",
        SubSectionQuestionListAPIView.as_view(),
        name="questions-by-subsection-name",
    ),
    path('single-response/', SingleAPIView.as_view(), name='user-response'),
    path(
        'single-response-status/<uuid:tracking_id>/',
        SingleResponseStatusAPIView.as_view(),
        name='single-response-status',
    ),

    path("sessions/<int:pk>/pdf/", SessionPDFView.as_view()),
]
