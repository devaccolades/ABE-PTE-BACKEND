from mocktest.services.evaluation_breakdown import build_evaluation_breakdown


ACTIVE_JOB_STATUSES = {
    "waiting_dispatch",
    "dispatched",
    "processing",
    "waiting_retry",
}


def build_single_practice_status(response, job):
    """Return candidate-facing feedback and the persisted score explanation."""
    result = response.evaluation_result if isinstance(response.evaluation_result, dict) else {}
    evaluation = result.get("evaluation")
    if not isinstance(evaluation, dict):
        evaluation = {}

    status = _public_status(response, job)
    feedback = _feedback_payload(evaluation.get("feedback"))
    error = ""
    if status == "failed":
        error = response.evaluation_error or str(result.get("error") or "")

    payload = {
        "response_id": response.pk,
        "question": {
            "id": response.question_id,
            "name": response.question.name or f"Question {response.question_id}",
            "subsection": (
                response.question.subsection.name
                if response.question.subsection
                else ""
            ),
            "mock_test": {
                "id": str(response.question.mock_test_section.mock_test_id),
                "title": response.question.mock_test_section.mock_test.title,
            },
        },
        "status": status,
        "stage": response.evaluation_stage or _stage_for_job(job),
        "terminal": status in {"completed", "failed"},
        "retrying": job.status == "waiting_retry",
        "message": _status_message(status, feedback, error),
        "feedback": feedback,
        "transcript": _transcript_text(response.transcribed_audio_data),
        "error": error,
    }
    if status == "completed":
        payload["score_breakdown"] = build_evaluation_breakdown(response)
    return payload


def _public_status(response, job):
    if job.status == "completed" or (
        response.evaluated and response.evaluation_status == "completed"
    ):
        return "completed"
    if job.status in {"failed_permanent", "manual_review"}:
        return "failed"
    if job.status == "waiting_retry":
        return "retrying"
    if job.status in ACTIVE_JOB_STATUSES:
        if response.evaluation_status in {"transcribing", "evaluating"}:
            return response.evaluation_status
        return "pending"
    return "failed" if response.evaluation_status == "failed" else "pending"


def _stage_for_job(job):
    if job.status == "waiting_retry":
        return "retrying"
    if job.status == "processing":
        return "evaluation"
    return "queued"


def _status_message(status, feedback, error):
    if status == "completed":
        return feedback["summary"] or "Evaluation completed."
    if status == "failed":
        return error or "Evaluation could not be completed."
    if status == "transcribing":
        return "Your recording is being transcribed."
    if status == "evaluating":
        return "Your answer is being evaluated."
    if status == "retrying":
        return "Evaluation is temporarily delayed and will retry automatically."
    return "Your answer is queued for evaluation."


def _feedback_payload(raw_feedback):
    if isinstance(raw_feedback, str):
        return {
            "summary": raw_feedback.strip(),
            "details": [],
            "errors": [],
            "explanation": "",
            "observations": [],
        }

    if not isinstance(raw_feedback, dict):
        return {
            "summary": "",
            "details": [],
            "errors": [],
            "explanation": "",
            "observations": [],
        }

    excluded = {"summary", "details", "errors", "explanation"}
    observations = [
        {
            "label": str(key).replace("_", " ").title(),
            "value": value,
        }
        for key, value in raw_feedback.items()
        if key not in excluded and value not in (None, "", [], {})
    ]
    return {
        "summary": str(raw_feedback.get("summary") or "").strip(),
        "details": (
            raw_feedback.get("details")
            if isinstance(raw_feedback.get("details"), list)
            else []
        ),
        "errors": (
            raw_feedback.get("errors")
            if isinstance(raw_feedback.get("errors"), list)
            else []
        ),
        "explanation": str(raw_feedback.get("explanation") or "").strip(),
        "observations": observations,
    }


def _transcript_text(transcribed_audio_data):
    if not isinstance(transcribed_audio_data, dict):
        return ""
    transcription = transcribed_audio_data.get("transcription")
    if isinstance(transcription, dict) and transcription.get("text"):
        return str(transcription["text"]).strip()
    return str(transcribed_audio_data.get("text") or "").strip()
