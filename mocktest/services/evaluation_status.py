from collections import Counter

from mocktest.models import UserResponse
from mocktest.services.duplicate_responses import duplicate_response_groups


ACTIVE_STATUSES = {"pending", "transcribing", "evaluating"}


def build_session_evaluation_status(session, include_responses=False):
    session.sync_evaluation_completion()
    responses = (
        UserResponse.objects
        .filter(user_session=session)
        .select_related("question__subsection")
        .order_by("submitted_at", "id")
    )
    responses = list(responses)

    counts = Counter(response.evaluation_status for response in responses)
    total = len(responses)
    completed = sum(
        1
        for response in responses
        if response.evaluated or response.evaluation_status == "completed"
    )
    failed = counts.get("failed", 0)
    active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    pending = max(total - completed - failed, 0)

    duplicate_groups = duplicate_response_groups(
        UserResponse.objects.filter(user_session=session)
    )
    duplicate_group_count = duplicate_groups.count()
    duplicate_extra_rows = sum(row["count"] - 1 for row in duplicate_groups)

    payload = {
        "session_id": session.session_id,
        "session_pk": session.pk,
        "exam_completed": session.is_completed,
        "exam_completed_at": session.completed_at,
        "student": session.name,
        "mock_test_id": str(session.mock_test_id),
        "mock_test_title": session.mock_test.title,
        "total_responses": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "active": active,
        "statuses": dict(counts),
        "duplicate_groups": duplicate_group_count,
        "duplicate_extra_rows": duplicate_extra_rows,
        "is_complete": total > 0 and completed == total,
        "has_failures": failed > 0,
        "has_duplicates": duplicate_group_count > 0,
        "can_download_final_pdf": (
            session.is_completed
            and total > 0
            and completed == total
            and duplicate_group_count == 0
        ),
    }

    if include_responses:
        payload["responses"] = [
            {
                "id": response.id,
                "question_id": response.question_id,
                "question_name": response.question.name,
                "subsection": (
                    response.question.subsection.name
                    if response.question and response.question.subsection
                    else None
                ),
                "evaluated": response.evaluated,
                "evaluation_status": response.evaluation_status,
                "evaluation_stage": response.evaluation_stage,
                "evaluation_error": response.evaluation_error,
                "submitted_at": response.submitted_at,
                "last_evaluation_attempt_at": response.last_evaluation_attempt_at,
            }
            for response in responses
        ]

    return payload


def can_download_session_pdf(session):
    return build_session_evaluation_status(session)["can_download_final_pdf"]
