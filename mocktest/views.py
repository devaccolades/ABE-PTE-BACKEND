from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Section,Question
from .serializers import SectionSerializer,QuestionSerializer

class MockTestAllSectionsAPIView(APIView):
    def get(self, request):
        sections = Section.objects.all()
        
        if not sections.exists():
            return Response({"error": "No sections found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = SectionSerializer(sections, many=True)

        return Response({
            "sections_count": sections.count(),
            "sections": serializer.data
        }, status=status.HTTP_200_OK)

class Questions(APIView):
    def get(self,request):
        questions = Question.objects.all()
        if not questions.exists():
            return Response({"error": "No questions found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = QuestionSerializer(questions, many=True)

        return Response({
            "sections_count": questions.count(),
            "sections": serializer.data
        }, status=status.HTTP_200_OK)
