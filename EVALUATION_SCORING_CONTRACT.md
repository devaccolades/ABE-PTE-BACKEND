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
| Free text | Summarize Written Text, Write Essay, Summarize Spoken Text, Highlight Incorrect Words, Write from Dictation |

The effective evaluator is deterministic for objective questions and Write from
Dictation. Highlight Incorrect Words remains AI evaluated without requiring a
stored answer key.

Stored payloads are classified without modifying them:

- `canonical`: valid current structure;
- `legacy_compatible`: safely normalizable historical structure;
- `invalid`: insufficient or ambiguous input that cannot be evaluated safely.

For audio answers, the original response audio is canonical. A non-empty stored
transcript without its audio is recoverable legacy evidence, while a text value
alone is not a substitute for a missing recording. Structural validation also
rejects empty answers, malformed identifiers, duplicate option selections,
ambiguous wrappers, and invalid mappings.

Comma-delimited multiple-choice IDs such as `"1609,1607"` are classified as
legacy-compatible and normalized to `[1609, 1607]`. They are not interpreted as
one option ID. The deterministic evaluator uses the normalized IDs for negative
marking.

This classification is audit-only during Phase 1. It is deliberately not yet
enforced in live submission or retry paths because production contains older
mixed payloads. Question-aware validation of option ownership, blank ownership,
and expected answer counts is the next boundary.

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

## Precision

Calculations use decimal arithmetic. Scores are not rounded during compilation;
rounding belongs only at a final display or export boundary.

## Rollout

The v2 compiler is pure and has no database writes. Its first release is test and
shadow-comparison only. Live `UserResponse` and `SingleResponse` scoring remains
on the current compiler until production score deltas have been reviewed.
