"""OpenAI availability as seen by staff, derived from recent evaluation outcomes."""

from django.db.models import Max, Q
from django.urls import reverse

from mocktest.models import SingleResponse, UserResponse


BILLING_URL = "https://platform.openai.com/settings/organization/billing/"
CREDIT_MARKERS = ("credits exhausted", "insufficient_quota", "credit_balance_exhausted", "no credits remaining")
# Before credit exhaustion was reported separately it was stored as a rate limit.
RATE_LIMIT_MARKERS = ("rate limit", "too many requests", "429", "quota")
RESPONSE_MODELS = (UserResponse, SingleResponse)


def _matches(markers):
    query = Q()
    for marker in markers:
        query |= Q(evaluation_error__icontains=marker)
    return query


def _failures(markers, *, excluding=()):
    count, latest = 0, None
    for model in RESPONSE_MODELS:
        failed = model.objects.filter(evaluation_status="failed").filter(_matches(markers))
        if excluding:
            failed = failed.exclude(_matches(excluding))
        count += failed.count()
        latest = _later(latest, failed.aggregate(latest=Max("last_evaluation_attempt_at"))["latest"])
    return count, latest


def _later(*values):
    present = [value for value in values if value is not None]
    return max(present) if present else None


def openai_status():
    """Return the current OpenAI state for the dashboard and admin warnings.

    An outage is current when its latest failure is newer than the latest
    successful evaluation; once evaluations succeed again, earlier failures are
    reported as needing a retry.
    """
    credit_count, credit_latest = _failures(CREDIT_MARKERS)
    limit_count, limit_latest = _failures(RATE_LIMIT_MARKERS, excluding=CREDIT_MARKERS)
    last_success = None
    for model in RESPONSE_MODELS:
        last_success = _later(
            last_success,
            model.objects.filter(evaluation_status="completed")
            .aggregate(latest=Max("last_evaluation_attempt_at"))["latest"],
        )

    def current(latest):
        return latest is not None and (last_success is None or latest > last_success)

    status = {
        "affected": credit_count + limit_count,
        "last_success": last_success,
        "billing_url": BILLING_URL,
        "failed_url": reverse("admin:mocktest_userresponse_changelist") + "?evaluation_status__exact=failed",
        "single_failed_url": reverse("admin:mocktest_singleresponse_changelist") + "?evaluation_status__exact=failed",
    }
    if credit_count and current(credit_latest):
        return {**status, "state": "credits_exhausted", "tone": "danger", "since": credit_latest,
                "title": "OpenAI credits exhausted",
                "detail": "Speaking and writing evaluations are failing. Add credits, then retry the failed responses."}
    if limit_count and current(limit_latest):
        return {**status, "state": "rate_limited", "tone": "warning", "since": limit_latest,
                "title": "OpenAI is rejecting requests",
                "detail": "Rate limit or credits: evaluations are failing. Check the OpenAI billing page, then retry the failed responses."}
    detail = "Evaluations are completing normally."
    if status["affected"]:
        detail = (f"Working again. {status['affected']} response(s) failed during an earlier "
                  "OpenAI outage and need a retry.")
    return {**status, "state": "working", "tone": "success", "since": None,
            "title": "OpenAI working", "detail": detail}
