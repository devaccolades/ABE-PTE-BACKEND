# serializers.py
from rest_framework import serializers
from .models import Section, SubSection, Question, MockTestSection

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'question_type', 'instructions', 'question_text',
            'audio_file', 'image_file', 'answering_time'
        ]


class SubSectionSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = SubSection
        fields = ['id', 'name', 'order', 'questions']

    def get_questions(self, obj):
        questions = Question.objects.filter(subsection=obj).order_by('id')
        return QuestionSerializer(questions, many=True).data


class MockTestSectionSerializer(serializers.ModelSerializer):
    subsections = serializers.SerializerMethodField()

    class Meta:
        model = MockTestSection
        fields = [
            'id',
            'section',
            'order',
            'total_score_for_section',
            'section_total_duration',
            'per_question_timer',
            'subsections'
        ]

    def get_subsections(self, obj):
        subsections = SubSection.objects.filter(section=obj.section).order_by('order')
        return SubSectionSerializer(subsections, many=True).data


class MockTestSectionsListSerializer(serializers.ModelSerializer):
    mocktest_sections = MockTestSectionSerializer(many=True)

    class Meta:
        model = Section
        fields = ['mocktest_sections']
