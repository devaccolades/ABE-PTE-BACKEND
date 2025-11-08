from django.contrib import admin
from .models import *


class SubSectionInline(admin.TabularInline):
    model = SubSection
    extra = 1
    ordering = ['order']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    ordering = ['id']


# Inline for options — shown inside SubQuestion
class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 2
    fields = ['option_text', 'is_correct', 'order_position']
    show_change_link = True


# Inline for sub-questions — shown inside Question (for fill_blank type)
class SubQuestionInline(admin.TabularInline):
    model = SubQuestion
    extra = 1
    fields = ['blank_number', 'text_before_blank', 'text_after_blank', 'correct_answer']
    show_change_link = True


class MockTestSectionInline(admin.TabularInline):
    """Inline to attach sections to a Mock Test"""
    model = MockTestSection
    extra = 1
    ordering = ['order']


class UserResponseInline(admin.TabularInline):
    model = UserResponse
    extra = 0
    readonly_fields = (
        'question', 'text_response', 'audio_response',
        'speaking_score_awarded', 'writing_score_awarded',
        'reading_score_awarded', 'listening_score_awarded',
        'evaluated', 'submitted_at'
    )
    can_delete = False
    ordering = ['submitted_at']


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    inlines = [SubSectionInline]
    ordering = ['name']


@admin.register(SubSection)
class SubSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'section', 'order')
    search_fields = ('name',)
    ordering = ['order']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'name','id', 'question_type', 'subsection', 'reading_time', 'answering_time',
        'speaking_score_max', 'writing_score_max', 'reading_score_max', 'listening_score_max'
    )
    search_fields = ('name', 'text')
    list_filter = ('question_type', 'subsection')
    ordering = ['subsection__id', 'id']

    inlines = [SubQuestionInline]

    def get_inlines(self, request, obj=None):
        """Show inlines based on question type."""
        if obj and obj.question_type == 'fill_blank':
            return [SubQuestionInline]
        else:
            # For single/multiple/reorder types, show options directly
            return [QuestionOptionInline]


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_question_name', 'get_blank_number', 'option_text', 'is_correct')
    search_fields = ('option_text', 'question__name')
    list_filter = ('is_correct',)
    ordering = ['question', 'id']

    def get_question_name(self, obj):
        return obj.question.name if obj.question else obj.sub_question.question.name
    get_question_name.short_description = "Question"

    def get_blank_number(self, obj):
        return obj.sub_question.blank_number if obj.sub_question else None
    get_blank_number.short_description = "Blank #"


@admin.register(SubQuestion)
class SubQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'blank_number', 'correct_answer')
    search_fields = ('question__name', 'correct_answer')
    ordering = ['question', 'blank_number']
    inlines = [QuestionOptionInline]


@admin.register(MockTest)
class MockTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'total_score', 'total_duration', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    inlines = [MockTestSectionInline]
    ordering = ['-created_at']


@admin.register(MockTestSection)
class MockTestSectionAdmin(admin.ModelAdmin):
    list_display = ('mock_test', 'section', 'order')
    list_filter = ('mock_test',)
    ordering = ['mock_test', 'order']


@admin.register(UserMockTestSession)
class UserMockTestSessionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'mock_test', 'session_id',
        'started_at', 'completed_at', 'is_completed', 'total_score'
    )
    list_filter = ('mock_test', 'is_completed')
    search_fields = ('name', 'session_id', 'mock_test__title')
    readonly_fields = (
        'started_at', 'completed_at',
        'speaking_score_awarded', 'writing_score_awarded',
        'reading_score_awarded', 'listening_score_awarded',
        'total_score'
    )
    ordering = ['-started_at']


@admin.register(UserResponse)
class UserResponseAdmin(admin.ModelAdmin):
    list_display = (
        'user_session',
        'id',
        'mock_test',
        'question',
        'is_correct',
        'score_awarded',
        'evaluated',
        'submitted_at',
    )
    list_filter = (
        'mock_test',
        'is_correct',
        'evaluated',
    )
    search_fields = (
        'user_session__name',
        'question__question_text',
    )
    readonly_fields = ('submitted_at',)
    list_per_page = 25

