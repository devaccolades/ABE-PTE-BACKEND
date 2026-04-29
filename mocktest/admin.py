from django.contrib import admin
from django.urls import path
from django.http import FileResponse, Http404
from django.utils.html import format_html
from django.db.models import Prefetch

from .models import *
from .services.pdf_service import generate_session_pdf


# =========================
# INLINES
# =========================

class SubSectionInline(admin.TabularInline):
    model = SubSection
    extra = 1
    ordering = ['order']


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 2
    fields = ['option_text', 'is_correct', 'order_position']
    show_change_link = True


class SubQuestionInline(admin.TabularInline):
    model = SubQuestion
    extra = 1
    fields = ['blank_number', 'text_before_blank', 'text_after_blank', 'correct_answer']
    show_change_link = True


class MockTestSectionInline(admin.TabularInline):
    model = MockTestSection
    extra = 1
    ordering = ['order']


class UserResponseInline(admin.TabularInline):
    model = UserResponse
    extra = 0
    can_delete = False
    ordering = ['submitted_at']

    readonly_fields = (
        'question',
        'response_display',
        'scores_display',
        'evaluated',
        'submitted_at',
    )

    # -------------------------
    # RESPONSE DISPLAY (SMART)
    # -------------------------
    def response_display(self, obj):
        # JSON answer
        if obj.answer_data:
            return format_html(
                '<pre style="white-space:pre-wrap;max-width:400px;">{}</pre>',
                obj.answer_data
            )

        # Audio answer
        if obj.answer_audio:
            return format_html(
                '<a href="{}" target="_blank">🎧 Audio</a>',
                obj.answer_audio.url
            )

        return "-"

    response_display.short_description = "Response"

    # -------------------------
    # SCORES DISPLAY (COMPACT)
    # -------------------------
    def scores_display(self, obj):
        return format_html(
            "S: {} | W: {} | R: {} | L: {}",
            obj.speaking_score_awarded,
            obj.writing_score_awarded,
            obj.reading_score_awarded,
            obj.listening_score_awarded,
        )

    scores_display.short_description = "Scores"
# =========================
# CORE ADMINS
# =========================

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
        'name', 'id', 'question_type', 'subsection',
        'reading_time', 'answering_time',
        'speaking_score_max', 'writing_score_max',
        'reading_score_max', 'listening_score_max'
    )

    search_fields = ('name', 'text')
    list_filter = ('question_type', 'subsection')
    ordering = ['subsection__id', 'id']

    def get_inlines(self, request, obj=None):
        if obj and obj.question_type == 'fill_blank':
            return [SubQuestionInline]
        return [QuestionOptionInline]


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_question_name', 'get_blank_number', 'option_text', 'is_correct')
    search_fields = ('option_text', 'question__name')
    list_filter = ('is_correct',)
    ordering = ['question', 'id']

    def get_question_name(self, obj):
        return obj.question.name if obj.question else obj.sub_question.question.name

    def get_blank_number(self, obj):
        return obj.sub_question.blank_number if obj.sub_question else None


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
    list_display = ('id', 'mock_test', 'section', 'order')
    list_filter = ('mock_test',)
    ordering = ['mock_test', 'order']


# =========================
# USER SESSION ADMIN (MAIN UX)
# =========================

@admin.register(UserMockTestSession)
class UserMockTestSessionAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'mock_test',
        'short_session_id',
        'started_at',
        'status_badge',
        'total_score',
        'download_pdf_button',
    )

    list_filter = ('mock_test', 'is_completed')
    search_fields = ('name', 'session_id', 'mock_test__title')
    ordering = ['-started_at']

    readonly_fields = (
        'session_id',
        'started_at',
        'completed_at',
        'total_score'
    )

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "mock_test", "session_id")
        }),
        ("Progress", {
            "fields": ("started_at", "completed_at", "is_completed")
        }),
        ("Result", {
            "fields": ("total_score",)
        }),
    )

    inlines = [UserResponseInline]

    # -------------------------
    # OPTIMIZED QUERYSET
    # -------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('mock_test')

    # -------------------------
    # SHORT SESSION ID
    # -------------------------
    def short_session_id(self, obj):
        return str(obj.session_id)[:8]
    short_session_id.short_description = "Session"

    # -------------------------
    # STATUS BADGE
    # -------------------------
    def status_badge(self, obj):
        if obj.is_completed:
            return format_html('<span style="color:green;font-weight:bold;">✔ Completed</span>')
        return format_html('<span style="color:red;font-weight:bold;">✘ Pending</span>')
    status_badge.short_description = "Status"

    # -------------------------
    # PDF BUTTON
    # -------------------------
    def download_pdf_button(self, obj):
        return format_html(
            '<a style="padding:4px 8px;background:#28a745;color:white;border-radius:4px;text-decoration:none;" href="download-pdf/{}/" target="_blank">PDF</a>',
            obj.pk
        )

    download_pdf_button.short_description = "PDF"

    # -------------------------
    # BULK ACTION
    # -------------------------
    actions = ['mark_as_completed']

    def mark_as_completed(self, request, queryset):
        updated = queryset.update(is_completed=True)
        self.message_user(request, f"{updated} sessions marked as completed.")
    mark_as_completed.short_description = "Mark selected sessions as completed"

    # -------------------------
    # CUSTOM URL
    # -------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "download-pdf/<int:session_id>/",
                self.admin_site.admin_view(self.download_pdf_view),
                name="download-session-pdf",
            ),
        ]
        return custom_urls + urls

    # -------------------------
    # PDF VIEW (SAFE)
    # -------------------------
    # admin.py

    def download_pdf_view(self, request, session_id):
        try:
            session = (
                UserMockTestSession.objects
                .select_related("mock_test")
                .prefetch_related(
                    "userresponse_set__question__subsection__section"
                )
                .get(pk=session_id)
            )
        except UserMockTestSession.DoesNotExist:
            raise Http404("Session not found")

        file_path = f"/tmp/session_{session.id}.pdf"
        generate_session_pdf(session, file_path)

        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=f"session_{session.id}.pdf",
        )

# =========================
# USER RESPONSE ADMIN
# =========================

@admin.register(UserResponse)
class UserResponseAdmin(admin.ModelAdmin):
    list_display = (
        'user_session',
        'id',
        'mock_test',
        'question',
        'evaluated',
        'submitted_at',
    )

    list_filter = ('mock_test', 'evaluated')
    search_fields = ('user_session__name', 'question__question_text')

    readonly_fields = ('submitted_at',)
    list_per_page = 25


# =========================
# OTHER MODELS
# =========================

@admin.register(GlobalRubric)
class GlobalRubricAdmin(admin.ModelAdmin):
    list_display = ('key', 'rubric')
    search_fields = ('key',)


@admin.register(SingleResponse)
class SingleResponseAdmin(admin.ModelAdmin):
    list_display = ('name', 'question', 'submitted_at')
    list_filter = ('question__question_type', 'name')
    readonly_fields = ('submitted_at',)
    ordering = ['-submitted_at']