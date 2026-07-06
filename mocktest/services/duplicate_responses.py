from django.db.models import Count, Max, Min


def duplicate_response_groups(responses):
    return (
        responses.values("user_session_id", "question_id")
        .annotate(
            count=Count("id"),
            first_submitted_at=Min("submitted_at"),
            last_submitted_at=Max("submitted_at"),
        )
        .filter(count__gt=1)
        .order_by("-count", "first_submitted_at")
    )


def recommended_keep_response(responses):
    return sorted(
        responses,
        key=lambda response: (
            response.evaluation_status == "completed" or response.evaluated,
            response.submitted_at,
            response.id,
        ),
        reverse=True,
    )[0]
