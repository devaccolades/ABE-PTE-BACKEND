# Celery Queue Split Server TODO

These are server-side steps to do after deploying the code that adds separate
Celery queues.

## Queues

The backend now routes tasks to:

```text
transcription
evaluation
default
```

Relevant environment variables:

```bash
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CELERY_TASK_DEFAULT_QUEUE=default
CELERY_EVALUATION_QUEUE=evaluation
CELERY_TRANSCRIPTION_QUEUE=transcription
```

## Initial Worker Plan

Start conservatively while using one OpenAI key:

```bash
celery -A abe_pte worker -Q transcription --concurrency=1 --loglevel=info
celery -A abe_pte worker -Q evaluation --concurrency=2 --loglevel=info
celery -A abe_pte worker -Q default --concurrency=1 --loglevel=info
```

Do not start with high concurrency. The OpenAI key and Whisper calls are the
bottleneck.

## Recommended Systemd Services

Create separate services:

```text
celery-transcription.service
celery-evaluation.service
celery-default.service
```

Each service must load the same `.env` values as Django:

```text
OPENAI_API_KEY
OPENAI_WHISPER_API_KEY
OPENAI_TIMEOUT_SECONDS
OPENAI_MAX_RETRIES
OPENAI_EVALUATION_MODEL
OPENAI_TRANSCRIPTION_MODEL
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
DB_*
```

## Deployment Verification

After starting workers:

```bash
python manage.py check_evaluation_runtime
```

Expected:

```text
workers=...
Worker queues
- ...: evaluation
- ...: transcription
```

Then inspect backlog:

```bash
python manage.py inspect_evaluations
python manage.py inspect_evaluations --status failed --older-than-minutes 60
```

Requeue only small batches:

```bash
python manage.py requeue_pending_evaluations --status failed --older-than-minutes 60 --limit 25 --dry-run
python manage.py requeue_pending_evaluations --status failed --older-than-minutes 60 --limit 25
```

## Rollback

If split workers are unstable, stop queue-specific services and run one combined
worker temporarily:

```bash
celery -A abe_pte worker -Q default,evaluation,transcription --concurrency=2 --loglevel=info
```
