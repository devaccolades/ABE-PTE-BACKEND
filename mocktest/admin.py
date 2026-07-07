from django.contrib import admin, messages
from django.contrib.auth.models import Group, User
from django.urls import path, reverse
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils.html import format_html
from django.db.models import Max, Prefetch, Q

from .models import *
from .services.pdf_service import generate_session_pdf
from .services.evaluation_queue import queue_response_evaluation


admin.site.unregister(Group)
admin.site.unregister(User)


RATE_LIMIT_ERROR_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "quota",
    "insufficient_quota",
)


def is_api_limit_error(error):
    error_text = str(error or "").lower()
    return any(marker in error_text for marker in RATE_LIMIT_ERROR_MARKERS)


def api_limit_error_query():
    query = Q()
    for marker in RATE_LIMIT_ERROR_MARKERS:
        query |= Q(evaluation_error__icontains=marker)
    return query


def add_api_limit_warning(modeladmin, request, response_model):
    failed_limit_responses = response_model.objects.filter(
        evaluation_status="failed",
    ).filter(api_limit_error_query())
    count = failed_limit_responses.count()

    if not count:
        return

    latest_limit_at = failed_limit_responses.aggregate(
        latest=Max("last_evaluation_attempt_at"),
    )["latest"]
    latest_success_at = response_model.objects.filter(
        evaluation_status="completed",
    ).aggregate(latest=Max("last_evaluation_attempt_at"))["latest"]

    recovery_note = ""
    if latest_limit_at and latest_success_at and latest_success_at > latest_limit_at:
        recovery_note = (
            " A newer evaluation completed after the latest quota/rate-limit "
            "failure, so the OpenAI API key appears active again."
        )

    modeladmin.message_user(
        request,
        (
            f"OpenAI API quota/rate limit issue detected on {count} failed "
            "evaluation response(s). Evaluation retries may continue failing "
            "until the API limit resets or quota is increased."
            f"{recovery_note}"
        ),
        level=messages.WARNING,
    )


def evaluation_status_badge(obj):
    if obj.evaluation_status == "completed" or obj.evaluated:
        return format_html('<span style="color:green;font-weight:bold;">Evaluated</span>')

    if obj.evaluation_status == "failed":
        return format_html(
            '<span style="color:#b45309;font-weight:bold;">Error: {}</span>',
            obj.evaluation_error or "Evaluation failed",
        )

    if obj.evaluation_status == "transcribing":
        return format_html('<span style="color:#2563eb;">Transcribing</span>')

    if obj.evaluation_status == "evaluating":
        return format_html('<span style="color:#2563eb;">Evaluating</span>')

    if obj.answer_audio and not obj.transcribed_audio_data:
        return format_html('<span style="color:#6b7280;">Pending transcription</span>')

    return format_html('<span style="color:#6b7280;">Pending evaluation</span>')


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
        'evaluation_status',
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

    def evaluation_status(self, obj):
        return evaluation_status_badge(obj)

    evaluation_status.short_description = "Evaluation Status"
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
        'retry_evaluations_button',
        'download_pdf_button',
    )

    list_filter = ('mock_test', 'is_completed')
    search_fields = ('name', 'session_id', 'mock_test__title')
    ordering = ['-started_at']

    readonly_fields = (
        'session_id',
        'current_question_order',
        'completed_sections',
        'started_at',
        'completed_at',
        'total_score'
    )

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "mock_test", "session_id")
        }),
        ("Progress", {
            "fields": ('current_mocktest_section','current_question_order','completed_sections',"started_at", "completed_at", "is_completed")
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

    def changelist_view(self, request, extra_context=None):
        add_api_limit_warning(self, request, UserResponse)
        return super().changelist_view(request, extra_context=extra_context)

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

    def retry_evaluations_button(self, obj):
        url = reverse("admin:retry-session-evaluations", args=[obj.pk])
        return format_html(
            '<a style="padding:4px 8px;background:#2563eb;color:white;border-radius:4px;text-decoration:none;" href="{}">Retry</a>',
            url,
        )

    retry_evaluations_button.short_description = "Retry"

    # -------------------------
    # BULK ACTION
    # -------------------------
    actions = ['mark_as_completed', 'retry_failed_or_pending_evaluations', 'recalculate_scores']

    def mark_as_completed(self, request, queryset):
        updated = queryset.update(is_completed=True)
        self.message_user(request, f"{updated} sessions marked as completed.")
    mark_as_completed.short_description = "Mark selected sessions as completed"

    def _queue_retryable_session_responses(self, sessions):
        responses = (
            UserResponse.objects
            .filter(user_session__in=sessions)
            .filter(Q(evaluated=False) | Q(evaluation_status="failed"))
            .exclude(evaluation_status__in=["transcribing", "evaluating"])
            .select_related("question__subsection")
        )

        queued = 0
        for response in responses:
            queue_response_evaluation(response)
            queued += 1

        return queued

    def retry_failed_or_pending_evaluations(self, request, queryset):
        queued = self._queue_retryable_session_responses(queryset)

        self.message_user(
            request,
            f"{queued} failed/pending response(s) queued for Celery evaluation.",
        )
    retry_failed_or_pending_evaluations.short_description = (
        "Retry failed/pending evaluations for selected sessions"
    )

    def recalculate_scores(self, request, queryset):
        updated = 0
        for session in queryset:
            session.aggregate_scores()
            updated += 1

        self.message_user(request, f"{updated} session scores recalculated.")
    recalculate_scores.short_description = "Recalculate selected session scores"

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
            path(
                "retry-evaluations/<int:session_id>/",
                self.admin_site.admin_view(self.retry_session_evaluations_view),
                name="retry-session-evaluations",
            ),
        ]
        return custom_urls + urls

    def retry_session_evaluations_view(self, request, session_id):
        try:
            session = UserMockTestSession.objects.get(pk=session_id)
        except UserMockTestSession.DoesNotExist:
            raise Http404("Session not found")

        queued = self._queue_retryable_session_responses(
            UserMockTestSession.objects.filter(pk=session.pk)
        )

        self.message_user(
            request,
            f"{queued} failed/pending response(s) queued for {session.name}.",
        )

        return redirect(request.META.get("HTTP_REFERER") or "../")

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
        'evaluation_status',
        'retry_evaluation',
        'submitted_at',
    )

    list_filter = ('mock_test', 'evaluated', 'evaluation_status', 'evaluation_stage')
    search_fields = ('user_session__name', 'question__text')

    readonly_fields = (
        'submitted_at',
        'evaluation_status',
        'evaluation_stage',
        'evaluation_error',
        'evaluation_attempts',
        'last_evaluation_attempt_at',
    )
    list_per_page = 25
    actions = ['requeue_selected_evaluations']

    def changelist_view(self, request, extra_context=None):
        add_api_limit_warning(self, request, UserResponse)
        return super().changelist_view(request, extra_context=extra_context)

    def evaluation_status(self, obj):
        return evaluation_status_badge(obj)

    evaluation_status.short_description = "Evaluation Status"

    def retry_evaluation(self, obj):
        if obj.evaluation_status in ("transcribing", "evaluating"):
            return format_html('<span style="color:#6b7280;">In progress</span>')

        url = reverse("admin:mocktest_userresponse_retry_evaluation", args=[obj.pk])
        label = "Try again" if obj.evaluation_status == "failed" else "Requeue"
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    retry_evaluation.short_description = "Retry"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/retry-evaluation/",
                self.admin_site.admin_view(self.retry_evaluation_view),
                name="mocktest_userresponse_retry_evaluation",
            ),
        ]
        return custom_urls + urls

    def retry_evaluation_view(self, request, object_id):
        response = self.get_object(request, object_id)
        if response is None:
            raise Http404("Response not found")

        if response.evaluation_status in ("transcribing", "evaluating"):
            self.message_user(
                request,
                "This response is already being processed.",
                level="warning",
            )
        else:
            mode = queue_response_evaluation(response)
            self.message_user(
                request,
                f"Response {response.id} queued for {mode}.",
            )

        return redirect(request.META.get("HTTP_REFERER") or "../")

    def requeue_selected_evaluations(self, request, queryset):
        queued = 0
        for response in queryset.select_related("question__subsection"):
            if response.evaluation_status in ("transcribing", "evaluating"):
                continue
            queue_response_evaluation(response)
            queued += 1

        self.message_user(
            request,
            f"{queued} responses queued for Celery evaluation.",
        )
    requeue_selected_evaluations.short_description = "Requeue selected evaluations"


# =========================
# OTHER MODELS
# =========================

@admin.register(GlobalRubric)
class GlobalRubricAdmin(admin.ModelAdmin):
    list_display = ('key', 'rubric')
    search_fields = ('key',)


@admin.register(SingleResponse)
class SingleResponseAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'question',
        'evaluated',
        'evaluation_status',
        'retry_evaluation',
        'submitted_at',
    )
    list_filter = (
        'question__question_type',
        'name',
        'evaluated',
        'evaluation_status',
        'evaluation_stage',
    )
    readonly_fields = (
        'submitted_at',
        'evaluation_status',
        'evaluation_stage',
        'evaluation_error',
        'evaluation_attempts',
        'last_evaluation_attempt_at',
    )
    ordering = ['-submitted_at']
    actions = ['requeue_selected_evaluations']

    def changelist_view(self, request, extra_context=None):
        add_api_limit_warning(self, request, SingleResponse)
        return super().changelist_view(request, extra_context=extra_context)

    def evaluation_status(self, obj):
        return evaluation_status_badge(obj)

    evaluation_status.short_description = "Evaluation Status"

    def retry_evaluation(self, obj):
        if obj.evaluation_status in ("transcribing", "evaluating"):
            return format_html('<span style="color:#6b7280;">In progress</span>')

        url = reverse("admin:mocktest_singleresponse_retry_evaluation", args=[obj.pk])
        label = "Try again" if obj.evaluation_status == "failed" else "Requeue"
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    retry_evaluation.short_description = "Retry"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/retry-evaluation/",
                self.admin_site.admin_view(self.retry_evaluation_view),
                name="mocktest_singleresponse_retry_evaluation",
            ),
        ]
        return custom_urls + urls

    def retry_evaluation_view(self, request, object_id):
        response = self.get_object(request, object_id)
        if response is None:
            raise Http404("Single response not found")

        if response.evaluation_status in ("transcribing", "evaluating"):
            self.message_user(
                request,
                "This response is already being processed.",
                level="warning",
            )
        else:
            mode = queue_response_evaluation(response)
            self.message_user(
                request,
                f"Single response {response.id} queued for {mode}.",
            )

        return redirect(request.META.get("HTTP_REFERER") or "../")

    def requeue_selected_evaluations(self, request, queryset):
        queued = 0
        for response in queryset.select_related("question__subsection"):
            if response.evaluation_status in ("transcribing", "evaluating"):
                continue
            queue_response_evaluation(response)
            queued += 1

        self.message_user(
            request,
            f"{queued} single responses queued for Celery evaluation.",
        )
    requeue_selected_evaluations.short_description = "Requeue selected evaluations"
