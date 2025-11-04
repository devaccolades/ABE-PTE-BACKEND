# serializers.py
from rest_framework import serializers
from .models import *

class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamPart
        fields = "__all__"

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = "__all__"

class SubSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubSection
        fields = "__all__"

class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOptions
        fields = "__all__"

class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    subsection_name = serializers.CharField(source='subsection.name', read_only=True)
    section_name = serializers.CharField(source='subsection.section.name', read_only=True)
    exam_part_name = serializers.CharField(source='subsection.section.exam_part.name', read_only=True)
    
    class Meta:
        model = Question
        fields = [
            'exam_part_name',
            'section_name',
            'subsection_name',
            'id',
            'name',
            'text',
            'audio',
            'image',
            'correct_answer',
            'reading_time',
            'answering_time',
            'speaking_score_max',
            'writing_score_max',
            'reading_score_max',
            'listening_score_max',
            'options',
        ]

class MockTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTest
        fields = "__all__"


class MockTestSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MockTestSection
        fields = "__all__"

class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMockTestSession
        fields = "__all__"






class LightQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'name', 'text', 'reading_time', 'answering_time']

class UserMockTestSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMockTestSession
        fields = ['id', 'session_id', 'name', 'mock_test', 'created_at']


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


class LightSubSectionSerializer(serializers.ModelSerializer):
    questions = LightQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = SubSection
        fields = ['id', 'name', 'order', 'questions']


class LightSectionSerializer(serializers.ModelSerializer):
    subsections = LightSubSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'name', 'skill', 'exam_part', 'total_duration', 'subsections']


class LightweightMockTestSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()

    class Meta:
        model = MockTest
        fields = ['test_id', 'title', 'description', 'total_score', 'total_duration', 'sections']

    def get_sections(self, obj):
        mocktest_sections = obj.sections.select_related('section').order_by('order')
        return LightSectionSerializer([m.section for m in mocktest_sections], many=True).data


class UserMockTestSessionCreateSerializer(serializers.ModelSerializer):
    mock_test_details = LightweightMockTestSerializer(source='mock_test', read_only=True)

    class Meta:
        model = UserMockTestSession
        fields = ['id', 'name', 'session_id', 'mock_test', 'mock_test_details']

