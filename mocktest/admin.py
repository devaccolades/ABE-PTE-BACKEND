from django.contrib import admin, messages
from django.contrib.auth.models import Group, User
from django.urls import path, reverse
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils.html import format_html
from django.db.models import F, Max, Prefetch, Q
from unfold.admin import ModelAdmin, TabularInline

from .models import *
from .forms import MockTestAdminForm, QuestionAdminForm
from .services.pdf_service import generate_session_pdf
from .services.question_config import SUBQUESTION_SUBSECTIONS
from .services.evaluation_status import can_download_session_pdf
from .services.evaluation_input import response_input_issue
from .services.evaluation_queue import (
    EvaluationQueueUnavailable,
    queue_response_evaluation,
)


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
        return format_html('<span style="color:#22c55e;font-weight:bold;">Evaluated</span>')

    input_issue = response_input_issue(obj)
    if input_issue:
        return format_html(
            '<span style="color:#f59e0b;font-weight:bold;" title="{}">'
            "Replacement audio required</span>",
            input_issue.message,
        )

    if obj.evaluation_status == "failed":
        return format_html(
            '<span style="color:#ef4444;font-weight:bold;">Error: {}</span>',
            obj.evaluation_error or "Evaluation failed",
        )

    if obj.evaluation_status == "transcribing":
        return format_html('<span style="color:#0e9ed6;">Transcribing</span>')

    if obj.evaluation_status == "evaluating":
        return format_html('<span style="color:#0e9ed6;">Evaluating</span>')

    if obj.answer_audio and not obj.transcribed_audio_data:
        return format_html('<span style="color:#94a3b8;">Pending transcription</span>')

    return format_html('<span style="color:#94a3b8;">Pending evaluation</span>')


def audio_recording_link(obj):
    if not obj.answer_audio:
        return format_html('<span style="color:#94a3b8;">No audio</span>')

    try:
        exists = obj.answer_audio.storage.exists(obj.answer_audio.name)
    except OSError:
        exists = False

    if not exists:
        return format_html(
            '<span style="color:#ef4444;">File missing: {}</span>',
            obj.answer_audio.name,
        )

    return format_html(
        '<a href="{}" target="_blank" rel="noopener">Play audio</a>',
        obj.answer_audio.url,
    )


audio_recording_link.short_description = "Audio recording"


# =========================
# INLINES
# =========================

class SubSectionInline(TabularInline):
    model = SubSection
    extra = 1
    ordering = ['order']


class QuestionOptionInline(TabularInline):
    model = QuestionOption
    extra = 2
    fields = ['option_text', 'is_correct', 'order_position']
    show_change_link = True


class SubQuestionInline(TabularInline):
    model = SubQuestion
    extra = 1
    fields = ['blank_number', 'text_before_blank', 'text_after_blank', 'correct_answer']
    show_change_link = True


class MockTestSectionInline(TabularInline):
    model = MockTestSection
    extra = 1
    ordering = ['order']


class UserResponseInline(TabularInline):
    model = UserResponse
    extra = 0
    can_delete = False
    ordering = ['submitted_at']

    readonly_fields = (
        'question',
        'response_display',
        'audio_recording',
        'scores_display',
        'evaluation_status',
        'evaluated',
        'submitted_at',
    )

    # -------------------------
    # RESPONSE DISPLAY (SMART)
    # -------------------------
    def response_display(self, obj):
        if not obj.answer_data:
            return "-"
        return format_html(
            '<pre style="white-space:pre-wrap;max-width:400px;">{}</pre>',
            obj.answer_data,
        )

    response_display.short_description = "Response"

    def audio_recording(self, obj):
        return audio_recording_link(obj)

    audio_recording.short_description = "Audio recording"

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
class SectionAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('name',)
    search_fields = ('name',)
    inlines = [SubSectionInline]
    ordering = ['name']


@admin.register(SubSection)
class SubSectionAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('name', 'section', 'order')
    search_fields = ('name',)
    ordering = ['order']


@admin.register(Question)
class QuestionAdmin(ModelAdmin):
    form = QuestionAdminForm
    compressed_fields = True
    list_filter_submit = True
    warn_unsaved_form = True
    list_display = (
        'name', 'id', 'question_type', 'subsection',
        'explanation_status', 'explanation_draft_status',
        'reading_time', 'answering_time',
        'speaking_score_max', 'writing_score_max',
        'reading_score_max', 'listening_score_max'
    )

    search_fields = ('name', 'text', 'answer_explanation')
    list_filter = ('question_type', 'subsection')
    ordering = ['subsection__id', 'id']
    actions = ['publish_explanation_drafts']

    def get_inlines(self, request, obj=None):
        if (
            obj
            and obj.subsection
            and obj.subsection.name in SUBQUESTION_SUBSECTIONS
        ):
            return [SubQuestionInline]
        return [QuestionOptionInline]

    @admin.display(description="Explanation", boolean=True)
    def explanation_status(self, obj):
        return bool(obj.answer_explanation)

    @admin.display(description="AI draft", boolean=True)
    def explanation_draft_status(self, obj):
        return bool(obj.answer_explanation_draft)

    @admin.action(description="Publish reviewed explanation drafts")
    def publish_explanation_drafts(self, request, queryset):
        ready = queryset.exclude(answer_explanation_draft="")
        updated = ready.update(answer_explanation=F("answer_explanation_draft"))
        self.message_user(
            request,
            f"Published {updated} reviewed question explanation(s).",
        )


@admin.register(QuestionOption)
class QuestionOptionAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('id', 'get_question_name', 'get_blank_number', 'option_text', 'is_correct')
    search_fields = ('option_text', 'question__name')
    list_filter = ('is_correct',)
    ordering = ['question', 'id']

    def get_question_name(self, obj):
        return obj.question.name if obj.question else obj.sub_question.question.name

    def get_blank_number(self, obj):
        return obj.sub_question.blank_number if obj.sub_question else None


@admin.register(SubQuestion)
class SubQuestionAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('id', 'question', 'blank_number', 'correct_answer')
    search_fields = ('question__name', 'correct_answer')
    ordering = ['question', 'blank_number']
    inlines = [QuestionOptionInline]


@admin.register(MockTest)
class MockTestAdmin(ModelAdmin):
    form = MockTestAdminForm
    compressed_fields = True
    warn_unsaved_form = True
    list_display = (
        'title',
        'total_score',
        'total_duration',
        'is_active',
        'scoring_mode',
        'created_at',
    )
    list_filter = ('is_active', 'scoring_mode')
    search_fields = ('title', 'description')
    inlines = [MockTestSectionInline]
    ordering = ['-created_at']


@admin.register(MockTestSection)
class MockTestSectionAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('id', 'mock_test', 'section', 'order')
    list_filter = ('mock_test',)
    ordering = ['mock_test', 'order']


# =========================
# USER SESSION ADMIN (MAIN UX)
# =========================

@admin.register(UserMockTestSession)
class UserMockTestSessionAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True
    list_fullwidth = True

    list_display = (
        'name',
        'mock_test',
        'short_session_id',
        'scoring_mode',
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
        'is_completed',
        'scoring_mode',
        'total_score'
    )

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "mock_test", "session_id")
        }),
        ("Progress", {
            "fields": ('current_mocktest_section','current_question_order','completed_sections',"started_at", "completed_at", "is_completed", "scoring_mode")
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
            return format_html('<span style="color:#22c55e;font-weight:bold;">Completed</span>')
        if obj.completed_at:
            return format_html('<span style="color:#f59e0b;font-weight:bold;">Evaluation pending</span>')
        return format_html('<span style="color:#94a3b8;font-weight:bold;">Exam in progress</span>')
    status_badge.short_description = "Status"

    # -------------------------
    # PDF BUTTON
    # -------------------------
    def download_pdf_button(self, obj):
        if not can_download_session_pdf(obj):
            return format_html(
                '<span style="color:#94a3b8;" title="Available after every response is evaluated">Pending</span>'
            )
        return format_html(
            '<a class="button" href="download-pdf/{}/" target="_blank">PDF</a>',
            obj.pk
        )

    download_pdf_button.short_description = "PDF"

    def retry_evaluations_button(self, obj):
        url = reverse("admin:retry-session-evaluations", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Retry</a>',
            url,
        )

    retry_evaluations_button.short_description = "Retry"

    # -------------------------
    # BULK ACTION
    # -------------------------
    actions = ['sync_completion_status', 'retry_failed_or_pending_evaluations', 'recalculate_scores']

    def sync_completion_status(self, request, queryset):
        updated = 0
        for session in queryset:
            if session.sync_evaluation_completion():
                updated += 1
        self.message_user(request, f"{updated} session completion status(es) synchronized.")
    sync_completion_status.short_description = "Synchronize evaluation completion status"

    def _queue_retryable_session_responses(self, sessions):
        responses = (
            UserResponse.objects
            .filter(user_session__in=sessions)
            .filter(Q(evaluated=False) | Q(evaluation_status="failed"))
            .exclude(evaluation_status__in=["transcribing", "evaluating"])
            .select_related("question__subsection")
        )

        queued = 0
        queue_failures = 0
        non_retryable = 0
        for response in responses:
            if response_input_issue(response):
                non_retryable += 1
                continue
            try:
                queue_response_evaluation(response)
                queued += 1
            except EvaluationQueueUnavailable:
                queue_failures += 1

        return queued, queue_failures, non_retryable

    def retry_failed_or_pending_evaluations(self, request, queryset):
        queued, queue_failures, non_retryable = (
            self._queue_retryable_session_responses(queryset)
        )

        self.message_user(
            request,
            f"{queued} response(s) queued; {queue_failures} queueing failure(s); "
            f"{non_retryable} require replacement input.",
            level=(
                messages.ERROR
                if queue_failures
                else messages.WARNING if non_retryable else messages.SUCCESS
            ),
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

        queued, queue_failures, non_retryable = (
            self._queue_retryable_session_responses(
                UserMockTestSession.objects.filter(pk=session.pk)
            )
        )

        self.message_user(
            request,
            f"{queued} response(s) queued for {session.name}; "
            f"{queue_failures} queueing failure(s); {non_retryable} require "
            "replacement input.",
            level=(
                messages.ERROR
                if queue_failures
                else messages.WARNING if non_retryable else messages.SUCCESS
            ),
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

        if not can_download_session_pdf(session):
            self.message_user(
                request,
                "PDF download is unavailable until every submitted response is evaluated.",
                level=messages.WARNING,
            )
            return redirect(request.META.get("HTTP_REFERER") or "../")

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
class UserResponseAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True
    list_fullwidth = True
    list_display = (
        'user_session',
        'id',
        'mock_test',
        'question',
        'audio_recording',
        'evaluated',
        'evaluation_status',
        'retry_evaluation',
        'submitted_at',
    )

    list_filter = ('mock_test', 'evaluated', 'evaluation_status', 'evaluation_stage')
    search_fields = ('user_session__name', 'question__text')

    readonly_fields = (
        'submitted_at',
        'audio_recording',
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

    def audio_recording(self, obj):
        return audio_recording_link(obj)

    audio_recording.short_description = "Audio recording"

    def retry_evaluation(self, obj):
        input_issue = response_input_issue(obj)
        if input_issue:
            return format_html(
                '<span style="color:#f59e0b;">Replacement audio required</span>'
            )
        if obj.evaluation_status in ("transcribing", "evaluating"):
            return format_html('<span style="color:#94a3b8;">In progress</span>')

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

        input_issue = response_input_issue(response)
        if input_issue:
            self.message_user(
                request,
                input_issue.message,
                level=messages.WARNING,
            )
        elif response.evaluation_status in ("transcribing", "evaluating"):
            self.message_user(
                request,
                "This response is already being processed.",
                level="warning",
            )
        else:
            try:
                mode = queue_response_evaluation(response)
                self.message_user(
                    request,
                    f"Response {response.id} queued for {mode}.",
                )
            except EvaluationQueueUnavailable as exc:
                self.message_user(request, str(exc), level=messages.ERROR)

        return redirect(request.META.get("HTTP_REFERER") or "../")

    def requeue_selected_evaluations(self, request, queryset):
        queued = 0
        queue_failures = 0
        non_retryable = 0
        for response in queryset.select_related("question__subsection"):
            if response_input_issue(response):
                non_retryable += 1
                continue
            if response.evaluation_status in ("transcribing", "evaluating"):
                continue
            try:
                queue_response_evaluation(response)
                queued += 1
            except EvaluationQueueUnavailable:
                queue_failures += 1

        self.message_user(
            request,
            f"{queued} response(s) queued; {queue_failures} queueing failure(s); "
            f"{non_retryable} require replacement input.",
            level=(
                messages.ERROR
                if queue_failures
                else messages.WARNING if non_retryable else messages.SUCCESS
            ),
        )
    requeue_selected_evaluations.short_description = "Requeue selected evaluations"


class EvaluationAuditAdmin(ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EvaluationJob)
class EvaluationJobAdmin(EvaluationAuditAdmin):
    list_display = (
        "id",
        "response_type",
        "response_id",
        "question_id",
        "status",
        "current_attempt",
        "engine_version",
        "updated_at",
    )
    list_filter = ("response_type", "status", "engine_version")
    search_fields = ("=response_id", "=question_id", "input_hash", "lease_owner")
    ordering = ("-updated_at",)


@admin.register(EvaluationAttempt)
class EvaluationAttemptAdmin(EvaluationAuditAdmin):
    list_display = (
        "id",
        "job",
        "attempt_number",
        "stage",
        "provider",
        "model",
        "retryable",
        "started_at",
        "finished_at",
    )
    list_filter = ("stage", "provider", "model", "retryable", "error_category")
    search_fields = (
        "=job__response_id",
        "task_id",
        "provider_request_id",
        "error_code",
    )
    ordering = ("-started_at",)


@admin.register(EvaluationOutbox)
class EvaluationOutboxAdmin(EvaluationAuditAdmin):
    list_display = (
        "event_id",
        "job",
        "event_type",
        "publish_attempts",
        "published_at",
        "created_at",
    )
    list_filter = ("event_type", "published_at")
    search_fields = ("=event_id", "=job__response_id", "last_error")
    ordering = ("-created_at",)


# =========================
# OTHER MODELS
# =========================

@admin.register(GlobalRubric)
class GlobalRubricAdmin(ModelAdmin):
    compressed_fields = True
    list_display = ('key', 'rubric')
    search_fields = ('key',)


@admin.register(SingleResponse)
class SingleResponseAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True
    list_fullwidth = True
    list_display = (
        'name',
        'question',
        'audio_recording',
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
        'audio_recording',
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

    def audio_recording(self, obj):
        return audio_recording_link(obj)

    audio_recording.short_description = "Audio recording"

    def retry_evaluation(self, obj):
        input_issue = response_input_issue(obj)
        if input_issue:
            return format_html(
                '<span style="color:#f59e0b;">Replacement audio required</span>'
            )
        if obj.evaluation_status in ("transcribing", "evaluating"):
            return format_html('<span style="color:#94a3b8;">In progress</span>')

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

        input_issue = response_input_issue(response)
        if input_issue:
            self.message_user(
                request,
                input_issue.message,
                level=messages.WARNING,
            )
        elif response.evaluation_status in ("transcribing", "evaluating"):
            self.message_user(
                request,
                "This response is already being processed.",
                level="warning",
            )
        else:
            try:
                mode = queue_response_evaluation(response)
                self.message_user(
                    request,
                    f"Single response {response.id} queued for {mode}.",
                )
            except EvaluationQueueUnavailable as exc:
                self.message_user(request, str(exc), level=messages.ERROR)

        return redirect(request.META.get("HTTP_REFERER") or "../")

    def requeue_selected_evaluations(self, request, queryset):
        queued = 0
        queue_failures = 0
        non_retryable = 0
        for response in queryset.select_related("question__subsection"):
            if response_input_issue(response):
                non_retryable += 1
                continue
            if response.evaluation_status in ("transcribing", "evaluating"):
                continue
            try:
                queue_response_evaluation(response)
                queued += 1
            except EvaluationQueueUnavailable:
                queue_failures += 1

        self.message_user(
            request,
            f"{queued} single response(s) queued; {queue_failures} queueing failure(s); "
            f"{non_retryable} require replacement input.",
            level=(
                messages.ERROR
                if queue_failures
                else messages.WARNING if non_retryable else messages.SUCCESS
            ),
        )
    requeue_selected_evaluations.short_description = "Requeue selected evaluations"
