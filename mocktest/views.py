# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import MockTest, MockTestSection, SubSection,Section
from .serializers import MockTestSectionSerializer

class MockTestAllSectionsAPIView(APIView):
    def get(self, request):
        try:
            section = Section.objects.all()
        except Section.DoesNotExist:
            return Response({"error": "Mock test not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            
            "sections_count": section.count(),
            "sections": section
        })
