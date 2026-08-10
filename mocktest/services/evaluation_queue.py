import logging

from django.db import transaction

from mocktest.services.evaluation_input import (
    response_input_issue,
)
from mocktest.services.evaluation_jobs import (
    dispatch_outbox_event,
    prepare_evaluation_dispatch,
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
    message = (
        f"Evaluation queue unavailable ({error_type}). Dispatch is saved and will "
        "retry automatically when Celery/Redis is healthy."
    )
    response.evaluation_result = {
        "ok": False,
        "stage": "queueing",
        "code": "evaluation_dispatch_pending",
        "retryable": True,
        "error": message,
    }
    response.evaluation_status = "pending"
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


def prepare_response_evaluation(response):
    input_issue = response_input_issue(response)
    if input_issue:
        _save_input_failure(response, input_issue)
        raise EvaluationInputUnavailable(input_issue.message)

    with transaction.atomic():
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
        job, event = prepare_evaluation_dispatch(response)
        if hasattr(response, "user_session_id"):
            from mocktest.services.session_finalization import (
                recalculate_session_state,
            )

            recalculate_session_state(response.user_session_id)

    return job, event


def dispatch_prepared_evaluation(response, job, event):

    if event is None:
        return "already_completed" if job.status == "completed" else "already_processing"

    outcome = dispatch_outbox_event(event.event_id)
    if outcome["status"] == "failed":
        exc = outcome["error"]
        logger.error(
            "Could not queue evaluation for %s id=%s error_type=%s",
            response.__class__.__name__,
            response.id,
            exc.__class__.__name__,
        )
        message = _save_queue_failure(response, exc)
        raise EvaluationQueueUnavailable(message) from exc
    return outcome["mode"]


def queue_response_evaluation(response):
    job, event = prepare_response_evaluation(response)
    return dispatch_prepared_evaluation(response, job, event)


def queue_user_response_evaluation(response):
    return queue_response_evaluation(response)
