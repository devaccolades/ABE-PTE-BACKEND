from django.contrib import admin
from .models import *

class SubSectionInline(admin.TabularInline):
    model = SubSection
    extra = 1
    ordering = ['order']


# class SectionInline(admin.TabularInline):
#     model = Section
#     extra = 1
#     ordering = ['exam_part__order']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    ordering = ['id']


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


# ============================================================
# Main Admin Models
# ============================================================

# @admin.register(Skill)
# class SkillAdmin(admin.ModelAdmin):
#     list_display = ('name',)
#     search_fields = ('name',)
#     ordering = ['name']


# @admin.register(ExamPart)
# class ExamPartAdmin(admin.ModelAdmin):
#     list_display = ('name', 'order', 'description')
#     ordering = ['order']
#     inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', )
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
        'name', 'subsection', 'reading_time', 'answering_time',
        'speaking_score_max', 'writing_score_max', 'reading_score_max', 'listening_score_max'
    )
    search_fields = ('name', 'text')
    ordering = ['subsection__order', 'id']

@admin.register(QuestionOptions)
class QuestionOptionsAdmin(admin.ModelAdmin):
    list_display = (
        'option_text',
        'question',
        'is_correct',
    )
    list_filter = ('question__subsection','question__name')
    search_fields = ('option_text', 'question__question_name')
    ordering = ['question__subsection__order', 'question__id', 'id']


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
    inlines = [UserResponseInline]


@admin.register(UserResponse)
class UserResponseAdmin(admin.ModelAdmin):
    list_display = (
        'user_session', 'mock_test', 'question',
        'speaking_score_awarded', 'writing_score_awarded',
        'reading_score_awarded', 'listening_score_awarded',
        'evaluated', 'submitted_at'
    )
    list_filter = ('evaluated', 'mock_test', 'user_session__mock_test')
    search_fields = (
        'question__name', 'user_session__name', 'mock_test__title'
    )
    readonly_fields = (
        'submitted_at', 'mock_test', 'question', 'text_response', 'audio_response'
    )
    ordering = ['-submitted_at']