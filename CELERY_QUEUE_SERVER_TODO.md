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
EVALUATION_STALE_AFTER_MINUTES=20
EVALUATION_RECOVERY_BATCH_SIZE=100
EVALUATION_RECOVERY_INTERVAL_SECONDS=300
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

## Automatic stale evaluation recovery

Celery Beat schedules recovery checks for responses left in `transcribing` or
`evaluating` after a worker interruption. Run exactly one Beat process:

```bash
pm2 start /home/ubuntu/venv/bin/python --name celery-beat -- -m celery -A abe_pte beat -l info
pm2 save
```

Verify it is running:

```bash
pm2 show celery-beat
pm2 logs celery-beat --lines 100
```

The default recovery check runs every 5 minutes and only requeues active work
whose last attempt is at least 20 minutes old. Keep only one Beat instance to
avoid duplicate periodic jobs.
