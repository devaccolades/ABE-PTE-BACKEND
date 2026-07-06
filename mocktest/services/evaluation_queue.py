from celery import chain

from mocktest.models import SingleResponse
from mocktest.tasks import (
    evaluate_single_response,
    evaluate_user_response,
    transcribe_single_task,
    transcribe_task,
)


def queue_response_evaluation(response):
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

    subsection = response.question.subsection
    is_single = isinstance(response, SingleResponse)
    needs_transcription = (
        subsection
        and subsection.ai_input_type == "audio"
        and response.answer_audio
        and not response.transcribed_audio_data
    )

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

    return "evaluation"


def queue_user_response_evaluation(response):
    return queue_response_evaluation(response)
