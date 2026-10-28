# Summary Source Fidelity Review

Implemented locally on 23 October 2026. Production rollout and live-model
verification are separate steps; historical scores have not been changed.

## Why This Exists

Hitha's SingleResponse 289 (BB-SGD 1, Bindu-T2) contains an invented pets story.
Its saved gpt-5-nano assessment awards Content 5/6, while the current question
reference describes mandatory physical education. Correct arithmetic then
produces Listening 7.5/9 and Speaking 4.25/8.5. The Content-zero gate does not
trigger because Content is nonzero. Repetition/template checks do not establish
whether a fluent answer faithfully represents its source.

The original prompt/reference was not retained in the historical job records,
so this change does not claim to prove why that old assessment was produced.

## Scope

| Task | Source Used |
| --- | --- |
| Retell Lecture | Question Correct answer, containing reviewed source material |
| Summarize Group Discussion | Question Correct answer, containing reviewed source material |
| Summarize Spoken Text | Question Correct answer, containing reviewed source material |
| Summarize Written Text | Question text, containing the passage being summarized |

The common orchestrator applies the review to full exams, single-question
practice and the diagnostic evaluation API, including validated grading-cache
hits. It is not limited by the template detector's minimum answer length.

Read Aloud, Repeat Sentence, Describe Image, Respond to a Situation, Essay,
WFD, fixed-answer tasks, MCQ and blanks are not changed by this policy. In
particular, an Essay may legitimately disagree with a suggested position.

## Decision Flow

1. Existing input, strict-Form and prompt-copy checks remain in place. An existing
   integrity zero retains its reason and does not incur another model call.
2. Existing rubric grading, language audits and delivery safeguards remain intact.
3. A separate model request compares only the source and candidate meaning. It
   does not receive the first grader's scores or feedback. It checks topic,
   negation, causal relationships, conclusions and speaker positions.
4. Its JSON assessment must contain candidate/source quotations and a
   comparison reason. Quotes are validated against the actual input strings as
   consecutive words: case, punctuation, apostrophe style and `...` between
   quoted fragments are tolerated, word order and contiguity are not. Pairs that
   cannot be traced to both texts are dropped (kept in `dropped_evidence`) and
   cannot support a decision. The verdict must still be justified by the
   remaining pairs, and any supported claim, traceable or not, blocks a zero.
5. A high-confidence off-topic or contradictory verdict with no supported source
   point triggers a whole-answer zero. Original marks and the reason are retained.
6. A grounded or mixed answer retains normal rubric grading. Missing details,
   synonyms, paraphrases and a partly faithful answer are not automatic zeros.
7. An uncertain or below-threshold verdict, or evidence still unverifiable after
   the repair, never invents a zero. The answer keeps its normal rubric grading
   and `integrity_checks.source_fidelity` records `status=review` with
   `requires_review=true` for staff follow-up. These reviews are not cached, so a
   re-evaluation asks again. Earlier versions failed the evaluation instead,
   which blocked valid answers (and their session PDFs) on a self-reported
   confidence estimate.
8. Provider failures still return `ok=false`, code `source_fidelity_unavailable`,
   and use the existing bounded task retry policy. Missing or oversized input is
   non-retryable until the question bank is corrected.

There is one bounded repair for malformed evidence. Neither input is silently
truncated: both must fit 12,000 characters. A self-reported confidence score is
not a calibrated probability, and exact quotes do not prove semantic correctness.
This remains model-assisted judgment, not a guarantee or a plagiarism detector.

## Evidence and Caching

- Result: `integrity_checks.source_fidelity`, including verdict, quote evidence,
  source/answer hashes, model, audit prompt hash/version and audit cache ID.
- Override: `score_overrides[].code = source_fidelity_failed`, with original marks.
- Applied overrides are logged without including full candidate/source text.
- Audit cache stores the exact source and answer snapshot for later diagnosis;
  the full private snapshot is not added to the returned API result. Evidence
  quotes may appear in the result, like other evaluation feedback.
- Grading and audit cache entries have different prompt hashes. The audit key
  includes task, complete source, complete answer and detector version; model is
  also part of the cache lookup. Quotes, snapshot, version and current confidence
  threshold are checked before reuse. Invalid cached reviews are reviewed again.
- Prompt version is now `pte-evaluation-prompt-v7`; new evaluation attempts and
  successful/policy-result wrappers record it. Old grading cache keys are not
  promoted into the new prompt version. Historical results remain unchanged.

There is normally one extra paid model call per previously unseen summary/source
pair, using `OPENAI_EVALUATION_MODEL`, plus a possible evidence-repair call. Valid
audit cache hits avoid repeating that request. Existing language-audit calls are
unchanged. Allow for additional evaluation latency and monitor task timeouts.

## Configuration

```env
SOURCE_FIDELITY_ENABLED=true
SOURCE_FIDELITY_MIN_CONFIDENCE=0.90
```

Both are reported by `check_evaluation_runtime`. The enabled default protects new
evaluations. Setting enabled to false is an explicit rollback that removes this
extra protection; it does not alter existing results or other integrity checks.

No model/schema changes, new dependencies, migration or frontend build are needed.
Deploy backend changes, run checks/tests, and restart Django/Celery after checking
active/reserved work. No need to restart Beat for this change alone.

```bash
/home/ubuntu/venv/bin/python manage.py check
/home/ubuntu/venv/bin/python manage.py test \
  examinor.test_source_fidelity examinor.test_evaluation_context \
  mocktest.test_evaluation_jobs
```

## Non-Saving Server Verification

The diagnostic command reads the original response and current question source.
It does not reconstruct the historical prompt, retranscribe audio, apply scores,
enqueue tasks, write cache entries or update any response/job/session.

```bash
# Dry run: no model call.
/home/ubuntu/venv/bin/python manage.py check_response_source_fidelity \
  --response-model single --response-id 289

# Explicit paid review, with no response or cache writes.
/home/ubuntu/venv/bin/python manage.py check_response_source_fidelity \
  --response-model single --response-id 289 --evaluate
```

The pets case should return `status=hard_zero` and `is_source_invalid=true`,
with an off-topic assessment explaining the PE/pets mismatch. This diagnostic
tests the independent reviewer only; end-to-end confirmation still needs a
separate approved QA submission and checks of effective awards/finalization.
Also verify a faithful PE summary receives a grounded or mixed verdict before
rolling out broadly. Do not overwrite response 289 merely to obtain a pass.

## Local Verification Limits

Automated tests mock provider responses. They verify enforcement, quote validation,
cache isolation, positive/mixed cases, contradictory SWT, both response models,
all scoring modes, preservation of strict Form zeros and the non-saving command.
They do not establish the real model's semantic accuracy on every trainer case.
Production PostgreSQL, live-model behavior and remaining trainer concerns need
their own verification. No claim is made that all 45 reported scenarios are fixed.

Verification run: 214 tests passed (`examinor` plus `mocktest.test_evaluation_jobs`),
including 21 new source-fidelity tests, with mocked providers and isolated SQLite.
The full modified suite ran 424 tests with one failure, ten errors and one skip.
The same eleven failing test names reproduced on untouched HEAD (403 tests) in
the same environment: existing paper-edit-lock fixtures, an Essay fixture missing
Form, a runtime-health fixture and the migration-inventory test affected by the
isolated settings. These unrelated failures were not silently fixed or ignored.
