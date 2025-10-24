from rest_framework import serializers
from .models import Question, SubSection,Section

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'question_type', 'instructions', 'question_text', 'audio_file', 'image_file', 'answering_time']
        
class SubSectionSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = SubSection
        fields = ['id', 'name', 'order', 'questions']

    def get_questions(self, obj):
        questions = Question.objects.filter(subsection=obj, section__section_type='speaking & writing')
        return QuestionSerializer(questions, many=True).data
