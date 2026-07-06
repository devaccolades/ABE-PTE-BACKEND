# ABE Backend Evaluation Inspection

## Context

The current ABE backend evaluates PTE responses through asynchronous Celery jobs. API endpoints create a `UserResponse` immediately, then Celery later handles optional audio transcription and OpenAI-based evaluation. The admin dashboard and PDF reports read whatever score data has been persisted back to the database.

The client-reported issue is that some tests submitted months ago are still not evaluated, so downloaded PDF reports can show missing or incomplete results.

## Current Evaluation Flow

1. A user submits a response through the API.
2. The backend creates a `UserResponse` row with `evaluated=False`.
3. If audio exists, Celery runs transcription first.    
4. Celery then runs evaluation.
5. Evaluation result is saved to `evaluation_result`.
6. `apply_skill_scores()` maps rubric scores into speaking/writing/reading/listening scores.
7. `evaluated=True` is set only if score application succeeds.
8. Session totals are recalculated from responses where `evaluated=True`.
9. PDF reports read saved scores from the database.

## Likely Root Cause

This is mainly an async reliability and observability issue.

If Celery fails during transcription, OpenAI evaluation, JSON parsing, rubric mapping, or score application, the response can remain `evaluated=False` indefinitely. Several failure paths return error dictionaries to Celery but do not persist the failure state onto the `UserResponse`. That means the admin dashboard may only show “not evaluated,” without explaining why.

For audio responses, the risk is higher because Celery uses a chain:

```text
transcribe_task -> evaluate_user_response
```

If transcription fails, evaluation never runs.

## OpenAI/API Key Limitation

The MVP appears to depend on a single OpenAI API key/token for evaluation and transcription. This creates several operational risks:

- If that key hits rate limits, evaluations may fail or delay.
- If the OpenAI API times out, Celery may leave responses pending.
- If the key is revoked, expired, misconfigured, or missing in the Celery worker environment, all evaluations can stop.
- If many users submit tests at the same time, requests may queue up behind one external API bottleneck.
- A single key makes it harder to separate transcription traffic from evaluation traffic.
- There is no visible circuit breaker or fallback behavior when OpenAI is unavailable.

At MVP scale this may be acceptable, but it is fragile once real users submit many tests.

## MVP Limitations

The current project is functional as an MVP, but it has important limits:

- Celery job failures are not clearly stored in the database.
- There is no response-level evaluation status such as `pending`, `transcribing`, `evaluating`, `failed`, or `completed`.
- There is no admin retry/requeue option for stuck responses.
- There is no batch recovery command for old unevaluated responses.
- OpenAI responses are parsed manually and are not fully schema-validated.
- Rule-based tasks still rely on OpenAI, even when correct answers already exist in the database.
- Audio analysis uses simplified heuristics and should not be considered production-grade pronunciation scoring.
- Session totals only include responses marked `evaluated=True`.
- PDFs can be generated even when responses are pending or failed, which can make reports look complete when they are not.
- Missing migrations were detected for `SingleResponse` and related model changes.
- Celery broker/result backend is configured as local Redis, with no visible deployment/process supervision in the repo.
- There is no clear monitoring for queue length, failed tasks, retries, or OpenAI latency.

## What Can Be Improved At This Stage

### 1. Add Durable Evaluation Status

Add fields to `UserResponse` and `SingleResponse`:

```text
evaluation_status: pending/transcribing/evaluating/completed/failed
evaluation_stage: transcription/evaluation/scoring
evaluation_error: last error message
evaluation_attempts: retry count
last_evaluation_attempt_at
```

This makes dashboard inspection much easier.

### 2. Persist Celery Failures

Whenever transcription or evaluation fails, save the error to the response row. Avoid returning error dictionaries only to Celery, because those are not visible in the dashboard/PDF flow.

### 3. Add Retry and Requeue Tools

Add:

- Admin action: requeue selected unevaluated/failed responses.
- Management command: requeue old pending responses in batches.
- Celery retry policy for temporary OpenAI/network/timeout failures.

This directly addresses old client tests that are stuck.

### 4. Validate OpenAI Output Before Scoring

Before calling `apply_skill_scores()`, validate:

- `ok=True`
- `evaluation.scores` exists
- rubric keys match expected criteria
- scores are numeric
- each score is within `0..max`

Invalid model output should become a clear failed state, not an invisible pending state.

### 5. Separate Rule-Based Scoring From AI Scoring

For MCQ, fill-in-the-blanks, reorder paragraphs, and similar tasks, scoring should be deterministic Python logic using stored correct answers. OpenAI should be reserved for subjective scoring such as essays, summaries, and speaking content.

This will reduce cost, latency, timeout risk, and scoring inconsistency.

### 6. Add OpenAI Timeout/Backoff Settings

Use explicit timeouts and retry/backoff behavior around OpenAI calls. Track timeout errors separately from invalid model responses.

Recommended categories:

- API timeout
- rate limit
- authentication/configuration error
- invalid JSON/model output
- scoring validation failure

### 7. Add Queue Monitoring

At minimum, monitor:

- Celery worker running status
- Redis availability
- pending queue length
- failed task count
- average evaluation time
- OpenAI timeout/rate-limit count

### 8. Make PDFs Honest About Pending Work

PDF reports should show whether a session has pending or failed responses. If not all responses are evaluated, the report should say so clearly instead of silently showing zero or missing scores.

### 9. Fix Migrations

Generate and apply the missing migration for `SingleResponse` and related model changes before deploying further changes.

## Suggested Implementation Order

1. Add evaluation status/error fields and migration.
2. Update Celery tasks to persist failure states.
3. Add admin/dashboard visibility for pending and failed responses.
4. Add requeue admin action and management command.
5. Add OpenAI output validation.
6. Convert deterministic rule-based tasks away from OpenAI.
7. Add queue/OpenAI monitoring.
8. Update PDF reports to show incomplete evaluation state.

## Corrections Implemented In Code

The first reliability pass has now been implemented in the backend codebase:

- Added durable evaluation fields to `UserResponse` and `SingleResponse`: status, stage, last error, attempt count, and last attempt timestamp.
- Added migrations for those fields, including a backfill that marks already evaluated responses as completed and known errored responses as failed.
- Added a follow-up migration to backfill existing `SingleResponse` evaluation statuses, so old evaluated single tests are not mislabeled as pending.
- Optimized evaluation-status backfill migrations to use bulk updates for completed/pending rows, reducing migration runtime on production-sized response tables.
- Updated Celery transcription/evaluation tasks to mark progress, persist failures, and retry transient OpenAI/network/timeout errors.
- Added OpenAI timeout and retry settings via `OPENAI_TIMEOUT_SECONDS` and `OPENAI_MAX_RETRIES`.
- Added configurable OpenAI model settings via `OPENAI_EVALUATION_MODEL` and `OPENAI_TRANSCRIPTION_MODEL`.
- Added OpenAI error categorization so auth, rate-limit, timeout, connection, and status-code failures are easier to diagnose.
- Made the OpenAI evaluation client lazy so Django/Celery can boot even when the key is missing, and evaluation failures are persisted as structured response errors.
- Added explicit missing-key handling for Whisper transcription before opening/processing the audio file.
- Updated Celery evaluation to use the exact `SubSection` linked to the question instead of looking up subsections globally by name.
- Kept name-based evaluation for direct examinor API usage, but it now returns a clear duplicate-subsection error instead of raising an ORM exception.
- Normalized text `answer_data` before prompt construction so payloads like `{"text": "..."}` are evaluated as the candidate answer, not as raw Python dict text.
- Added stable JSON fallback for structured non-text answers so prompt hashes remain deterministic.
- Made Celery evaluation validate the queued `question_id` against the response's linked question before scoring, preventing wrong-rubric evaluation from stale/manual task calls.
- Scoped evaluation cache entries by `OPENAI_EVALUATION_MODEL` so model upgrades do not reuse cached scores from an older evaluator model.
- Made evaluation cache writes concurrency-safe so parallel Celery workers do not fail a successful evaluation when another worker creates the same cache row first.
- Made Celery broker/result backend URLs environment-configurable with `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`.
- Added Celery task routing for split `evaluation`, `transcription`, and `default` queues.
- Extended runtime checks to report worker queue coverage and fail when expected evaluation/transcription queues are not consumed.
- Added `CELERY_QUEUE_SERVER_TODO.md` with the server-side worker/systemd rollout checklist.
- Added `check_evaluation_runtime` to verify OpenAI settings, Redis connectivity, and Celery worker responses before requeueing old evaluations.
- Removed the settings import crash for missing Whisper key so diagnostic commands can still run and report configuration problems cleanly.
- Added strict score validation before applying skill scores, so bad model output becomes a clear failed evaluation instead of silently corrupting totals.
- Converted objective/rule-based question types away from OpenAI scoring where stored correct answers are enough.
- Added admin visibility and requeue actions for stuck or failed evaluations.
- Added management commands to inspect evaluation health, requeue pending evaluations, evaluate one response synchronously, and recalculate session totals.
- Added `/mocktest/session-evaluation-status/?session_id=...` so the frontend can poll queued/evaluating/completed/failed progress instead of assuming results are immediate.
- Updated response submission APIs to explicitly return evaluation queued metadata.
- Improved session score recalculation output to show total/evaluated/pending/failed response counts, and added `--only-complete` for recalculating only fully evaluated sessions.
- Made session score recalculation duplicate-aware by reporting duplicate response groups and adding `--skip-duplicates`.
- Improved `evaluate_response_now` diagnostics to print current response state and added `--force-transcription` for rerunning audio transcription on a single response.
- Added `inspect_duplicate_responses` to find historical duplicate full mock-test response rows before score recalculation, including a conservative recommended keep id.
- Added `cleanup_duplicate_responses`, a dry-run-first duplicate cleanup command that deletes only with explicit `--confirm-delete` and can recalculate affected sessions with `--recalculate`.
- Wrapped confirmed duplicate cleanup and optional recalculation in a database transaction, with validation for unsafe limits.
- Extended requeue support to both full mock-test responses and single-response rows.
- Extended evaluation inspection to support single-response rows with `inspect_evaluations --single`.
- Added `--status` and `--older-than-minutes` filters to inspection and requeue commands so old failed/stuck responses can be targeted safely.
- Added response indexes for evaluation repair queries: status/submitted time, status/last-attempt time, mock-test/submitted time, and session/submitted time.
- Persisted task failures for missing or misconfigured questions instead of returning invisible Celery error payloads.
- Changed session `total_score` storage to a float so recalculated PDF/dashboard totals do not lose decimals.
- Updated PDF reports to clearly warn when a session is not fully evaluated and to show failed/pending response details.
- Updated PDF reports to warn when historical duplicate response rows exist and to mark duplicate answer rows individually.
- Fixed response submission lookup so mock-test answers are scoped to the session's mock test instead of using global question names.
- Added `question_id` submission support to avoid duplicate-name ambiguity.
- Added defensive request validation for missing or invalid question identifiers.
- Added duplicate-submission protection for full mock-test responses so a frontend retry cannot create multiple answers for the same session/question and double-count scores.

Current automated verification:

```text
OPENAI_API_KEY=dummy OPENAI_WHISPER_API_KEY=dummy ./venv/bin/python manage.py test
Ran 53 tests: OK

OPENAI_API_KEY=dummy OPENAI_WHISPER_API_KEY=dummy ./venv/bin/python manage.py makemigrations --check --dry-run
No changes detected

OPENAI_API_KEY=dummy OPENAI_WHISPER_API_KEY=dummy ./venv/bin/python manage.py check_evaluation_runtime --skip-redis --skip-celery
Evaluation runtime looks healthy.
```

## Remaining Server-Side Deployment Work

Before applying this on the live server:

1. Take a fresh database backup.
2. Deploy code and run migrations.
3. Confirm Celery workers have the same environment variables as Django, especially OpenAI keys and timeout settings.
4. Run `inspect_evaluations` to measure the existing backlog.
5. Requeue old pending/failed responses in controlled batches.
6. Regenerate/download a few affected PDFs and verify they now show either completed scores or an honest incomplete/failed status.

Useful commands:

```bash
python manage.py inspect_evaluations
python manage.py inspect_evaluations --single
python manage.py inspect_duplicate_responses
python manage.py cleanup_duplicate_responses
python manage.py check_evaluation_runtime
python manage.py inspect_evaluations --status failed --older-than-minutes 60
python manage.py inspect_evaluations --status evaluating --older-than-minutes 60
python manage.py requeue_pending_evaluations --dry-run
python manage.py requeue_pending_evaluations --status failed --older-than-minutes 60 --dry-run
python manage.py requeue_pending_evaluations --status evaluating --older-than-minutes 60 --dry-run
python manage.py requeue_pending_evaluations --limit 50
python manage.py requeue_pending_evaluations --single --dry-run
python manage.py recalculate_session_scores --dry-run
python manage.py recalculate_session_scores --only-complete --dry-run
python manage.py recalculate_session_scores --skip-duplicates --dry-run
python manage.py evaluate_response_now <response_id> --dry-run
python manage.py evaluate_response_now <response_id> --force-transcription
```

Recommended live-server pattern:

```bash
python manage.py check_evaluation_runtime
python manage.py inspect_evaluations --status failed --older-than-minutes 60
python manage.py inspect_duplicate_responses
python manage.py cleanup_duplicate_responses
python manage.py requeue_pending_evaluations --status failed --older-than-minutes 60 --limit 25 --dry-run
python manage.py requeue_pending_evaluations --status failed --older-than-minutes 60 --limit 25
```

Use the same pattern for `evaluating` or `transcribing` only when the rows are clearly stale and Celery is confirmed healthy.

## Immediate Production Triage Queries

Run these checks on the production database:

```python
from mocktest.models import UserResponse, UserMockTestSession

UserResponse.objects.filter(evaluated=False).count()

UserResponse.objects.filter(
    evaluated=False,
    answer_audio__isnull=False,
    transcribed_audio_data__isnull=True,
).count()

UserMockTestSession.objects.filter(
    userresponse__evaluated=False,
).distinct().count()

UserResponse.objects.filter(
    evaluated=False,
).values(
    "question__subsection__name",
).order_by(
    "question__subsection__name",
)
```

These will confirm whether the production backlog is mostly audio transcription failures, OpenAI evaluation failures, or score-application failures.