import uuid
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from .models import Question,MockTest,MockTestSection
from .serializers import UserMockTestSession,SingleQuestionSerializer



class StartMockTestAPIView(APIView):
    def post(self, request):
        name = request.data.get("name")
        mocktest_id = request.data.get("mocktest_id")

        if not name or not mocktest_id:
            return Response({"error": "Name and mocktest_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mocktest = MockTest.objects.get(pk=mocktest_id)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock test not found."}, status=status.HTTP_404_NOT_FOUND)

        session = UserMockTestSession.objects.create(
            name=name,
            session_id=str(uuid.uuid4()),
            mock_test=mocktest
        )

        return Response({
            "session_id": session.session_id,
            "mocktest_title": mocktest.title,
            "total_questions": Question.objects.filter(subsection__section__mock_test_sections__mock_test=mocktest).count()
        }, status=status.HTTP_201_CREATED)

class SingleQuestionPagination(PageNumberPagination):
    page_size = 1
    page_query_param = 'page'

class GetQuestionAPIView(APIView):
    def get(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = UserMockTestSession.objects.select_related('mock_test').get(session_id=session_id)
        except UserMockTestSession.DoesNotExist:
            return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)

        # ✅ Get all section IDs linked to this mock test
        section_ids = MockTestSection.objects.filter(
            mock_test=session.mock_test
        ).values_list('section_id', flat=True)

        questions = Question.objects.filter(
            subsection__section_id__in=section_ids
        ).select_related(
            'subsection', 'subsection__section'
        ).order_by(
            'subsection__section__mock_test_sections__order',
            'subsection__order',
            'id'
        )
        paginator = SingleQuestionPagination()
        paginated_qs = paginator.paginate_queryset(questions, request)
        serializer = SingleQuestionSerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)


