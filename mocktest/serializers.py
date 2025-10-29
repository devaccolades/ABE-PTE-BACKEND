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
    skill_name = serializers.CharField(source='subsection.section.skill.name', read_only=True)
    exam_part_name = serializers.CharField(source='subsection.section.exam_part.name', read_only=True)
    
    class Meta:
        model = Question
        fields = [
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
            'subsection_name',
            'section_name',
            'skill_name',
            'exam_part_name',
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

class UserSessionSerilaizer(serializers.ModelSerializer):
    class Meta:
        model = UserMockTestSession
        fields = "__all__"

