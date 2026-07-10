# Celery Logs Runbook

This project runs Celery through PM2 on the server.

## Check Celery process

```bash
pm2 list
pm2 show celery
pm2 show celery-beat
```

The Celery process should include these queues:

```bash
-Q default,evaluation,transcription
```

For MVP/single-token setup, prefer concurrency 1:

```bash
--concurrency=1
```

## Watch Celery logs

```bash
pm2 logs celery --lines 100
```

For more history:

```bash
pm2 logs celery --lines 500
```

Press `Ctrl+C` to stop watching logs. This does not stop Celery.

## What good logs look like

When an evaluation is picked up:

```text
Task mocktest.tasks.evaluate_user_response[...] received
Evaluation begins...
```

When OpenAI succeeds:

```text
HTTP Request: POST https://api.openai.com/v1/responses "HTTP/1.1 200 OK"
Task mocktest.tasks.evaluate_user_response[...] succeeded
```

## Common failure: OpenAI quota/rate limit

If the API key is rate-limited, logs show:

```text
HTTP Request: POST https://api.openai.com/v1/responses "HTTP/1.1 429 Too Many Requests"
Retry in 60s: Exception('OpenAI API rate limit exceeded')
```

This means Celery is working, but OpenAI rejected the request. Fix by waiting for the limit window to reset, increasing quota, or using a valid API key/project with available quota.

## Check runtime health

```bash
python manage.py check_evaluation_runtime
```

Healthy output should show:

```text
Redis broker: ok
Redis result backend: ok
Worker queues: default, evaluation, transcription
Evaluation runtime looks healthy.
```

## Inspect evaluation status

All responses:

```bash
python manage.py inspect_evaluations
```

One session:

```bash
python manage.py inspect_evaluations --session-id <session_id>
```

Failed responses:

```bash
python manage.py inspect_evaluations --status failed
```

Stuck evaluating responses:

```bash
python manage.py inspect_evaluations --status evaluating --older-than-minutes 10
```

## Retry evaluations

From admin:

- Open `Mocktest > User mock test sessions`
- Use the `Retry` button on a session row
- Or select sessions and run `Retry failed/pending evaluations for selected sessions`

From command line:

```bash
python manage.py requeue_pending_evaluations --session-id <session_id>
```

## Restart Celery

Use this command when updating the worker command:

```bash
pm2 delete celery
pm2 start /home/ubuntu/venv/bin/python --name celery -- -m celery -A abe_pte worker -l info -Q default,evaluation,transcription --concurrency=1
pm2 save
```

Then verify:

```bash
python manage.py check_evaluation_runtime
```

## Automatic recovery process

Celery Beat must also be online for stale evaluation recovery:

```bash
pm2 start /home/ubuntu/venv/bin/python --name celery-beat -- -m celery -A abe_pte beat -l info
pm2 save
pm2 logs celery-beat --lines 100
```

Run only one `celery-beat` process. It schedules a check every five minutes for
responses stuck in `transcribing` or `evaluating` for at least 20 minutes.
