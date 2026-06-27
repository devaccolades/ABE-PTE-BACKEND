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

