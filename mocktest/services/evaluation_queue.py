import logging

from celery import chain

from examinor.scoring.task_contracts import has_usable_transcript
from mocktest.models import SingleResponse
from mocktest.services.evaluation_input import (
    question_requires_audio,
    response_input_issue,
)
from mocktest.tasks import (
    evaluate_single_response,
    evaluate_user_response,
    transcribe_single_task,
    transcribe_task,
)


logger = logging.getLogger(__name__)


class EvaluationQueueUnavailable(RuntimeError):
    pass


class EvaluationInputUnavailable(EvaluationQueueUnavailable):
    pass


def _save_input_failure(response, issue):
    response.evaluation_result = issue.as_result()
    response.evaluation_status = "failed"
    response.evaluation_stage = "submission"
    response.evaluation_error = issue.message
    response.save(
        update_fields=[
            "evaluation_result",
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
        ]
    )


def _save_queue_failure(response, error):
    error_type = error.__class__.__name__
    message = f"Evaluation queue unavailable ({error_type}). Retry when Celery/Redis is healthy."
    response.evaluation_result = {
        "ok": False,
        "stage": "queueing",
        "error": message,
    }
    response.evaluation_status = "failed"
    response.evaluation_stage = "queueing"
    response.evaluation_error = message
    response.save(
        update_fields=[
            "evaluation_result",
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
        ]
    )
    return message


def queue_response_evaluation(response):
    requires_audio = question_requires_audio(response.question)
    input_issue = response_input_issue(response)
    if input_issue:
        _save_input_failure(response, input_issue)
        raise EvaluationInputUnavailable(input_issue.message)

    response.evaluation_status = "pending"
    response.evaluation_stage = ""
    response.evaluation_error = ""
    response.save(
        update_fields=[
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
        ]
    )

    is_single = isinstance(response, SingleResponse)
    needs_transcription = (
        requires_audio
        and response.answer_audio
        and not has_usable_transcript(response.transcribed_audio_data)
    )

    try:
        if needs_transcription:
            transcribe = transcribe_single_task if is_single else transcribe_task
            evaluate = evaluate_single_response if is_single else evaluate_user_response
            chain(
                transcribe.s(response.id),
                evaluate.si(response.id, response.question_id),
            ).delay()
            return "transcription_and_evaluation"

        if is_single:
            evaluate_single_response.delay(response.id, response.question_id)
        else:
            evaluate_user_response.delay(response.id, response.question_id)
    except Exception as exc:
        logger.error(
            "Could not queue evaluation for %s id=%s error_type=%s",
            response.__class__.__name__,
            response.id,
            exc.__class__.__name__,
        )
        message = _save_queue_failure(response, exc)
        raise EvaluationQueueUnavailable(message) from exc

    return "evaluation"


def queue_user_response_evaluation(response):
    return queue_response_evaluation(response)
