import os
import uuid
import subprocess
from celery import shared_task
from celery.exceptions import Retry
from billiard.exceptions import SoftTimeLimitExceeded

from examinor.services.rule_evaluator import run_rule_evaluation, uses_rule_evaluation
from .models import *
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.utils import timezone
from mocktest.services.transcription import transcribe_and_analyse
from examinor.scoring.task_contracts import (
    PayloadStatus,
    has_usable_transcript,
    inspect_answer_payload,
)
from examinor.scoring.validators import (
    rubric_maxima,
    validate_and_normalize_evaluation_result,
)
from examinor.services.orchestrator import build_task_rubric
from examinor.services.orchestrator import run_evaluation_for_subsection


class EvaluationTaskFailed(RuntimeError):
    pass


def save_evaluation_failure(response, stage, error, extra=None):
    result = {
        "ok": False,
        "stage": stage,
        "error": str(error),
    }
    if extra:
        result.update(extra)
    response.evaluation_result = result
    response.evaluation_status = "failed"
    response.evaluation_stage = stage
    response.evaluation_error = str(error)
    response.save(
        update_fields=[
            "evaluation_result",
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
        ]
    )


def mark_evaluation_attempt(response, status, stage):
    response.evaluation_status = status
    response.evaluation_stage = stage
    response.evaluation_error = ""
    response.evaluation_attempts += 1
    response.last_evaluation_attempt_at = timezone.now()
    response.save(
        update_fields=[
            "evaluation_status",
            "evaluation_stage",
            "evaluation_error",
            "evaluation_attempts",
            "last_evaluation_attempt_at",
        ]
    )


def is_transient_evaluation_error(evaluation_result):
    if not isinstance(evaluation_result, dict):
        return False

    error = str(evaluation_result.get("error", "")).lower()
    transient_terms = (
        "timeout",
        "rate limit",
        "connection",
        "temporarily",
        "service unavailable",
    )
    return any(term in error for term in transient_terms)


def validation_rubric_for_subsection(subsection):
    if uses_rule_evaluation(subsection):
        return subsection.rubric
    return build_task_rubric(subsection)


def build_unanswered_evaluation_result(subsection):
    maxima = rubric_maxima(validation_rubric_for_subsection(subsection))
    if not maxima:
        maxima = {"score": 1.0}

    scores = {
        key: {"score": 0.0, "max": max_score}
        for key, max_score in maxima.items()
    }
    return {
        "ok": True,
        "evaluation": {
            "scores": scores,
            "weighted_score": 0.0,
            "max_score": sum(maxima.values()),
            "answer_status": PayloadStatus.UNANSWERED.value,
            "evaluation_source": "system",
            "feedback": {
                "summary": "No answer was submitted. This question received zero.",
                "details": [],
            },
        },
    }


def inspect_response_answer(response, subsection_name):
    return inspect_answer_payload(
        subsection_name,
        response.answer_data,
        has_audio=bool(response.answer_audio and response.answer_audio.name),
        has_transcript=has_usable_transcript(response.transcribed_audio_data),
    )


def validate_evaluation_or_fail(response, evaluation_result, subsection):
    is_valid, normalized_result, error = validate_and_normalize_evaluation_result(
        evaluation_result,
        validation_rubric_for_subsection(subsection),
    )

    if is_valid:
        return normalized_result

    save_evaluation_failure(
        response,
        "scoring",
        error,
        {"raw_evaluation": evaluation_result},
    )
    return None


def normalize_queued_question_id(response, question_id):
    try:
        queued_question_id = int(question_id)
    except (TypeError, ValueError):
        error = f"Queued question_id {question_id!r} is not a valid integer"
        save_evaluation_failure(response, "evaluation", error)
        return None, error

    if response.question_id != queued_question_id:
        error = (
            f"Queued question_id {queued_question_id} does not match "
            f"response question_id {response.question_id}"
        )
        save_evaluation_failure(response, "evaluation", error)
        return None, error

    return queued_question_id, None


    # print("Running Whisper transcription...")

    # if not os.path.exists(input_path):
    #     return {"error": "Audio file not found", "path": input_path}
    # try:
    #     subprocess.run(
    #         [
    #             "ffmpeg", "-y",
    #             "-i", input_path,
    #             "-ar", "16000",
    #             "-ac", "1",
    #             output_path
    #         ],
    #         check=True,
    #         stdout=subprocess.DEVNULL,
    #         stderr=subprocess.DEVNULL
    #     )
    # except Exception as e:
    #     return {
    #         "error": "FFmpeg conversion failed",
    #         "details": str(e)
    #     }

    # try:
    #     transcription = transcribe_and_analyse(output_path)
    # except Exception as e:
    #     return {
    #         "error": "Failed to transcribe audio",
    #         "details": str(e)
    #     }

    # user_response = UserResponse.objects.get(id=user_response_id)
    # user_response.transcribed_audio_data = transcription
    # user_response.save()

    # # cleanup
    # os.remove(input_path)
    # os.remove(output_path)

    # return {"status": "success", "transcription": transcription}
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def transcribe_task(self,user_response_id,):
    user_response = UserResponse.objects.get(id=user_response_id)
    mark_evaluation_attempt(user_response, "transcribing", "transcription")

    if not user_response.answer_audio:
        error = "Audio answer file is missing; transcription cannot start."
        save_evaluation_failure(user_response, "transcription", error)
        raise EvaluationTaskFailed(error)

    input_path = user_response.answer_audio.path
    output_path = f"/tmp/{uuid.uuid4()}.wav"

    try:
        # Convert audio to wav
        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            output_path
        ], check=True)

        transcript = transcribe_and_analyse(output_path)

        user_response.transcribed_audio_data = transcript
        user_response.save()
    except Exception as e:
        save_evaluation_failure(user_response, "transcription", e)
        raise self.retry(exc=e)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

    return user_response_id

from django.db import transaction

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def evaluate_user_response(self, user_answer_id, question_id):
    print("Evaluation begins...")

    try:
        try:
            user_answer = (
                UserResponse.objects
                .select_related("question__subsection", "user_session")
                .get(id=user_answer_id)
            )
        except UserResponse.DoesNotExist:
            return {"error": f"UserResponse {user_answer_id} does not exist"}

        mark_evaluation_attempt(user_answer, "evaluating", "evaluation")

        queued_question_id, error = normalize_queued_question_id(
            user_answer,
            question_id,
        )
        if error:
            raise EvaluationTaskFailed(error)

        question = user_answer.question

        if not question.subsection:
            error = f"Question {question.id} has no subsection assigned"
            save_evaluation_failure(user_answer, "evaluation", error)
            raise EvaluationTaskFailed(error)
        
        evaluation_payload = {}

        if user_answer.answer_data:
            evaluation_payload["answer_data"] = user_answer.answer_data

        if (
            question.correct_answer
            and question.subsection.name != "highlight_incorrect_words"
        ):
            evaluation_payload["reference_answer"] = question.correct_answer

        subsection = question.subsection.name
        subsection_obj = question.subsection

        if subsection_obj.ai_input_type == "audio":
            if not user_answer.transcribed_audio_data:
                error = (
                    "Audio transcription is missing; queue transcription before evaluation."
                    if user_answer.answer_audio
                    else "Audio answer file is missing; transcription and evaluation cannot start."
                )
                save_evaluation_failure(user_answer, "transcription", error)
                raise EvaluationTaskFailed(error)
            evaluation_payload["transcribed_audio_data"] = user_answer.transcribed_audio_data

        payload_inspection = inspect_response_answer(user_answer, subsection)

        if payload_inspection.status == PayloadStatus.UNANSWERED:
            evaluation_result = build_unanswered_evaluation_result(subsection_obj)
        elif uses_rule_evaluation(subsection_obj):
            evaluation_result = run_rule_evaluation(
                user_answer=user_answer,
                question=question,
                subsection=subsection_obj,
            )
        else:
            # -------------------------
            # AI-BASED EVALUATION
            # -------------------------

            evaluation_result = run_evaluation_for_subsection(
                subsection_obj,
                question.text,
                evaluation_payload
            )

        if not evaluation_result.get("ok", False):
            user_answer.evaluation_result = evaluation_result
            user_answer.evaluation_status = "failed"
            user_answer.evaluation_stage = "evaluation"
            user_answer.evaluation_error = evaluation_result.get("error") or "Evaluation failed"
            user_answer.save(
                update_fields=[
                    "evaluation_result",
                    "evaluation_status",
                    "evaluation_stage",
                    "evaluation_error",
                ]
            )
            if is_transient_evaluation_error(evaluation_result):
                raise self.retry(exc=Exception(evaluation_result.get("error")))
            raise EvaluationTaskFailed(user_answer.evaluation_error)

        evaluation_result = validate_evaluation_or_fail(
            user_answer,
            evaluation_result,
            subsection_obj,
        )
        if evaluation_result is None:
            raise EvaluationTaskFailed("Evaluation validation failed")

        with transaction.atomic():

            # 1️⃣ Save raw evaluation output
            user_answer.evaluation_result = evaluation_result
            user_answer.save(update_fields=["evaluation_result"])

            # 2️⃣ Apply trait → skill routing (UserResponse)
            user_answer.apply_skill_scores()

            # 3️⃣ Aggregate to session totals (UserMockTestSession)
            user_answer.user_session.aggregate_scores()

        return {
            "status": "success",
            "user_answer_id": user_answer_id,
            "question_id": queued_question_id,
            "subsection": subsection,
            "evaluation_result": evaluation_result,
        }

    except Retry:
        raise
    except EvaluationTaskFailed:
        raise
    except SoftTimeLimitExceeded:
        error = "Evaluation task exceeded its soft time limit"
        try:
            user_answer = UserResponse.objects.get(id=user_answer_id)
            save_evaluation_failure(user_answer, "evaluation", error)
        except UserResponse.DoesNotExist:
            pass
        raise self.retry(exc=TimeoutError(error))
    except Exception as e:
        try:
            user_answer = UserResponse.objects.get(id=user_answer_id)
            save_evaluation_failure(user_answer, "evaluation", e)
        except UserResponse.DoesNotExist:
            pass
        raise
    


##### single answer gimmiks


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def transcribe_single_task(self,user_response_id,):
    user_response = SingleResponse.objects.get(id=user_response_id)
    mark_evaluation_attempt(user_response, "transcribing", "transcription")

    if not user_response.answer_audio:
        error = "Audio answer file is missing; transcription cannot start."
        save_evaluation_failure(user_response, "transcription", error)
        raise EvaluationTaskFailed(error)

    input_path = user_response.answer_audio.path
    output_path = f"/tmp/{uuid.uuid4()}.wav"

    try:
        # Convert audio to wav
        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            output_path
        ], check=True)

        transcript = transcribe_and_analyse(output_path)

        user_response.transcribed_audio_data = transcript
        user_response.save()
    except Exception as e:
        save_evaluation_failure(user_response, "transcription", e)
        raise self.retry(exc=e)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)

    return user_response_id

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def evaluate_single_response(self, user_answer_id, question_id):
    print("Evaluation begins...")

    try:
        try:
            user_answer = (
                SingleResponse.objects
                .select_related("question__subsection")
                .get(id=user_answer_id)
            )
        except SingleResponse.DoesNotExist:
            return {"error": f"UserResponse {user_answer_id} does not exist"}

        mark_evaluation_attempt(user_answer, "evaluating", "evaluation")

        queued_question_id, error = normalize_queued_question_id(
            user_answer,
            question_id,
        )
        if error:
            raise EvaluationTaskFailed(error)

        question = user_answer.question

        if not question.subsection:
            error = f"Question {question.id} has no subsection assigned"
            save_evaluation_failure(user_answer, "evaluation", error)
            raise EvaluationTaskFailed(error)
        
        evaluation_payload = {}

        if user_answer.answer_data:
            evaluation_payload["answer_data"] = user_answer.answer_data

        if (
            question.correct_answer
            and question.subsection.name != "highlight_incorrect_words"
        ):
            evaluation_payload["reference_answer"] = question.correct_answer

        subsection = question.subsection.name
        subsection_obj = question.subsection

        if subsection_obj.ai_input_type == "audio":
            if not user_answer.transcribed_audio_data:
                error = (
                    "Audio transcription is missing; queue transcription before evaluation."
                    if user_answer.answer_audio
                    else "Audio answer file is missing; transcription and evaluation cannot start."
                )
                save_evaluation_failure(user_answer, "transcription", error)
                raise EvaluationTaskFailed(error)
            evaluation_payload["transcribed_audio_data"] = user_answer.transcribed_audio_data

        payload_inspection = inspect_response_answer(user_answer, subsection)

        if payload_inspection.status == PayloadStatus.UNANSWERED:
            evaluation_result = build_unanswered_evaluation_result(subsection_obj)
        elif uses_rule_evaluation(subsection_obj):
            evaluation_result = run_rule_evaluation(
                user_answer=user_answer,
                question=question,
                subsection=subsection_obj,
            )
        else:
            # -------------------------
            # AI-BASED EVALUATION
            # -------------------------

            evaluation_result = run_evaluation_for_subsection(
                subsection_obj,
                question.text,
                evaluation_payload
            )

        if not evaluation_result.get("ok", False):
            user_answer.evaluation_result = evaluation_result
            user_answer.evaluation_status = "failed"
            user_answer.evaluation_stage = "evaluation"
            user_answer.evaluation_error = evaluation_result.get("error") or "Evaluation failed"
            user_answer.save(
                update_fields=[
                    "evaluation_result",
                    "evaluation_status",
                    "evaluation_stage",
                    "evaluation_error",
                ]
            )
            if is_transient_evaluation_error(evaluation_result):
                raise self.retry(exc=Exception(evaluation_result.get("error")))
            raise EvaluationTaskFailed(user_answer.evaluation_error)

        evaluation_result = validate_evaluation_or_fail(
            user_answer,
            evaluation_result,
            subsection_obj,
        )
        if evaluation_result is None:
            raise EvaluationTaskFailed("Evaluation validation failed")

        with transaction.atomic():

            # 1️⃣ Save raw evaluation output
            user_answer.evaluation_result = evaluation_result
            user_answer.save(update_fields=["evaluation_result"])

            # 2️⃣ Apply trait → skill routing (UserResponse)
            user_answer.apply_skill_scores()

            # 3️⃣ Aggregate to session totals (UserMockTestSession)
            # user_answer.user_session.aggregate_scores()

        return {
            "status": "success",
            "user_answer_id": user_answer_id,
            "question_id": queued_question_id,
            "subsection": subsection,
            "evaluation_result": evaluation_result,
        }

    except Retry:
        raise
    except EvaluationTaskFailed:
        raise
    except SoftTimeLimitExceeded:
        error = "Evaluation task exceeded its soft time limit"
        try:
            user_answer = SingleResponse.objects.get(id=user_answer_id)
            save_evaluation_failure(user_answer, "evaluation", error)
        except SingleResponse.DoesNotExist:
            pass
        raise self.retry(exc=TimeoutError(error))
    except Exception as e:
        try:
            user_answer = SingleResponse.objects.get(id=user_answer_id)
            save_evaluation_failure(user_answer, "evaluation", e)
        except SingleResponse.DoesNotExist:
            pass
        raise


@shared_task
def recover_stale_evaluations(stale_after_minutes=None, batch_size=None):
    """Requeue active evaluations abandoned by an interrupted worker."""
    from django.conf import settings
    from mocktest.services.evaluation_queue import queue_response_evaluation

    stale_after_minutes = (
        settings.EVALUATION_STALE_AFTER_MINUTES
        if stale_after_minutes is None
        else int(stale_after_minutes)
    )
    batch_size = (
        settings.EVALUATION_RECOVERY_BATCH_SIZE
        if batch_size is None
        else int(batch_size)
    )
    if stale_after_minutes < 1:
        raise ValueError("stale_after_minutes must be at least 1")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    cutoff = timezone.now() - timezone.timedelta(minutes=stale_after_minutes)
    recovered = 0
    processed = 0
    queue_failures = 0
    by_model = {}

    for response_model in (UserResponse, SingleResponse):
        remaining = batch_size - processed
        if remaining <= 0:
            break

        response_ids = list(
            response_model.objects.filter(
                evaluated=False,
                evaluation_status__in=("transcribing", "evaluating"),
                last_evaluation_attempt_at__lte=cutoff,
            )
            .order_by("last_evaluation_attempt_at", "id")
            .values_list("id", flat=True)[:remaining]
        )

        model_recovered = 0
        for response_id in response_ids:
            processed += 1
            response = (
                response_model.objects.select_related("question__subsection")
                .filter(
                    id=response_id,
                    evaluated=False,
                    evaluation_status__in=("transcribing", "evaluating"),
                    last_evaluation_attempt_at__lte=cutoff,
                )
                .first()
            )
            if response is None:
                continue

            try:
                queue_response_evaluation(response)
            except Exception as exc:
                save_evaluation_failure(response, "queueing", exc)
                queue_failures += 1
                continue

            recovered += 1
            model_recovered += 1

        by_model[response_model.__name__] = model_recovered

    return {
        "recovered": recovered,
        "processed": processed,
        "queue_failures": queue_failures,
        "by_model": by_model,
        "stale_after_minutes": stale_after_minutes,
    }
    
