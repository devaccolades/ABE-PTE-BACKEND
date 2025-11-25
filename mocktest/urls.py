# urls.py
from django.urls import path
from .views import StartMockTestAPIView, GetQuestionAPIView, UserResponseAPIView,MockTestListAPIView

urlpatterns = [
   
    path('start-test/', StartMockTestAPIView.as_view(), name='start-test'),
    path('get-question/', GetQuestionAPIView.as_view(), name='get-question'),
    path('user-response/', UserResponseAPIView.as_view(), name='user-response'),
    path('mocktest-list/', MockTestListAPIView.as_view(), name='mock-test'),

]
