# serializers.py
from rest_framework import serializers
from .models import *

class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOptions
        fields = "__all__"

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'name', 'text', 'reading_time', 'answering_time']



class SingleQuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    subsection = serializers.CharField(source='subsection.name', read_only=True)
    section = serializers.CharField(source='subsection.section.name', read_only=True)

    class Meta:
        model = Question
        fields = [
            'id', 'name', 'text', 'audio', 'image',
            'reading_time', 'answering_time',
            'section', 'subsection', 'options'
        ]


class SubSectionSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = SubSection
        fields = ['id', 'name', 'order', 'questions']


class SectionSerializer(serializers.ModelSerializer):
    subsections = SubSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'name', 'skill', 'exam_part', 'total_duration', 'subsections']


class MockTestSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()

    class Meta:
        model = MockTest
        fields = ['test_id', 'title', 'description', 'total_score', 'total_duration', 'sections']

    def get_sections(self, obj):
        mocktest_sections = obj.sections.select_related('section').order_by('order')
        return SectionSerializer([m.section for m in mocktest_sections], many=True).data


class UserMockTestSessionCreateSerializer(serializers.ModelSerializer):
    mock_test_details = MockTestSerializer(source='mock_test', read_only=True)

    class Meta:
        model = UserMockTestSession
        fields = ['id', 'name', 'session_id', 'mock_test', 'mock_test_details']

class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserResponse
        fields = "__all__"
