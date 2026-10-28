from django.db.models import Count
from django.urls import reverse

from mocktest.models import MockTest, UserMockTestSession, UserResponse
from mocktest.services.openai_status import openai_status


def failed_evaluations_badge(request):
    return UserResponse.objects.filter(evaluation_status="failed").count()


def incomplete_sessions_badge(request):
    return UserMockTestSession.objects.filter(is_completed=False).count()


def dashboard_callback(request, context):
    latest_sessions = list(
        UserMockTestSession.objects.select_related("mock_test")
        .order_by("-started_at")[:8]
    )
    for session in latest_sessions:
        session.sync_evaluation_completion()

    response_counts = {
        row["evaluation_status"]: row["count"]
        for row in UserResponse.objects.values("evaluation_status").annotate(
            count=Count("id")
        )
    }
    completed = response_counts.get("completed", 0)
    failed = response_counts.get("failed", 0)
    processing = (
        response_counts.get("transcribing", 0)
        + response_counts.get("evaluating", 0)
    )
    pending = response_counts.get("pending", 0)
    api_status = openai_status()

    context.update(
        {
            "dashboard_metrics": [
                {
                    "label": "Active mock tests",
                    "value": MockTest.objects.filter(is_active=True).count(),
                    "icon": "assignment",
                    "url": reverse("admin:mocktest_mocktest_changelist"),
                    "tone": "primary",
                },
                {
                    "label": "Completed evaluations",
                    "value": completed,
                    "icon": "check_circle",
                    "url": reverse("admin:mocktest_userresponse_changelist")
                    + "?evaluation_status__exact=completed",
                    "tone": "success",
                },
                {
                    "label": "Processing",
                    "value": processing,
                    "icon": "sync",
                    "url": reverse("admin:mocktest_userresponse_changelist"),
                    "tone": "info",
                },
                {
                    "label": "Needs attention",
                    "value": failed + pending,
                    "icon": "error",
                    "url": reverse("admin:mocktest_userresponse_changelist"),
                    "tone": "danger" if failed else "warning",
                },
            ],
            "evaluation_health": {
                "completed": completed,
                "pending": pending,
                "processing": processing,
                "failed": failed,
            },
            "openai_status": api_status,
            "latest_sessions": latest_sessions,
            "session_list_url": reverse(
                "admin:mocktest_usermocktestsession_changelist"
            ),
            "response_list_url": reverse("admin:mocktest_userresponse_changelist"),
        }
    )
    return context
