import hashlib
import json
import uuid

from celery import chain
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from examinor.scoring.contracts import SCORING_VERSION
from examinor.scoring.task_contracts import has_usable_transcript
from mocktest.models import (
    EvaluationAttempt,
    EvaluationJob,
    EvaluationOutbox,
    SingleResponse,
    UserResponse,
)
from mocktest.services.evaluation_input import question_requires_audio


OUTBOX_LOCK_SECONDS = 120


def evaluation_engine_version():
    return str(
        getattr(settings, "EVALUATION_ENGINE_VERSION", "pte-evaluation-v1")
    )


def response_type_for(response):
    if isinstance(response, UserResponse):
        return "user"
    if isinstance(response, SingleResponse):
        return "single"
    raise TypeError(f"Unsupported evaluation response type: {type(response).__name__}")


def build_input_snapshot(response):
    audio = {"name": "", "size": None}
    if response.answer_audio and response.answer_audio.name:
        audio["name"] = response.answer_audio.name
        try:
            audio["size"] = response.answer_audio.size
        except (FileNotFoundError, OSError):
            audio["size"] = None

    return {
        "response_type": response_type_for(response),
        "response_id": response.pk,
        "question_id": response.question_id,
        "answer_data": response.answer_data,
        "answer_audio": audio,
        "transcribed_audio_data": response.transcribed_audio_data,
    }


def input_snapshot_hash(snapshot):
    payload = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def prepare_evaluation_dispatch(response):
    snapshot = build_input_snapshot(response)
    response_type = snapshot["response_type"]
    input_hash = input_snapshot_hash(snapshot)
    engine_version = evaluation_engine_version()

    with transaction.atomic():
        job, _ = EvaluationJob.objects.get_or_create(
            response_type=response_type,
            response_id=response.pk,
            input_hash=input_hash,
            engine_version=engine_version,
            revision=1,
            defaults={
                "question_id": response.question_id,
                "input_snapshot": snapshot,
            },
        )
        if job.status == "dispatched":
            return job, None
        if job.status == "processing" and _lease_is_active(job):
            return job, None
        if job.status == "completed" and response.evaluated:
            return job, None

        job.status = "waiting_dispatch"
        job.available_at = timezone.now()
        job.lease_owner = ""
        job.lease_expires_at = None
        job.input_snapshot = snapshot
        job.save(
            update_fields=[
                "status",
                "available_at",
                "lease_owner",
                "lease_expires_at",
                "input_snapshot",
                "updated_at",
            ]
        )

        try:
            with transaction.atomic():
                event, _ = EvaluationOutbox.objects.get_or_create(
                    job=job,
                    event_type="dispatch",
                    published_at__isnull=True,
                )
        except IntegrityError:
            event = EvaluationOutbox.objects.get(
                job=job,
                event_type="dispatch",
                published_at__isnull=True,
            )

    return job, event


def dispatch_outbox_event(event_id):
    claim = _claim_outbox_event(event_id)
    if claim is None:
        return {"status": "already_claimed", "mode": "already_queued"}

    event, lock_token = claim
    try:
        response = response_for_job(event.job)
        mode = publish_response_work(response)
    except Exception as exc:
        _record_publish_failure(event.event_id, lock_token, exc)
        return {
            "status": "failed",
            "mode": "waiting_dispatch",
            "error": exc,
        }

    _record_publish_success(event.event_id, lock_token)
    return {"status": "published", "mode": mode}


def dispatch_pending_outbox_events(batch_size=100):
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    event_ids = list(
        EvaluationOutbox.objects.filter(
            published_at__isnull=True,
            job__available_at__lte=timezone.now(),
        )
        .order_by("created_at")
        .values_list("event_id", flat=True)[:batch_size]
    )
    result = {"processed": 0, "published": 0, "failed": 0, "already_claimed": 0}
    for event_id in event_ids:
        outcome = dispatch_outbox_event(event_id)
        result["processed"] += 1
        result[outcome["status"]] += 1
    return result


def response_for_job(job):
    if job.response_type == "user":
        model = UserResponse
    elif job.response_type == "single":
        model = SingleResponse
    else:
        raise ValueError(f"Unsupported evaluation response type: {job.response_type}")
    return model.objects.select_related("question__subsection").get(pk=job.response_id)


def publish_response_work(response):
    from mocktest.tasks import (
        evaluate_single_response,
        evaluate_user_response,
        transcribe_single_task,
        transcribe_task,
    )

    is_single = isinstance(response, SingleResponse)
    needs_transcription = (
        question_requires_audio(response.question)
        and response.answer_audio
        and not has_usable_transcript(response.transcribed_audio_data)
    )
    if needs_transcription:
        transcribe = transcribe_single_task if is_single else transcribe_task
        evaluate = evaluate_single_response if is_single else evaluate_user_response
        chain(
            transcribe.s(response.pk),
            evaluate.si(response.pk, response.question_id),
        ).delay()
        return "transcription_and_evaluation"

    evaluate = evaluate_single_response if is_single else evaluate_user_response
    evaluate.delay(response.pk, response.question_id)
    return "evaluation"


def start_evaluation_attempt(response, stage, task_id=""):
    job = _latest_job(response)
    if job is None:
        return "legacy"

    now = timezone.now()
    lease_seconds = int(getattr(settings, "EVALUATION_JOB_LEASE_SECONDS", 360))
    with transaction.atomic():
        job = EvaluationJob.objects.select_for_update().get(pk=job.pk)
        if response.evaluated and response.evaluation_status == "completed":
            if job.status != "completed" or job.lease_owner or job.lease_expires_at:
                job.status = "completed"
                job.lease_owner = ""
                job.lease_expires_at = None
                job.save(
                    update_fields=[
                        "status",
                        "lease_owner",
                        "lease_expires_at",
                        "updated_at",
                    ]
                )
            return "completed"
        if (
            job.status == "processing"
            and _lease_is_active(job, now=now)
        ):
            return "busy"

        job.current_attempt += 1
        job.status = "processing"
        job.lease_owner = task_id or f"worker-{uuid.uuid4()}"
        job.lease_expires_at = now + timezone.timedelta(seconds=lease_seconds)
        job.save(
            update_fields=[
                "current_attempt",
                "status",
                "lease_owner",
                "lease_expires_at",
                "updated_at",
            ]
        )
        EvaluationAttempt.objects.create(
            job=job,
            attempt_number=job.current_attempt,
            stage=stage,
            task_id=task_id,
            provider="openai" if stage == "evaluation" else "whisper",
            model=(
                settings.OPENAI_EVALUATION_MODEL
                if stage == "evaluation"
                else settings.OPENAI_TRANSCRIPTION_MODEL
            ),
            scoring_version=SCORING_VERSION,
            input_snapshot=job.input_snapshot,
        )
    return "claimed"


def finish_evaluation_attempt(
    response,
    *,
    succeeded,
    result=None,
    error="",
    retryable=False,
    final=True,
):
    job = _latest_job(response)
    if job is None:
        return

    now = timezone.now()
    with transaction.atomic():
        job = EvaluationJob.objects.select_for_update().get(pk=job.pk)
        attempt = job.attempts.filter(finished_at__isnull=True).order_by(
            "-attempt_number"
        ).first()
        if attempt:
            attempt.finished_at = now
            attempt.latency_ms = max(
                0,
                int((now - attempt.started_at).total_seconds() * 1000),
            )
            attempt.retryable = retryable
            if succeeded:
                attempt.normalized_result = result or {}
            else:
                attempt.error_detail = str(error)
                attempt.error_category = "temporary" if retryable else "permanent"
            attempt.save(
                update_fields=[
                    "finished_at",
                    "latency_ms",
                    "retryable",
                    "normalized_result",
                    "error_detail",
                    "error_category",
                ]
            )

        if succeeded:
            job.status = "completed" if final else "dispatched"
        else:
            job.status = "waiting_retry" if retryable else "failed_permanent"
        job.lease_owner = ""
        job.lease_expires_at = None
        job.save(
            update_fields=[
                "status",
                "lease_owner",
                "lease_expires_at",
                "updated_at",
            ]
        )


def _latest_job(response):
    return (
        EvaluationJob.objects.filter(
            response_type=response_type_for(response),
            response_id=response.pk,
        )
        .order_by("-created_at", "-pk")
        .first()
    )


def _claim_outbox_event(event_id):
    now = timezone.now()
    stale_before = now - timezone.timedelta(seconds=OUTBOX_LOCK_SECONDS)
    with transaction.atomic():
        event = (
            EvaluationOutbox.objects.select_for_update()
            .select_related("job")
            .get(event_id=event_id)
        )
        if event.published_at:
            return None
        if event.locked_at and event.locked_at > stale_before:
            return None
        token = uuid.uuid4()
        event.locked_at = now
        event.lock_token = token
        event.publish_attempts += 1
        event.save(update_fields=["locked_at", "lock_token", "publish_attempts"])
        return event, token


def _record_publish_success(event_id, lock_token):
    with transaction.atomic():
        event = EvaluationOutbox.objects.select_for_update().get(event_id=event_id)
        if event.lock_token != lock_token:
            return
        event.published_at = timezone.now()
        event.last_error = ""
        event.locked_at = None
        event.lock_token = None
        event.save(
            update_fields=[
                "published_at",
                "last_error",
                "locked_at",
                "lock_token",
            ]
        )
        EvaluationJob.objects.filter(
            pk=event.job_id,
            status="waiting_dispatch",
        ).update(
            status="dispatched",
            lease_owner="",
            lease_expires_at=None,
        )


def _record_publish_failure(event_id, lock_token, error):
    with transaction.atomic():
        event = EvaluationOutbox.objects.select_for_update().get(event_id=event_id)
        if event.lock_token != lock_token:
            return
        event.last_error = f"{error.__class__.__name__}: {error}"
        event.locked_at = None
        event.lock_token = None
        event.save(update_fields=["last_error", "locked_at", "lock_token"])
        retry_delay = _outbox_retry_delay(event)
        EvaluationJob.objects.filter(pk=event.job_id).update(
            status="waiting_dispatch",
            available_at=timezone.now() + timezone.timedelta(seconds=retry_delay),
            lease_owner="",
            lease_expires_at=None,
        )


def _lease_is_active(job, now=None):
    now = timezone.now() if now is None else now
    return bool(job.lease_expires_at and job.lease_expires_at > now)


def _outbox_retry_delay(event):
    base = int(getattr(settings, "EVALUATION_OUTBOX_RETRY_BASE_SECONDS", 60))
    maximum = int(getattr(settings, "EVALUATION_OUTBOX_RETRY_MAX_SECONDS", 900))
    if base <= 0 or maximum <= 0:
        return 0
    exponent = min(max(event.publish_attempts - 1, 0), 8)
    backoff = min(maximum, base * (2 ** exponent))
    jitter = event.event_id.int % max(1, min(base, 30))
    return min(maximum, backoff + jitter)
