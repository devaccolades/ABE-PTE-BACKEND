from collections import Counter

from mocktest.models import UserResponse
from mocktest.services.duplicate_responses import duplicate_response_groups
from mocktest.services.evaluation_input import response_input_issue
from mocktest.services.session_finalization import current_session_result


ACTIVE_STATUSES = {"pending", "transcribing", "evaluating"}


def build_session_evaluation_status(session, include_responses=False):
    session.sync_evaluation_completion()
    session.refresh_from_db()
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
    input_required = sum(
        1 for response in responses if response_input_issue(response)
    )
    active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    pending = max(total - completed - failed, 0)

    duplicate_groups = duplicate_response_groups(
        UserResponse.objects.filter(user_session=session)
    )
    duplicate_group_count = duplicate_groups.count()
    duplicate_extra_rows = sum(row["count"] - 1 for row in duplicate_groups)

    manifest_counts = Counter()
    expected_questions = total
    resolved_questions = total
    finalized_result = None
    if session.manifest_version:
        manifest_counts = Counter(
            session.question_manifest.values_list("status", flat=True)
        )
        expected_questions = session.expected_question_count
        resolved_questions = expected_questions - manifest_counts.get("pending", 0)
        finalized_result = current_session_result(session)

    payload = {
        "session_id": session.session_id,
        "session_pk": session.pk,
        "exam_completed": session.is_completed,
        "exam_completed_at": (
            session.finalized_at
            if session.manifest_version
            else session.completed_at if session.is_completed else None
        ),
        "submission_completed_at": (
            session.submission_completed_at or session.completed_at
        ),
        "student": session.name,
        "mock_test_id": str(session.mock_test_id),
        "mock_test_title": (
            session.mock_test_snapshot.get("title")
            if session.mock_test_snapshot
            else session.mock_test.title
        ),
        "scoring_mode": session.scoring_mode,
        "manifest_version": session.manifest_version,
        "expected_questions": expected_questions,
        "resolved_questions": resolved_questions,
        "answered_questions": (
            manifest_counts.get("answered", 0)
            if session.manifest_version
            else total
        ),
        "skipped_questions": manifest_counts.get("skipped", 0),
        "timed_out_questions": manifest_counts.get("timed_out", 0),
        "not_reached_questions": manifest_counts.get("not_reached", 0),
        "pending_questions": manifest_counts.get("pending", 0),
        "total_responses": total,
        "completed": completed,
        "failed": failed,
        "input_required": input_required,
        "pending": pending,
        "active": active,
        "statuses": dict(counts),
        "duplicate_groups": duplicate_group_count,
        "duplicate_extra_rows": duplicate_extra_rows,
        "is_complete": session.is_completed,
        "has_failures": failed > 0,
        "has_duplicates": duplicate_group_count > 0,
        "finalized_at": session.finalized_at,
        "finalized_result_version": session.finalized_result_version,
        "can_download_final_pdf": (
            session.is_completed
            and (
                bool(finalized_result)
                if session.manifest_version
                else total > 0 and completed == total
            )
            and duplicate_group_count == 0
        ),
    }

    if include_responses:
        response_details = []
        for response in responses:
            input_issue = response_input_issue(response)
            response_details.append({
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
                "evaluation_code": input_issue.code if input_issue else None,
                "retryable": bool(
                    response.evaluation_status == "failed" and not input_issue
                ),
                "submitted_at": response.submitted_at,
                "last_evaluation_attempt_at": response.last_evaluation_attempt_at,
            })
        payload["responses"] = response_details
        if session.manifest_version:
            payload["questions"] = list(
                session.question_manifest.order_by("order").values(
                    "order",
                    "question_id_snapshot",
                    "section_name",
                    "subsection_name",
                    "expected_input_type",
                    "status",
                    "response_id",
                    "resolved_at",
                )
            )

    return payload


def can_download_session_pdf(session):
    return build_session_evaluation_status(session)["can_download_final_pdf"]
