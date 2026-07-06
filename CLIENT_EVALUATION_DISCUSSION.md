# ABE Evaluation System Discussion Notes

## 1. What Was Lacking In The MVP Evaluation Setup

The first version was functional as an MVP, but the evaluation pipeline did not have enough production safety around asynchronous AI work.

Main gaps:

- Evaluation depended heavily on Celery background jobs, but failures were not clearly persisted back to the response records.
- A response could stay as `evaluated=False` indefinitely if transcription, OpenAI evaluation, JSON parsing, scoring, or Celery execution failed.
- There was no clear response-level lifecycle such as `pending`, `transcribing`, `evaluating`, `completed`, or `failed`.
- The admin/dashboard could show that a test was not evaluated, but not always why.
- PDFs could be downloaded even when some answers were still pending or failed, making reports look final when they were not.
- There was no safe batch requeue tool for old stuck evaluations.
- There was no easy health check for Redis, Celery workers, OpenAI keys, or queue readiness.
- Objective question types were using AI in places where deterministic scoring should be enough.
- A single OpenAI key was being used for both transcription and evaluation, which creates rate-limit and timeout risk under load.
- Celery was effectively one general processing path, so slow audio transcription could block other evaluations.
- Duplicate submissions could create duplicate response rows, which could confuse reports and score totals.
- There was limited protection against stale/manual Celery tasks evaluating a response against the wrong question/rubric.

In short: the MVP could evaluate responses, but it did not have enough observability, retry tooling, queue separation, or failure recovery for real production usage.

## 2. What We Are Doing Now

We are turning evaluation from a fragile background process into a trackable, repairable queued workflow.

Work completed in the backend:

- Added durable evaluation status fields:
  - `pending`
  - `transcribing`
  - `evaluating`
  - `completed`
  - `failed`
- Added error/stage/attempt tracking on responses.
- Updated Celery tasks to persist failures instead of silently leaving rows unevaluated.
- Added retry behavior for transient OpenAI/network/timeout issues.
- Added OpenAI timeout/retry/model configuration.
- Added clearer OpenAI error categorization.
- Added validation before applying AI scores, so invalid model output becomes a clear failed state.
- Converted rule-based objective question types away from OpenAI where possible.
- Added admin and command-line requeue tools.
- Added inspection commands to find pending, failed, stale, and duplicate responses.
- Added a one-response diagnostic command for server debugging.
- Added safer score recalculation tools.
- Added duplicate response detection and cleanup tooling.
- Updated PDFs to warn about incomplete or duplicate evaluations.
- Added duplicate-submission protection for full mock tests.
- Added a session evaluation status API so the frontend can poll progress instead of assuming immediate results.
- Added Celery queue routing for separate `evaluation`, `transcription`, and `default` queues.
- Added a runtime health check for OpenAI config, Redis, Celery workers, and queue coverage.

New frontend/API behavior available:

```text
Submit answer -> response saved quickly -> evaluation queued -> frontend polls status -> final PDF only when safe
```

Status endpoint:

```bash
GET /mocktest/session-evaluation-status/?session_id=<session_id>
```

This returns counts like:

```text
total responses
completed
pending
failed
active
duplicate groups
can download final PDF
```

Server-side queue split prepared:

```text
transcription queue
evaluation queue
default queue
```

This allows audio transcription and evaluation to be processed independently instead of blocking each other.

## 3. What Else We Can Do

These are the next improvements to make the system more scalable and production-ready.

### A. Server Deployment And Recovery

On the live server:

- take a fresh DB backup
- deploy the new code
- run migrations
- start separate Celery workers for transcription and evaluation
- run health checks
- inspect old failed/pending responses
- requeue stuck evaluations in small batches
- recalculate completed session scores
- regenerate sample PDFs for verification

Recommended server workers:

```bash
celery -A abe_pte worker -Q transcription --concurrency=1 --loglevel=info
celery -A abe_pte worker -Q evaluation --concurrency=2 --loglevel=info
celery -A abe_pte worker -Q default --concurrency=1 --loglevel=info
```

### B. Add OpenAI Concurrency Throttling

Queue split helps, but it does not fully protect the single OpenAI key.

Next backend improvement:

- limit how many OpenAI evaluation calls can run at the same time
- limit how many Whisper transcription calls can run at the same time
- if the limit is reached, Celery should retry later instead of overwhelming OpenAI

Suggested starting limits:

```text
evaluation OpenAI calls: 2 at a time
transcription OpenAI calls: 1 at a time
```

### C. Monitoring Dashboard

Add an operational dashboard for:

- Celery workers alive/down
- Redis connection
- pending queue length
- failed evaluations
- average evaluation time
- OpenAI timeout/rate-limit counts
- old stuck responses

This can start as admin/management commands and later become a proper dashboard.

### D. Frontend Progress UX

Frontend should show:

```text
Evaluation pending
Evaluation in progress
12 / 20 responses evaluated
2 failed responses
Final PDF available
```

This avoids client confusion when AI evaluation is still processing.

### E. Scale Beyond One Server

If usage grows:

- move Celery workers to a separate server
- keep Redis private and monitored
- increase OpenAI rate limits
- separate transcription and evaluation API keys/projects if needed
- consider multiple worker machines

### F. Load Testing

Before promising large exam batches, run controlled tests:

```text
5 concurrent exams
10 concurrent exams
20 concurrent exams
50 concurrent exams
```

Measure:

- response submission speed
- Celery queue backlog
- average evaluation time
- failed/timeout rate
- OpenAI rate-limit behavior
- PDF readiness time

## 4. Production / Next-Level AI Evaluation Engine

For a bigger application, we should not rely on one OpenAI token/API key as the whole evaluation engine. OpenAI should be one provider inside our own evaluation platform.

Better long-term architecture:

```text
Exam Backend
   |
   v
Evaluation Orchestrator
   |
   |-- rule-based scoring engine
   |-- AI text scoring engine
   |-- transcription engine
   |-- retry/fallback engine
   |-- audit/logging engine
   |
   v
Provider Layer
   |-- OpenAI
   |-- backup provider
   |-- local/rule-based scoring
```

### A. Provider Abstraction

Instead of hardcoding OpenAI calls directly into the business flow, create an internal evaluation interface:

```text
evaluate_answer(task_type, question, answer, rubric)
transcribe_audio(audio_file)
```

Behind that interface, we can use:

- OpenAI
- Azure OpenAI
- another backup provider
- local/rule-based scoring
- future domain-specific models

This keeps the exam app stable even if the provider changes.

### B. Multiple Keys / Projects

For production, use separate credentials for separate workloads:

```text
transcription key/project
evaluation key/project
staging key/project
production key/project
possibly tenant/client-specific keys later
```

Benefits:

- better rate-limit control
- easier billing visibility
- safer key rotation
- failure isolation
- easier debugging

### C. Central Rate Limit And Concurrency Control

Even with split queues, we need a central limit on external AI calls.

Example starting point:

```text
max 2 evaluation calls at once
max 1 transcription call at once
```

If the limit is reached:

```text
do not call OpenAI immediately
retry the Celery task later
keep the user response in processing state
```

This is safer than firing many calls and hitting timeouts/rate limits.

### D. Fallback Strategy

If the primary provider fails:

```text
retry same provider
try backup model/provider if suitable
queue for later if provider is down
mark failed with clear reason if unrecoverable
allow admin requeue
```

For objective questions, fallback should not be AI at all. They should be scored deterministically from the stored answers.

### E. Evaluation Versioning

Every AI evaluation should store:

```text
provider
model
prompt version
rubric version
scoring engine version
timestamp
raw output
normalized output
```

This helps answer client questions like:

```text
Why did this answer get this score?
Which model scored this?
Did scores change after a rubric update?
Can we reproduce this result?
```

### F. Human Review Workflow

For high-stakes or disputed exams, add:

```text
AI scored
flagged for review
human reviewed
adjusted if needed
finalized
```

This is especially useful for speaking and writing tasks.

### G. Cost And Usage Controls

At scale, we should track:

- cost per exam
- cost per section
- daily/monthly OpenAI usage
- per-client usage if multi-tenant
- retry cost
- failed-call cost

Cost controls:

- use AI only for subjective tasks
- use smaller/faster models where acceptable
- cache safe repeat evaluations
- throttle requeues
- alert when usage spikes

### H. Production Observability

A serious evaluation engine needs operational visibility:

- queue depth
- average evaluation duration
- provider timeout count
- provider rate-limit count
- failed evaluations by reason
- cost per day
- stuck sessions
- worker health
- Redis health
- DB query performance

### Production Direction

The long-term goal should be:

```text
ABE Exam App
    submits responses

Evaluation Service
    owns queues, retries, provider selection, scoring versions

Provider Adapters
    OpenAI / backup provider / rule engine

Admin Ops
    inspect, requeue, review, finalize

Reporting
    final only when evaluation is complete and safe
```

The key idea:

```text
OpenAI should be one provider inside our evaluation engine,
not the evaluation engine itself.
```

## Suggested Client Message

The MVP evaluation system worked for basic usage, but it did not have enough production safeguards around asynchronous AI evaluation. We are improving it by making evaluation a trackable queued process with clear statuses, retries, repair tools, duplicate protection, and honest PDF reporting. The next stage is deployment-side scaling: separate Celery workers, OpenAI concurrency limits, monitoring, and load testing before larger exam batches. For a larger product, we should evolve this into a dedicated evaluation engine where OpenAI is one provider behind our orchestration, versioning, retry, fallback, and audit layers.
