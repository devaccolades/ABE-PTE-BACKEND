from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Section,Question,MockTest
from .serializers import SectionSerializer,QuestionSerializer,MockTestSerializer


class MockTestAPIView(APIView):
    def get(self, request):
        tests = MockTest.objects.all()
        if not tests.exists():
            return Response({"error": "No sections found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = MockTestSerializer(tests,many=True)
        return Response({"tests":serializer.data},status=status.HTTP_200)


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


# class Questions(APIView):
#     def get(self,request):
#         questions = Question.objects.all()
#         if not questions.exists():
#             return Response({"error": "No questions found."}, status=status.HTTP_404_NOT_FOUND)

#         serializer = QuestionSerializer(questions, many=True)

#         return Response({
#             "sections_count": questions.count(),
#             "sections": serializer.data
#         }, status=status.HTTP_200_OK)