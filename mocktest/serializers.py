# serializers.py
from rest_framework import serializers
from .models import *
from django.conf import settings
from mocktest.services.evaluation_input import question_requires_audio

class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        # Correctness and ordering metadata must never reach exam candidates.
        fields = ["id", "option_text"]

class SubQuestionSerializer(serializers.ModelSerializer):
    """Serializer for each blank inside a fill-in-the-blank question."""
    options = QuestionOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SubQuestion
        fields = [
            "id",
            "blank_number",
            "text_before_blank",
            "text_after_blank",
            "options"
        ]

class MockTestSectionMiniSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source='section.name', read_only=True)

    class Meta:
        model = MockTestSection
        fields = [
            'id',
            'section_id',
            'section_name',
            'order',
            'total_duration'
        ]

class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    sub_questions = SubQuestionSerializer(many=True, read_only=True)

    mocktest_section = MockTestSectionMiniSerializer(
        source='mock_test_section',
        read_only=True
    )

    subsection = serializers.CharField(source='subsection.name', read_only=True)
    subsection_instruction = serializers.CharField(
        source='subsection.instructions',
        read_only=True
    )
    ai_input_type = serializers.SerializerMethodField()
    audio = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id',
            'name',
            'text',
            'audio',
            'image',
            'question_type',
            'reading_time',
            'answering_time',
            'mocktest_section',
            'subsection',
            'subsection_instruction',
            'ai_input_type',
            'options',
            'sub_questions',
        ]

    def get_audio(self, obj):
        request = self.context.get('request')
        if obj.audio:
            return request.build_absolute_uri(obj.audio.url)
        return None

    def get_ai_input_type(self, obj):
        return "audio" if question_requires_audio(obj) else "text"

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url)
        return None




class SingleQuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    sub_questions = SubQuestionSerializer(many=True, read_only=True)

    mocktest_section = MockTestSectionMiniSerializer(
        source='mock_test_section',
        read_only=True
    )

    subsection = serializers.CharField(source='subsection.name', read_only=True)
    subsection_instruction = serializers.CharField(
        source='subsection.instructions',
        read_only=True
    )
    ai_input_type = serializers.SerializerMethodField()

    audio = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id',
            'name',
            'text',
            'audio',
            'image',
            'question_type',
            'reading_time',
            'answering_time',
            'mocktest_section',
            'subsection',
            'subsection_instruction',
            'ai_input_type',
            'options',
            'sub_questions',
        ]

    # def get_mocktest_section(self, obj):
    #     request = self.context.get('request')
    #     session_id = request.query_params.get('session_id')

    #     if not session_id:
    #         return None

    #     try:
    #         session = UserMockTestSession.objects.get(session_id=session_id)
    #     except UserMockTestSession.DoesNotExist:
    #         return None
        
    #     mts = MockTestSection.objects.filter(
    #         mock_test=session.mock_test,
    #         section=obj.subsection.section
    #     ).first()

    #     if not mts:
    #         return None

    #     return {
    #         "id": mts.id,
    #         "section_id": mts.section_id,
    #         "section_name": mts.section.name,
    #         "order": mts.order,
    #         "total_duration": mts.total_duration
    #     }


    def get_audio(self, obj):
        if obj.audio:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.audio.url)
            return f"{settings.MEDIA_URL}{obj.audio.url}"
        return None

    def get_ai_input_type(self, obj):
        return "audio" if question_requires_audio(obj) else "text"

    def get_image(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return f"{settings.MEDIA_URL}{obj.image.url}"
        return None


class SessionQuestionSerializer(serializers.Serializer):
    """Candidate-safe representation of an immutable session question."""

    def to_representation(self, instance):
        snapshot = instance.question_snapshot or {}
        return {
            "id": instance.question_id_snapshot,
            "name": snapshot.get("name"),
            "text": snapshot.get("text"),
            "audio": self._media_url(snapshot.get("audio")),
            "image": self._media_url(snapshot.get("image")),
            "question_type": snapshot.get("question_type"),
            "reading_time": snapshot.get("reading_time", 0),
            "answering_time": snapshot.get("answering_time", 0),
            "mocktest_section": snapshot.get("mocktest_section") or {
                "id": instance.mock_test_section_id_snapshot,
                "section_id": None,
                "section_name": instance.section_name,
                "order": instance.section_order,
                "total_duration": None,
            },
            "subsection": snapshot.get("subsection") or instance.subsection_name,
            "subsection_instruction": snapshot.get("subsection_instruction"),
            "ai_input_type": instance.expected_input_type,
            "options": [
                {
                    "id": option.get("id"),
                    "option_text": option.get("text"),
                }
                for option in snapshot.get("options", [])
            ],
            "sub_questions": [
                {
                    "id": sub_question.get("id"),
                    "blank_number": sub_question.get("blank_number"),
                    "text_before_blank": sub_question.get("text_before_blank"),
                    "text_after_blank": sub_question.get("text_after_blank"),
                    "options": [
                        {
                            "id": option.get("id"),
                            "option_text": option.get("text"),
                        }
                        for option in sub_question.get("options", [])
                    ],
                }
                for sub_question in snapshot.get("sub_questions", [])
            ],
        }

    def _media_url(self, name):
        if not name:
            return None
        relative_url = f"{settings.MEDIA_URL.rstrip('/')}/{str(name).lstrip('/')}"
        request = self.context.get("request")
        return request.build_absolute_uri(relative_url) if request else relative_url


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

class MockTestListSerializer(serializers.ModelSerializer):

    class Meta:
        model = MockTest
        fields = "__all__"

class UserMockTestSessionCreateSerializer(serializers.ModelSerializer):
    mock_test_details = MockTestSerializer(source='mock_test', read_only=True)

    class Meta:
        model = UserMockTestSession
        fields = ['id', 'name', 'session_id', 'mock_test', 'mock_test_details']


class UserResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserResponse
        fields = "__all__"

class SingleResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SingleResponse
        fields = "__all__"
