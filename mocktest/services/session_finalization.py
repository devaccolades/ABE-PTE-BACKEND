import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from mocktest.models import (
    Question,
    SessionQuestion,
    SessionResult,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.evaluation_input import question_requires_audio


MANIFEST_VERSION = "session-manifest-v1"
RESOLVED_STATUSES = {"answered", "skipped", "timed_out", "not_reached"}
SKILL_NAMES = ("speaking", "writing", "reading", "listening")


def ordered_mock_test_questions(mock_test):
    return (
        Question.objects.filter(mock_test_section__mock_test=mock_test)
        .select_related(
            "mock_test_section__section",
            "subsection",
        )
        .prefetch_related("options", "sub_questions__options")
        .order_by(
            "mock_test_section__order",
            "subsection__order",
            "id",
        )
    )


def create_session_manifest(session_id):
    with transaction.atomic():
        session = (
            UserMockTestSession.objects.select_for_update()
            .select_related("mock_test")
            .get(pk=session_id)
        )
        existing = session.question_manifest.count()
        if existing:
            update_fields = []
            if not session.manifest_version:
                session.manifest_version = MANIFEST_VERSION
                update_fields.append("manifest_version")
            if not session.mock_test_snapshot:
                session.mock_test_snapshot = {
                    "id": str(session.mock_test_id),
                    "title": session.mock_test.title,
                    "description": session.mock_test.description,
                    "total_score": session.mock_test.total_score,
                    "total_duration": session.mock_test.total_duration,
                }
                update_fields.append("mock_test_snapshot")
            if session.expected_question_count != existing:
                session.expected_question_count = existing
                update_fields.append("expected_question_count")
            if update_fields:
                session.save(update_fields=update_fields)
            return existing

        questions = list(ordered_mock_test_questions(session.mock_test))
        if not questions:
            raise ValueError("Cannot start a mock test with no questions.")

        manifest_rows = []
        for position, question in enumerate(questions, start=1):
            subsection = question.subsection
            mock_test_section = question.mock_test_section
            section = mock_test_section.section if mock_test_section else None
            manifest_rows.append(
                SessionQuestion(
                    session=session,
                    question=question,
                    question_id_snapshot=question.pk,
                    order=position,
                    mock_test_section_id_snapshot=mock_test_section.pk,
                    section_name=(section.name or "") if section else "",
                    section_order=mock_test_section.order,
                    subsection_name=subsection.name if subsection else "",
                    subsection_order=subsection.order if subsection else 0,
                    expected_input_type=(
                        "audio" if question_requires_audio(question) else "text"
                    ),
                    question_snapshot=_question_snapshot(question),
                    rubric_snapshot=(subsection.rubric or {}) if subsection else {},
                    trait_skill_map_snapshot=(
                        subsection.trait_skill_map or {}
                        if subsection
                        else {}
                    ),
                    skill_maxima_snapshot={
                        skill: float(getattr(question, f"{skill}_score_max") or 0)
                        for skill in SKILL_NAMES
                    },
                )
            )

        SessionQuestion.objects.bulk_create(manifest_rows)
        session.manifest_version = MANIFEST_VERSION
        session.mock_test_snapshot = {
            "id": str(session.mock_test_id),
            "title": session.mock_test.title,
            "description": session.mock_test.description,
            "total_score": session.mock_test.total_score,
            "total_duration": session.mock_test.total_duration,
        }
        session.expected_question_count = len(manifest_rows)
        session.save(
            update_fields=[
                "manifest_version",
                "mock_test_snapshot",
                "expected_question_count",
            ]
        )
        return len(manifest_rows)


def session_question_ids(session):
    if not session.manifest_version:
        return list(
            ordered_mock_test_questions(session.mock_test).values_list("id", flat=True)
        )
    return list(
        session.question_manifest.order_by("order").values_list(
            "question_id_snapshot",
            flat=True,
        )
    )


def mark_session_question_answered(session_id, question_id, response_id):
    with transaction.atomic():
        session = UserMockTestSession.objects.select_for_update().get(pk=session_id)
        if not session.manifest_version:
            return False
        response = UserResponse.objects.only(
            "id",
            "user_session_id",
            "question_id",
        ).get(pk=response_id)
        if response.user_session_id != session.pk or response.question_id != question_id:
            raise ValueError(
                "Response does not belong to the session question being resolved."
            )
        row = SessionQuestion.objects.select_for_update().get(
            session=session,
            question_id_snapshot=question_id,
        )
        row.status = "answered"
        row.response_id = response_id
        row.resolved_at = timezone.now()
        row.save(update_fields=["status", "response", "resolved_at"])
        _finish_submission_if_resolved(session)
        _recalculate_locked(session)
        return True


def mark_section_timed_out(session_id, mock_test_section_id):
    with transaction.atomic():
        session = UserMockTestSession.objects.select_for_update().get(pk=session_id)
        if not session.manifest_version:
            return 0
        updated = session.question_manifest.filter(
            mock_test_section_id_snapshot=mock_test_section_id,
            status="pending",
        ).update(status="timed_out", resolved_at=timezone.now())
        _finish_submission_if_resolved(session)
        _recalculate_locked(session)
        return updated


def complete_session_submission(session_id, remaining_status="not_reached"):
    if remaining_status not in RESOLVED_STATUSES - {"answered"}:
        raise ValueError(f"Unsupported remaining question status: {remaining_status}")
    with transaction.atomic():
        session = UserMockTestSession.objects.select_for_update().get(pk=session_id)
        if not session.manifest_version:
            changed = session.completed_at is None
            if changed:
                session.completed_at = timezone.now()
                session.save(update_fields=["completed_at"])
            return changed

        now = timezone.now()
        session.question_manifest.filter(status="pending").update(
            status=remaining_status,
            resolved_at=now,
        )
        changed = session.submission_completed_at is None
        if changed:
            session.submission_completed_at = now
            session.completed_at = session.completed_at or now
            session.save(
                update_fields=["submission_completed_at", "completed_at"]
            )
        _recalculate_locked(session)
        return changed


def recalculate_session_state(session_id):
    with transaction.atomic():
        session = UserMockTestSession.objects.select_for_update().get(pk=session_id)
        if not session.manifest_version:
            return None
        return _recalculate_locked(session)


def session_is_finalizable(session_id):
    session = UserMockTestSession.objects.get(pk=session_id)
    if not session.manifest_version:
        responses = session.userresponse_set.all()
        return bool(
            session.completed_at
            and responses.exists()
            and not responses.exclude(
                evaluated=True,
                evaluation_status="completed",
            ).exists()
        )
    state = _manifest_state(session)
    return state["finalizable"]


def current_session_result(session):
    if not session.finalized_result_version:
        return None
    return session.result_versions.filter(
        version=session.finalized_result_version,
    ).first()


def _finish_submission_if_resolved(session):
    if session.question_manifest.filter(status="pending").exists():
        return False
    if session.submission_completed_at:
        return False
    now = timezone.now()
    session.submission_completed_at = now
    session.completed_at = session.completed_at or now
    session.save(update_fields=["submission_completed_at", "completed_at"])
    return True


def _recalculate_locked(session):
    state = _manifest_state(session)
    responses = state["completed_responses"]
    awarded = {
        skill: sum(
            float(getattr(response, f"{skill}_score_awarded") or 0)
            for response in responses
        )
        for skill in SKILL_NAMES
    }
    maxima = {skill: 0.0 for skill in SKILL_NAMES}
    manifest_rows = list(session.question_manifest.order_by("order"))
    for row in manifest_rows:
        for skill in SKILL_NAMES:
            maxima[skill] += float(row.skill_maxima_snapshot.get(skill) or 0)

    skill_scores = {
        skill: {
            "awarded": round(awarded[skill], 4),
            "maximum": round(maxima[skill], 4),
            "scaled": _scaled_score(awarded[skill], maxima[skill]),
        }
        for skill in SKILL_NAMES
    }
    overall_score = _scaled_score(sum(awarded.values()), sum(maxima.values()))

    session.speaking_score_awarded = awarded["speaking"]
    session.writing_score_awarded = awarded["writing"]
    session.reading_score_awarded = awarded["reading"]
    session.listening_score_awarded = awarded["listening"]
    session.total_score = overall_score

    update_fields = [
        "speaking_score_awarded",
        "writing_score_awarded",
        "reading_score_awarded",
        "listening_score_awarded",
        "total_score",
    ]

    if not state["finalizable"]:
        session.is_completed = False
        session.finalized_at = None
        update_fields.extend(["is_completed", "finalized_at"])
        session.save(update_fields=update_fields)
        return None

    response_snapshot = _response_snapshot(manifest_rows)
    result_payload = {
        "engine_version": str(settings.EVALUATION_ENGINE_VERSION),
        "scoring_mode": session.scoring_mode,
        "expected_question_count": state["expected"],
        "resolved_question_count": state["resolved"],
        "evaluated_response_count": state["evaluated"],
        "skill_scores": skill_scores,
        "overall_score": overall_score,
        "responses": response_snapshot,
    }
    content_hash = _content_hash(result_payload)
    result = session.result_versions.filter(content_hash=content_hash).first()
    if result is None:
        latest_version = session.result_versions.aggregate(
            value=Max("version")
        )["value"] or 0
        result = SessionResult.objects.create(
            session=session,
            version=latest_version + 1,
            engine_version=result_payload["engine_version"],
            scoring_mode=session.scoring_mode,
            expected_question_count=state["expected"],
            resolved_question_count=state["resolved"],
            evaluated_response_count=state["evaluated"],
            skill_scores=skill_scores,
            overall_score=overall_score,
            response_snapshot=response_snapshot,
            content_hash=content_hash,
        )

    session.is_completed = True
    session.finalized_at = result.finalized_at
    session.finalized_result_version = result.version
    update_fields.extend(
        ["is_completed", "finalized_at", "finalized_result_version"]
    )
    session.save(update_fields=update_fields)
    return result


def _manifest_state(session):
    rows = list(session.question_manifest.only("status", "response_id"))
    expected = len(rows)
    resolved = sum(1 for row in rows if row.status in RESOLVED_STATUSES)
    response_ids = [row.response_id for row in rows if row.status == "answered"]
    answered_count = sum(1 for row in rows if row.status == "answered")
    responses = list(UserResponse.objects.filter(pk__in=response_ids))
    evaluated_responses = [
        response
        for response in responses
        if response.evaluated and response.evaluation_status == "completed"
    ]
    duplicate_groups = (
        UserResponse.objects.filter(user_session=session)
        .values("question_id")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .count()
    )
    finalizable = bool(
        session.submission_completed_at
        and expected > 0
        and expected == session.expected_question_count
        and resolved == expected
        and len(response_ids) == answered_count
        and len(evaluated_responses) == answered_count
        and duplicate_groups == 0
    )
    return {
        "expected": expected,
        "resolved": resolved,
        "evaluated": len(evaluated_responses),
        "answered": answered_count,
        "duplicates": duplicate_groups,
        "completed_responses": evaluated_responses,
        "finalizable": finalizable,
    }


def _question_snapshot(question):
    mock_test_section = question.mock_test_section
    section = mock_test_section.section if mock_test_section else None
    subsection = question.subsection
    return {
        "id": question.pk,
        "name": question.name,
        "text": question.text,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "correct_answer": question.correct_answer,
        "answer_explanation": question.answer_explanation,
        "reading_time": question.reading_time,
        "answering_time": question.answering_time,
        "audio": question.audio.name if question.audio else "",
        "image": question.image.name if question.image else "",
        "mocktest_section": {
            "id": mock_test_section.pk if mock_test_section else None,
            "section_id": section.pk if section else None,
            "section_name": (section.name or "") if section else "",
            "order": mock_test_section.order if mock_test_section else 0,
            "total_duration": (
                mock_test_section.total_duration if mock_test_section else None
            ),
        },
        "subsection": subsection.name if subsection else "",
        "subsection_instruction": (
            subsection.instructions if subsection else None
        ),
        "options": [
            {
                "id": option.pk,
                "text": option.option_text,
                "is_correct": option.is_correct,
                "order_position": option.order_position,
                "sub_question_id": option.sub_question_id,
            }
            for option in question.options.all()
        ],
        "sub_questions": [
            {
                "id": sub_question.pk,
                "blank_number": sub_question.blank_number,
                "text_before_blank": sub_question.text_before_blank,
                "text_after_blank": sub_question.text_after_blank,
                "correct_answer": sub_question.correct_answer,
                "options": [
                    {
                        "id": option.pk,
                        "text": option.option_text,
                        "is_correct": option.is_correct,
                        "order_position": option.order_position,
                    }
                    for option in sub_question.options.all()
                ],
            }
            for sub_question in question.sub_questions.all()
        ],
    }


def _response_snapshot(manifest_rows):
    snapshots = []
    response_ids = [row.response_id for row in manifest_rows if row.response_id]
    responses = {
        response.pk: response
        for response in UserResponse.objects.filter(pk__in=response_ids)
    }
    for row in manifest_rows:
        response = responses.get(row.response_id)
        snapshots.append(
            {
                "order": row.order,
                "question_id": row.question_id_snapshot,
                "section": row.section_name,
                "subsection": row.subsection_name,
                "status": row.status,
                "question": row.question_snapshot,
                "skill_maxima": row.skill_maxima_snapshot,
                "response": (
                    {
                        "id": response.pk,
                        "answer_data": response.answer_data,
                        "answer_audio": (
                            response.answer_audio.name
                            if response.answer_audio
                            else ""
                        ),
                        "transcribed_audio_data": response.transcribed_audio_data,
                        "evaluation_result": response.evaluation_result,
                        "scores": {
                            skill: float(
                                getattr(response, f"{skill}_score_awarded") or 0
                            )
                            for skill in SKILL_NAMES
                        },
                    }
                    if response
                    else None
                ),
            }
        )
    return snapshots


def _scaled_score(awarded, maximum):
    if maximum <= 0:
        return 0.0
    return round(min(max((awarded / maximum) * 90, 0), 90), 2)


def _content_hash(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
