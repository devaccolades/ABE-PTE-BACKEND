# Evaluation Scoring Contract

## Version

`pte-score-v2`

This contract defines how already validated rubric criterion scores are converted
into fixed question-level PTE skill scores. It does not change question rubrics,
answer keys, question maxima, or stored historical results.

## Formula

For each skill independently:

```text
criterion ratio = sum(mapped criterion scores) / sum(mapped criterion maxima)
skill award = criterion ratio * configured question skill maximum
```

A criterion mapped to multiple skills contributes independently to each skill.
For example, a full-score criterion mapped to both reading and listening awards
the configured maximum for both skills.

### Client 6452 Golden Evidence

The seven scoring defects in `Evaluation feedback 6452.docx` are permanent
regression cases in `examinor.test_score_calculator`:

| Reported task | Validated evidence | Expected award |
|---|---:|---:|
| Repeat Sentence 4 | content 2/3, fluency 4/5, pronunciation 5/5 | Listening 1.00, Speaking 1.26; total 2.26/2.90 |
| Reading FIB Dropdown | 5/5 blanks | Reading 5/5 |
| Reorder Paragraphs | 3/3 adjacent pairs | Reading 3/3 |
| Reading FIB Drag and Drop | 4/5 blanks | Reading 4/5 |
| Listening FIB | 4/4 blanks | Listening 4/4 |
| Highlight Incorrect Words | full accuracy | Reading 5.5, Listening 4; total 9.5/9.5 |
| Write from Dictation | full accuracy | Writing 7, Listening 1; total 8/8 |

The assertions cover per-skill awards, combined awarded score, combined maximum,
and scoring version. They specifically prevent the old behavior that reduced a
raw task result such as 5/5 or 4/5 to a fractional score capped at one.

## Validation

Compilation must fail rather than silently repair or cap evidence when:

- a criterion score or maximum is missing or non-numeric;
- a score or maximum is infinite or NaN;
- a score is negative or exceeds its criterion maximum;
- a criterion maximum is zero or negative;
- a criterion has no valid skill mapping;
- a mapped skill has no positive question maximum;
- a positive question maximum has no mapped criterion;
- a mapping or gate policy references an unknown criterion or skill.

## Gate Policy

There is no global `content=0` or `form=0` rule in the compiler. A zero-score gate
is applied only when the task's reviewed policy explicitly supplies that
criterion as a gate. This prevents one task's rubric behavior from silently
changing another task.

The task registry currently defines these gates:

| Gate | Subsections |
|---|---|
| `content` | Read Aloud, Repeat Sentence, Describe Image, Retell Lecture, Summarise Group Discussion, Respond to a Situation |
| `content`, `form` | Summarize Written Text, Write Essay, Summarize Spoken Text |
| none | Answer Short Question and every rule-scored objective task |

These policies preserve the task-specific zero-score rules instead of inferring
them merely because a model happened to return a field named `content` or
`form`. They were reviewed against the current [Pearson PTE Academic Test Taker
Score Guide](https://www.pearsonpte.com/content/dam/ELL/pte/pearsonpte/resources/PTE-Academic-Test-Taker-Score-Guide.pdf)
on 2026-08-04.

## Task And Answer Contracts

`examinor.scoring.task_contracts.TASK_CONTRACTS` is the source of truth for the
effective evaluator, answer shape, and gate policy of all 22 supported
subsections.

| Answer contract | Subsections |
|---|---|
| Response audio | Read Aloud, Repeat Sentence, Describe Image, Retell Lecture, Answer Short Question, Summarise Group Discussion, Respond to a Situation |
| Blank mapping | Reading FIB Dropdown, Reading FIB Drag and Drop |
| Ordered mapping | Reorder Paragraphs |
| Single option ID | Reading MCQ Single, Listening MCQ Single, Highlight Correct Summary, Select Missing Word |
| Multiple option IDs | Reading MCQ Multiple, Listening MCQ Multiple |
| Delimited text | Listening Fill in the Blanks |
| Highlighted words | Highlight Incorrect Words |
| Free text | Summarize Written Text, Write Essay, Summarize Spoken Text, Write from Dictation |

The effective evaluator is deterministic for objective questions and Write from
Dictation. Highlight Incorrect Words is also deterministic: `Question.correct_answer`
contains the reviewed source-audio transcript, and the evaluator aligns it with
the displayed passage to derive incorrect displayed-word positions. Current
submissions contain zero-based word positions and exact words; historical
comma-delimited word selections remain compatible. A correct highlight earns
one point, a wrong highlight removes one point, and the result cannot fall below
zero.

A displayed word that is absent from the audio remains selectable and is scored
as incorrect. Audio-only words are not selectable, so report application blocks
them until a reviewer normalizes the scoring transcript to the displayed token
boundary.

HIW transcript preparation is a reviewed two-phase operation. The
`prepare_highlight_incorrect_word_keys` command generates a read-only JSON report;
only entries explicitly marked `approved` can be applied with count guards.
`reevaluate_highlight_incorrect_word_responses` similarly runs as a dry run until
explicitly confirmed and never calls an AI evaluation provider.

Stored payloads are classified without modifying them:

- `canonical`: valid current structure;
- `legacy_compatible`: safely normalizable historical structure;
- `unanswered`: an explicitly empty non-audio response that is complete and
  receives zero;
- `invalid`: insufficient or ambiguous input that cannot be evaluated safely.

For audio answers, the original response audio is canonical. A non-empty stored
transcript without its audio is recoverable legacy evidence, while a text value
alone is not a substitute for a missing recording. Structural validation also
rejects malformed identifiers, duplicate option selections, ambiguous wrappers,
and invalid mappings. Missing response audio remains invalid rather than
unanswered because a failed upload cannot be distinguished safely from a
candidate skip after submission.

Empty non-audio responses now bypass both AI and deterministic evaluators. The
Celery task creates a validated system result with every rubric criterion set to
zero, marks the response completed, and includes `answer_status=unanswered` and
`evaluation_source=system`. This avoids provider spend and prevents legitimate
skips from blocking session completion.

### Missing Response Audio

The task registry is the source of truth for whether candidate response audio is
required. Editable `SubSection.ai_input_type` values cannot weaken or change that
contract. Question APIs expose the effective contract so the frontend records
audio for every speaking task even when a database setting is stale.

Missing original response audio with no stored transcript is a permanent input
failure, not a retryable provider failure. It is stored with:

- `code=response_audio_missing`;
- `retryable=false`;
- a message requiring replacement audio.

Celery, admin bulk actions, per-response controls, and management commands do not
futilely requeue these rows. The original session response can instead be
resubmitted with `answer_audio` through the existing user-response endpoint. The
backend locks and repairs that row, clears stale scores and evaluation output,
preserves the unique session/question identity, and then queues transcription.
The response returns HTTP 200 with `recovered_submission=true`.

No score is fabricated for missing audio. The session remains incomplete and
the final PDF remains unavailable until replacement evidence is evaluated.

Comma-delimited multiple-choice IDs such as `"1609,1607"` are classified as
legacy-compatible and normalized to `[1609, 1607]`. They are not interpreted as
one option ID. The deterministic evaluator uses the normalized IDs for negative
marking.

Canonical and legacy-compatible classification remains audit-only during Phase
1. The live task path uses only the explicit `unanswered` state for its
deterministic zero-score short circuit. Question-aware validation of option
ownership, blank ownership, and expected answer counts is the next boundary.

The privacy-safe production audit command is:

```bash
python manage.py audit_answer_payloads \
  --output /home/ubuntu/abe-phase0/answer-payload-audit.csv
```

It exports model and object IDs, subsection, classification, issue codes, media
presence, and evaluation status. It never exports candidate answer content.

## Targeted Legacy Repair

The production audit on 2026-08-04 found 18 Listening MCQ Multiple responses
stored as comma-delimited IDs. All selected IDs were verified to belong to their
questions. The old parser awarded zero because it treated the whole string as a
single integer. Twelve responses have a corrected non-zero score; six remain
zero after proper negative marking.

The repair command is dry-run by default:

```bash
python manage.py repair_delimited_multiple_choice_responses \
  --model user \
  --subsection l_mc_multiple
```

The confirmed form requires the exact eligible count observed during the dry
run:

```bash
python manage.py repair_delimited_multiple_choice_responses \
  --model user \
  --subsection l_mc_multiple \
  --confirm \
  --expected-count 18
```

Before writing, it revalidates payload shape and option ownership under a
transaction. It then stores canonical option-ID lists, recomputes only those
deterministic evaluations, and recalculates only affected sessions. It never
calls an AI provider.

### JSON-Encoded Rule Answers

The production audit on 2026-08-05 found another 42 deterministic answers stored
as JSON strings rather than JSON objects or arrays:

- 15 Reading FIB Dropdown responses;
- 12 Reading FIB Drag and Drop responses;
- 9 Reorder Paragraphs responses;
- 6 Reading MCQ Multiple responses.

All 42 normalized answers passed question, blank, and option-ownership checks.
The old parser evaluated them as empty and stored zero. Correct parsing changes
37 scores; five legitimately remain zero.

The evaluator now normalizes JSON-encoded mapping payloads before deterministic
scoring. Historical rows can be inspected without writes using:

```bash
python manage.py repair_json_encoded_rule_responses --model user
```

The confirmed command is guarded by the exact dry-run count:

```bash
python manage.py repair_json_encoded_rule_responses \
  --model user \
  --confirm \
  --expected-count 42
```

The command rejects unknown blank references, options assigned to the wrong
dropdown blank, and option IDs outside the question. A confirmed repair runs in
one transaction, stores canonical answers, recomputes only deterministic
results, and recalculates only affected sessions.

## Mock-Test Publication Gate

New mock tests are drafts by default. Changing `is_active` from false to true
requires the complete mock test to pass the same centralized question-bank
contract used by the audit command. The gate checks section structure, question
ownership, prompts, required media and storage availability, deterministic
answer keys, rubric traits, global pronunciation/fluency rubrics, trait-to-skill
maps, and question skill maxima.

The Django admin reports actionable question-level errors and refuses the
activation. `MockTest.save()` enforces the same transition check so ordinary
application code cannot bypass the admin gate. Existing active tests are not
automatically disabled during rollout; they can be audited together with:

```bash
python manage.py check_mock_test_publication --active
```

One draft can be checked by UUID or exact title. Media field requirements can be
audited without accessing storage by adding `--skip-media-check`.

## Precision

Calculations use decimal arithmetic. Scores are not rounded during compilation;
rounding belongs only at a final display or export boundary.

## Rollout

The v2 compiler is pure. Both `UserResponse` and `SingleResponse` call one shared
response-scoring service controlled by `EVALUATION_SCORING_MODE`:

- `legacy`: calculate and promote only `pte-score-v1`;
- `shadow` (default): promote the legacy score while storing the v2 result,
  per-skill delta, or v2 contract error inside `evaluation_result`;
- `v2`: fail closed on a v2 contract error and promote `pte-score-v2`.

Shadow calculation makes no provider calls and does not alter the live awarded
score. The persisted evidence identifies both versions and the promoted version.
Operations can produce a historical comparison without modifying responses or
sessions:

```bash
python manage.py report_scoring_v2_deltas \
  --output /home/ubuntu/abe-phase0/scoring-v2-deltas.csv
```

The report supports model, response, session, mock-test, and subsection filters.
It contains IDs, score values, deltas, and compile errors, but no candidate answer
content. Production remains in shadow mode until the delta report and unexplained
contract errors have been reviewed.

Each mock test has a rollout mode and defaults to `shadow`. Enabling V2 for a
mock test requires that it is active and passes the complete publication
contract. Inactive tests cannot start through the public API. A newly started
full mock-test session inherits its mock test's mode and pins it for the
session's lifetime.

Every initial evaluation, retry, repair, and confirmed question-maximum
correction for a `UserResponse` uses the session pin rather than the current
process environment. Operations may therefore canary V2 on one validated mock
test without changing other new exams, partially completed exams, or historical
sessions. Existing mock tests and sessions are backfilled as `shadow` during
rollout. Standalone `SingleResponse` evaluations continue to use the current
environment mode.

Session-level impact can be reviewed without writes:

```bash
python manage.py report_scoring_v2_session_deltas \
  --output /home/ubuntu/abe-phase0/scoring-v2-session-deltas.csv
```

Incomplete sessions and sessions with V2 compile errors are not projected as
final results. The report also detects stale session aggregates and stored
response-versus-legacy mismatches.

## Question Skill Maximum Policy

Question skill maxima are no longer inferred from the sum of subsection rubric
bands. Rubric points describe criterion evidence; question maxima describe the
task's weighted contribution to each PTE skill within a particular exam version,
and the two values are not interchangeable.

Golden examples and objective-task raw point counts are audit references, not
universal maxima. Production evidence shows legitimate weights vary with exam
composition. A Repeat Sentence reference of speaking `1.4` and listening `1.5`,
for example, must not overwrite another reviewed exam version using `1.2` and
`1.25`.

Tasks without a reference are reported as `review_required`. Differences from a
reference are warnings requiring rubric-owner review. The Django admin and repair
commands never autofill or rewrite a question maximum from these references.

The publication validator enforces only universal maximum invariants: each
mapped skill requires a positive maximum, values must be finite and non-negative,
and a positive maximum cannot award a skill with no mapped rubric trait.

The read-only production audit is:

```bash
python manage.py audit_question_skill_maxima \
  --active \
  --output /home/ubuntu/abe-phase0/active-question-skill-maxima.csv
```

The CSV distinguishes reference matches, reference differences, and tasks
requiring policy approval. It never changes questions, responses, or session
scores. It also flags values at least three times above or below the median of
three or more same-exam, same-task, same-skill peers. Peer outliers are warnings,
not automatic corrections. Reference differences must be resolved against the
versioned exam weighting policy before v2 scoring is enabled.

### Confirmed Maximum Corrections

A confirmed one-question weighting defect is corrected with
`correct_question_skill_maximum`. The command is dry-run by default and requires
the current value. Its confirmed form additionally requires a reason and exact
evaluated `UserResponse` and `SingleResponse` counts observed in the dry run.

The write runs in one database transaction. It locks the question and affected
responses, changes only one skill maximum, recompiles stored criterion evidence
without calling an AI provider, recalculates affected sessions, and appends a
before/after record to `evaluation_result.score_corrections`. A changed current
maximum or response count aborts the operation without writes.
