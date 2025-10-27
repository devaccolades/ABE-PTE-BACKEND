# from django.contrib import admin
# from .models import MockTest, Section,SubSection,Question,MockTestQuestion,UserMockTestSession,UserResponse,MockTestSection,MockTestSubSection



# @admin.register(MockTest)
# class MockTestAdmin(admin.ModelAdmin):
#     list_display = ('title', 'total_duration', 'is_active', 'created_at')
#     list_filter = ('is_active', 'created_at')
#     search_fields = ('title', 'description')
#     ordering = ('-created_at',)
#     # inlines = [MockTestSectionInline]
#     list_per_page = 10

# @admin.register(Section)
# class SectionAdmin(admin.ModelAdmin):
#     list_display = ('section_type', 'has_subsection')
#     list_filter = ('section_type', 'has_subsection')
#     search_fields = ('section_type',)
#     # inlines = [SubSectionInline]


# @admin.register(SubSection)
# class SubSectionAdmin(admin.ModelAdmin):
#     list_display = ('name', 'section', 'order')
#     list_filter = ('section',)
#     search_fields = ('name',)
#     ordering = ('section', 'order')


# @admin.register(Question)
# class QuestionAdmin(admin.ModelAdmin):
#     list_display = ('id', 'section', 'question_type', 'is_first_listening_question', 'answering_time')
#     list_filter = ('section', 'question_type', 'is_first_listening_question')
#     search_fields = ('question_text',)
#     ordering = ('section', 'id')
#     readonly_fields = ('id',)
#     fieldsets = (
#         ('Basic Info', {
#             'fields': ('section', 'subsection', 'question_type', 'question_text')
#         }),
#         ('Media', {
#             'fields': ('audio_file', 'image_file')
#         }),
#         ('Answer & Options', {
#             'fields': ('correct_answer', 'options')
#         }),
#         ('Timing', {
#             'fields': ('answering_time', 'is_first_listening_question', 'reading_time')
#         }),
#     )

# @admin.register(MockTestSection)
# class MockTestSectionAdmin(admin.ModelAdmin):
#     list_display = ('mock_test', 'section', 'order', 'section_total_duration', 'total_score_for_section', 'per_question_timer')
#     list_filter = ('mock_test', 'section', 'per_question_timer')
#     search_fields = ('mock_test__title', 'section__section_type')
#     # inlines = [MockTestSubSectionInline, MockTestQuestionInline]
#     ordering = ('mock_test', 'order')


# @admin.register(MockTestSubSection)
# class MockTestSubSectionAdmin(admin.ModelAdmin):
#     list_display = ('mock_section', 'subsection', 'total_duration', 'total_score_for_subsection', 'per_question_timer')
#     list_filter = ('mock_section__mock_test', 'subsection')
#     search_fields = ('mock_section__mock_test__title', 'subsection__name')
#     ordering = ('mock_section', 'subsection')



# @admin.register(MockTestQuestion)
# class MockTestQuestionAdmin(admin.ModelAdmin):
#     list_display = ('mock_test', 'section', 'question', 'order', 'score_for_question')
#     list_filter = ('mock_test', 'section')
#     search_fields = ('mock_test__title', 'question__question_text')
#     ordering = ('mock_test', 'section', 'order')


# @admin.register(UserMockTestSession)
# class UserMockTestSessionAdmin(admin.ModelAdmin):
#     list_display = ('session_id', 'mock_test', 'started_at', 'completed_at', 'is_completed', 'total_score')
#     list_filter = ('is_completed', 'mock_test')
#     search_fields = ('session_id', 'mock_test__title')
#     ordering = ('-started_at',)
#     readonly_fields = ('started_at', 'completed_at')


# @admin.register(UserResponse)
# class UserResponseAdmin(admin.ModelAdmin):
#     list_display = ('session', 'mock_test', 'question', 'score_awarded', 'evaluated', 'submitted_at')
#     list_filter = ('evaluated', 'mock_test', 'session')
#     search_fields = ('question__question_text', 'session__session_id', 'mock_test__title')
#     ordering = ('-submitted_at',)
#     readonly_fields = ('submitted_at',)

from django.contrib import admin
from .models import Skill, ExamPart, Section, SubSection, Question, MockTest, MockTestSection


# ============================================================
# Inline Configurations
# ============================================================

class SubSectionInline(admin.TabularInline):
    model = SubSection
    extra = 1
    ordering = ['order']


class SectionInline(admin.TabularInline):
    model = Section
    extra = 1
    ordering = ['exam_part__order']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    ordering = ['id']


class MockTestSectionInline(admin.TabularInline):
    """Inline to attach sections to a Mock Test"""
    model = MockTestSection
    extra = 1
    ordering = ['order']


# ============================================================
# Main Admin Models
# ============================================================

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ['name']


@admin.register(ExamPart)
class ExamPartAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'description')
    ordering = ['order']
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'exam_part', 'skill', 'total_duration')
    list_filter = ('exam_part', 'skill')
    search_fields = ('name',)
    inlines = [SubSectionInline]
    ordering = ['exam_part__order', 'skill__name', 'name']


@admin.register(SubSection)
class SubSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'section', 'order')
    list_filter = ('section__exam_part', 'section__skill')
    search_fields = ('name',)
    inlines = [QuestionInline]
    ordering = ['section__exam_part__order', 'order']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'subsection', 'reading_time', 'answering_time',
        'speaking_score_max', 'writing_score_max', 'reading_score_max', 'listening_score_max'
    )
    list_filter = ('subsection__section__exam_part', 'subsection__section__skill')
    search_fields = ('name', 'text')
    ordering = ['subsection__order', 'id']


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
    list_filter = ('mock_test', 'section__exam_part', 'section__skill')
    ordering = ['mock_test', 'order']
