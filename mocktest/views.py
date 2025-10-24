# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import MockTest, MockTestSection, SubSection
from .serializers import MockTestSectionSerializer

class MockTestAllSectionsAPIView(APIView):
    def get(self, request, mocktest_id):
        try:
            mock_test = MockTest.objects.get(id=mocktest_id)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock test not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get all linked sections
        mock_sections = MockTestSection.objects.filter(mock_test=mock_test).select_related('section').order_by('order')
        serializer = MockTestSectionSerializer(mock_sections, many=True)

        return Response({
            "mock_test": mock_test.title,
            "sections_count": mock_sections.count(),
            "sections": serializer.data
        })
