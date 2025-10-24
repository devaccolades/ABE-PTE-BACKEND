
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import MockTestSection, Section, SubSection
from .serializers import SubSectionSerializer

class SpeakingSectionQuestionsAPIView(APIView):
    def get(self, request, mocktest_section_id):
        try:
            mock_section = MockTestSection.objects.get(id=mocktest_section_id)
        except MockTestSection.DoesNotExist:
            return Response({"error": "MockTestSection not found."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure it's a Speaking & Writing section
        if mock_section.section.section_type != "speaking & writing":
            return Response({"error": "This section is not Speaking & Writing."}, status=status.HTTP_400_BAD_REQUEST)

        # Get all subsections linked to this section
        subsections = SubSection.objects.filter(section=mock_section.section).order_by('order')
        serializer = SubSectionSerializer(subsections, many=True)
        return Response({
            "mock_test": mock_section.mock_test.title,
            "section": mock_section.section.section_type,
            "subsections": serializer.data
        })
