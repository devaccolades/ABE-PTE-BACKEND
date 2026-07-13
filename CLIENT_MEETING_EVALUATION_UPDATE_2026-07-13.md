# ABE AI Evaluation - Client Meeting Brief

**Meeting date:** 13 July 2026  
**Main client requirement:** Students should receive test results and detailed feedback as soon as possible after completing a mock test.

## 60-Second Opening

> We took the evaluation concern seriously and completed a major backend reliability upgrade. Every question is now tracked, failures show a clear reason, interrupted evaluations recover automatically, answers remain safe if the queue is unavailable, and administrators can retry either one question or a full test session. We also added duplicate protection and stronger Celery safeguards.
>
> This solves the silent-failure and recovery problems in the MVP. The remaining gap is immediate delivery to students. Evaluation speed still depends on funded AI capacity and concurrent demand, and the current frontend does not yet display completed results directly to students. Today, I would like us to agree on the expected number of simultaneous exams, a realistic result-delivery target, the AI operating budget, and the frontend result experience.

## Executive Summary

The original MVP could submit answers and evaluate them with AI, but it did not have enough safeguards for failures, delayed jobs, provider limits, or simultaneous exams. A failed evaluation could remain unfinished without a clear explanation or a reliable recovery path.

We have now completed and deployed a substantial backend reliability upgrade. Every answer has a visible evaluation status and error reason, failed work can be retried by question or session, interrupted work is automatically recovered, duplicate submissions are blocked, and Celery/Redis health can be checked directly.

This makes the MVP much safer and easier to operate. It does **not** yet guarantee immediate student-facing results. Two limitations remain outside the completed backend work:

1. AI evaluation and voice transcription depend on the available OpenAI account balance, rate limits, and service capacity.
2. Results are currently available in the backend dashboard/PDF; the frontend does not yet deliver completed results and detailed feedback directly to students.

## 1. What The MVP Was Lacking

The initial MVP proved that the evaluation concept worked, but it had production limitations:

- An evaluation could fail and remain unfinished without a clear status or reason.
- Old pending tests were difficult to identify and repair.
- There was no automatic recovery if Celery or the server stopped during evaluation.
- Redis/Celery queue failure during submission could leave misleading pending records.
- OpenAI quota, billing, timeout, and rate-limit problems were difficult to identify from the admin dashboard.
- There was no question-level or full-session retry workflow.
- Duplicate submissions could affect scoring and reporting.
- Voice transcription and AI evaluation shared limited server/provider capacity.
- Reports could be downloaded before every response was safely evaluated.
- There was no agreed result-delivery target or tested concurrent-exam capacity.
- Students could not receive results directly in the frontend.

In short, evaluation worked as an MVP feature, but it was not yet a production evaluation service with guaranteed delivery times.

## 2. What We Have Completed And Deployed

### Evaluation Tracking And Recovery

- Added per-question statuses: pending, transcribing, evaluating, completed, and failed.
- Added the exact failure stage, error description, attempt count, and last-attempt time.
- Added automatic retries for temporary OpenAI, timeout, and connection problems.
- Added automatic recovery every five minutes for work abandoned by a worker/server interruption.
- Added safe storage when Redis/Celery cannot accept a task: the answer remains saved and is marked as retryable instead of being lost.

### Admin Operations

- Added a general OpenAI quota/rate-limit warning in the backend admin.
- Added a retry button for an individual question.
- Added full mock-test session retry for failed or pending answers.
- Added inspection, controlled requeue, duplicate-checking, and score-recalculation commands.
- Added runtime checks for OpenAI configuration, Redis, Celery workers, and queue coverage.

### Data And Scoring Safety

- Added database-level protection against duplicate answers for the same student session and question.
- Added validation of AI scoring output before it can affect final scores.
- Moved objective questions to deterministic scoring where AI is unnecessary.
- Scoped cached evaluations by model and made cache writes safe under concurrent work.
- Added safeguards against evaluating a response with the wrong question or rubric.
- Updated reports to identify incomplete or failed evaluations instead of presenting them as final.

### Celery Reliability

- Created separate logical queues for evaluation, transcription, and general work.
- Added late task acknowledgement so work is confirmed only after completion.
- Added task recovery when a worker process is lost.
- Limited task prefetch so one worker does not reserve excessive exam work.
- Added soft and hard task time limits to stop permanently hung jobs.
- Added Celery Beat for scheduled stale-work recovery.

### Current Live Health

The deployed system currently reports:

- OpenAI evaluation and transcription keys loaded.
- Redis broker and result storage healthy.
- Celery worker online and consuming all required queues.
- Celery Beat recovery running every five minutes.
- Database duplicate protection applied.
- No duplicate response records in the new production database.

## 3. The Limitation We Must State Clearly

The recent work improves reliability and recovery. It cannot guarantee that every student receives results immediately after submission under the current MVP setup.

The current flow is:

```text
Student completes test
        |
Answers are saved immediately
        |
Transcription/evaluation enters a background queue
        |
OpenAI processes subjective answers
        |
Scores and feedback become available in the backend dashboard/PDF
```

Result time therefore depends on:

- how many subjective and voice questions are in the exam;
- how many students finish at the same time;
- current queue length and server worker capacity;
- OpenAI account balance, rate limits, latency, and availability;
- retries caused by invalid output, timeouts, or provider errors.

An OpenAI API key is only a credential. Creating multiple keys under the same account/project does not automatically multiply capacity. The real limits are the account/project billing balance, usage tier, requests-per-minute limits, token limits, and model availability.

The client previously mentioned an initial USD 5 payment with no later billing. OpenAI API usage is usage-based and may use prepaid credit. We need to verify the active balance, billing method, auto-recharge configuration, usage tier, and limits for both evaluation and transcription. When quota is unavailable, the backend can preserve and retry work, but it cannot make the provider evaluate it immediately.

## Suggested Client Wording

> We have completed a significant backend reliability upgrade. Evaluations are now tracked per question, failures show a clear reason, interrupted work is automatically recovered, and we have added both question-level and full-test retry options. This makes the current MVP much safer and prevents answers from being silently lost.
>
> The remaining limitation is delivery speed. AI evaluation depends on the available provider balance and capacity, and results are currently delivered through the backend dashboard rather than directly to the student frontend. Therefore, we cannot responsibly guarantee immediate student results with the present MVP setup. To provide that experience, the next phase needs confirmed AI capacity, performance testing, monitoring, separate processing workers, and frontend result delivery.

## 4. What We Should Do Next

### Immediate Actions

1. Verify OpenAI billing, credit balance, auto-recharge, usage tier, and model limits.
2. Confirm that evaluation and transcription credentials belong to correctly funded projects.
3. Complete honest Celery failure reporting so provider failures appear as failed tasks as well as failed database records.
4. Add queue-depth, failure-rate, evaluation-time, and quota-error monitoring.
5. Run controlled end-to-end tests while the OpenAI balance is active.
6. Measure actual completion time for one exam and for concurrent batches of 2, 5, 10, and 20 exams.

### Student Result Experience

The frontend needs a result workflow that can:

- show evaluation queued/in progress;
- show progress such as 18 of 25 answers completed;
- notify the student when results are ready;
- display scores and detailed feedback;
- show a controlled delay message rather than appearing broken;
- prevent a final report from being presented before evaluation is complete.

This is separate frontend scope. The backend status API required for polling already exists.

### Near-Term Production Improvements

- Run dedicated Celery worker processes for transcription, evaluation, and general work.
- Add central concurrency/rate limiting before calling external AI services.
- Add operational alerts for stopped workers, Redis failure, queue growth, repeated 429 errors, and stale sessions.
- Establish a result-delivery target based on measured load, for example a target number of minutes rather than the word "immediate."
- Add automated end-to-end exam fixtures so evaluation can be tested without manually completing full exams through the frontend.

### Next-Level Evaluation Engine

For a larger application, OpenAI should be one provider inside ABE's evaluation engine, not the entire evaluation engine.

```text
Exam application
      |
Evaluation orchestrator
      |-- deterministic scoring
      |-- transcription service
      |-- subjective AI scoring
      |-- retries and provider selection
      |-- scoring validation and versioning
      |-- audit and human review
      |
Provider layer
      |-- OpenAI
      |-- alternative/backup provider
      |-- future specialized or self-hosted model
```

At that stage we should add:

- provider abstraction and controlled fallback;
- separate production and staging projects;
- model, prompt, rubric, and scoring-version history;
- cost per exam and budget alerts;
- human review for disputed or low-confidence results;
- autoscaling workers and managed Redis;
- service-level monitoring and incident alerts;
- load-tested capacity with an agreed result-delivery target.

Provider fallback must be validated carefully. Different AI models can score the same answer differently, so switching providers silently during one exam could reduce scoring consistency. Fallback should use compatible rubrics, validation, version tracking, and review rules.

## 5. Decisions Needed From The Client

The meeting should conclude with decisions on these points:

1. **Expected volume:** How many students may complete exams at the same time?
2. **Delivery target:** Is the requirement truly immediate, or is a measured target such as 5, 10, or 15 minutes acceptable?
3. **Frontend scope:** Should students see results directly, receive a notification, or continue receiving reports through administrators?
4. **AI budget:** What monthly usage budget and auto-recharge limit should be approved?
5. **Production scope:** Does the client want an MVP reliability improvement or a production evaluation service with monitoring, scaling, fallback, and service targets?
6. **Review policy:** Should failed, disputed, or low-confidence evaluations be reviewed manually?

## Recommended Meeting Outcome

Agree on a staged next phase:

1. Activate and verify provider billing/capacity.
2. Run measured load tests and establish baseline evaluation times.
3. Agree on a realistic result-delivery target.
4. Implement student-facing progress and result delivery.
5. Add monitoring and dedicated workers.
6. Plan provider abstraction and fallback only after scoring consistency is validated.

The key message is straightforward: the backend is now substantially more reliable and recoverable, but guaranteed fast student-facing results require provider capacity, measured infrastructure, monitoring, and frontend delivery as the next phase.

## What We Should Not Promise Yet

- Do not promise instant results for every exam.
- Do not promise a fixed completion time before billing is active and load tests are measured.
- Do not describe additional API keys as guaranteed additional capacity.
- Do not describe backend retry/recovery as frontend result delivery.
- Do not promise a backup AI provider until scoring consistency has been validated.

## Official OpenAI References

- [OpenAI prepaid billing and auto-recharge](https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing)
- [OpenAI API rate-limit guidance](https://help.openai.com/en/articles/6891753-api-rate-limit-advice)
