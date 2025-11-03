import uuid
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Section,Question,MockTest
from .serializers import SectionSerializer,QuestionSerializer,MockTestSerializer,UserMockTestSessionCreateSerializer,UserMockTestSession



class StartMockTestAPIView(APIView):
    def post(self, request):
        name = request.data.get("name")
        mocktest_id = request.data.get("mocktest_id")  # frontend can pass selected mocktest

        if not name or not mocktest_id:
            return Response({"error": "Name and mocktest_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mocktest = MockTest.objects.get(pk=mocktest_id)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock test not found."}, status=status.HTTP_404_NOT_FOUND)

        # Create unique session
        session = UserMockTestSession.objects.create(
            name=name,
            session_id=str(uuid.uuid4()),
            mock_test=mocktest
        )

        serializer = UserMockTestSessionCreateSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



class MockTestAPIView(APIView):
    def get(self, request):
        tests = MockTest.objects.all()
        if not tests.exists():
            return Response({"error": "No sections found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = MockTestSerializer(tests,many=True)
        return Response({"tests":serializer.data},status=status.HTTP_200_OK)


class SectionsAPIView(APIView):
    def get(self, request):
        sections = Section.objects.all()
        
        if not sections.exists():
            return Response({"error": "No sections found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SectionSerializer(sections, many=True)

        return Response({
            "sections_count": sections.count(),
            "sections": serializer.data
        }, status=status.HTTP_200_OK)

class QuestionsAPIView(APIView):
    def get(self, request):
        try:
            # Fetch questions efficiently
            questions = Question.objects.select_related(
                'subsection__section__skill',
                'subsection__section__exam_part'
            ).prefetch_related('options')

            if not questions.exists():
                return Response(
                    {"detail": "No questions found."},
                    status=status.HTTP_204_NO_CONTENT
                )

            serializer = QuestionSerializer(questions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except DatabaseError as e:
            # Handle database-level errors
            return Response(
                {"error": "Database error occurred.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            # Catch-all for any unexpected errors
            return Response(
                {"error": "An unexpected error occurred.", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


