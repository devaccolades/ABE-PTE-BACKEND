# serializers.py
from rest_framework import serializers
from .models import *

class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'section_type', 'has_subsection']

class SubSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubSection
        fields = "__all__"


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = "__all__"