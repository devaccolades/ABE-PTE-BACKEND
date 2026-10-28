# Template Answer Detection and Scoring

Updated: 20 October 2026

The separate [company strict Form policy](STRICT_FORM_POLICY.md) can zero an
answer before any AI template assessment when it misses the full-credit word
range. It also rejects less-than-full assessed Form credit after evaluation.

## Plain-English Summary

A template answer is a reusable script that takes the place of actually
answering the question. It might sound fluent, contain correct grammar and
mention the topic, but communicate little about the particular task.

The system checks three different things:

1. Is the answer dominated by repeated phrases or sentence patterns?
2. Does it closely match a trainer-reviewed template in our library?
3. Even if the script is unfamiliar or paraphrased, does generic wording
   substitute for meaningful, question-specific content?

A familiar introduction, conclusion, polite request or linking phrase is NOT
enough to make an answer invalid. Organized answers with real observations,
relevant reasoning or an appropriate response to the situation are allowed.

Strong, sufficiently evidenced cases receive zero for the whole answer, not
just Content. Uncertain semantic cases are flagged internally and retain normal
rubric scoring. A review flag is stored evidence, not a new human-review queue
or an automatic pause in result publication.

## Basis in PTE Guidance

Pearson's Score Guide identifies answers that do not properly address the prompt
because substantial pre-prepared/memorized material substitutes for a response.
Its Describe Image example shows Content zero leading to no further scoring.
See [Pearson's Academic Score Guide, page 8](https://www.pearsonpte.com/content/dam/ELL/pte/pearsonpte/resources/PTE-Academic-Test-Taker-Score-Guide.pdf#page=8).

Pearson also warns against substantial memorized scripts for Retell Lecture,
while recommending coherent, connected explanations of actual lecture ideas.
See [Pearson's Retell Lecture guidance](https://www.pearsonpte.com/articles/answering-retell-lecture-effectively-in-pte-academic/).

Pearson's [Group Discussion guidance](https://www.pearsonpte.com/articles/summarize-group-discussion-task-for-pte/)
asks for an original account of the speakers' contributions, but also recommends
ordinary connecting and speaker-attribution phrases. Structure is not the same
as a memorized generic answer.

Our percentages, word counts and confidence cutoffs below are application
policies. They are NOT published Pearson detection thresholds or a reproduction
of Pearson's proprietary scoring technology.

## Which Questions Are Covered?

| Question Type | Template/Repetition Checks | Required Question Grounding |
| --- | --- | --- |
| Describe Image | Yes | Actual question image |
| Retell Lecture | Yes | Reviewed lecture transcript/key points |
| Summarise Group Discussion | Yes | Reviewed discussion transcript/key points |
| Respond to a Situation | Yes | Situation, intended audience and communication goal |
| Write Essay | Yes | Essay prompt, relevant position, reasoning and support |
| Summarize Written Text | Yes | Source passage |
| Summarize Spoken Text | Yes | Reviewed source transcript/key points |
| Read Aloud | No | Reproducing the supplied passage is expected |
| Repeat Sentence | No | Reproducing the sentence is expected |
| Write from Dictation | No | Reproducing the dictated words is expected |
| Answer Short Question | No | A short fixed answer is expected |
| MCQs, fill-in-the-blanks, ordering, word selection | No | Separate answer-key/rule scoring applies |

The same evaluation pipeline serves full mock exams and single-question practice.
All scoring modes receive the integrity override when it triggers.

## How Each Check Works

### 1. Repetition Within the Answer

`examinor/services/repetitive_answer.py` checks repeated word fragments,
sentence openings, similar sentence structures, repetition coverage and
vocabulary diversity. Multiple strong signals or dominant exact repetition
are required; repeating one phrase twice is not an automatic zero.

Minimum lengths and thresholds vary by task profile. Shorter answers can still
lose ordinary rubric marks even when too short for a repetition-based hard zero.
Detection can be disabled with `REPETITIVE_ANSWER_DETECTION_ENABLED=false`.

### 2. Trainer-Reviewed Known Templates

`examinor/services/known_answer_templates.py` compares the answer with active
`AnswerTemplate` records for that question type. Fixed wording is matched;
placeholder fields such as `[[topic]]` are excluded.

The reviewed catalog currently contains four frameworks, from the expert's
Universal templates document:

| Template | Minimum Answer Coverage | Minimum Matched Words | Minimum Separate Matching Blocks | Maximum Unmatched Words |
| --- | --- | --- | --- | --- |
| Describe Image | 60% | 35 | 3 | 24 |
| Retell Lecture | 58% | 32 | 3 | 30 |
| Summarise Group Discussion | 62% | 80 | 5 | 55 |
| Respond to a Situation | 60% | 35 | 3 | 24 |

All conditions must be met. These values are per-template and editable in
**Question bank > Answer templates**. The actual database may contain additional
trainer-approved templates or different configured thresholds.

Unmatched words are NOT proof of meaningful content. They could be unrelated
padding. The semantic check below separately examines what the answer means.
Conversely, if the new, source-grounded assessment identifies valid specific
content, a known-framework match is downgraded to a review flag rather than an
automatic zero. The lexical match evidence is retained.

Set `KNOWN_TEMPLATE_DETECTION_ENABLED=false` to disable this check independently.
There is no invented Essay blacklist: unfamiliar essay scripts are assessed by
the question-grounded check, and genuine new library entries need trainer review.

### 3. Question-Grounded Assessment of Unfamiliar Scripts

`examinor/services/template_content.py` requests an additional structured field
in the existing AI evaluation, not a separate routine provider call.

The evaluator must identify:

- Whether the answer is substantive, template-dominated, or uncertain.
- Whether it actually addresses the task.
- Exact candidate quotations containing generic material, with reasons.
- Exact candidate quotations expressing meaningful task-specific ideas, with reasons.
- Its confidence in that judgement and a task-grounded explanation.

Code verifies that the quoted words really occur in the saved answer. Generic
and specific evidence must not overlap. Overlapping generic quotations do not
inflate the counted coverage. The application, not the evaluator, makes the
final template-override decision using these conditions:

| Condition for Automatic Zero | Default |
| --- | --- |
| Eligible descriptive question type | One of the seven above |
| Minimum answer length | 25 words; 80 for Essay |
| Evaluator verdict | Template-dominated |
| Evaluator confidence | At least 0.90 |
| Addresses the task | No |
| Meaningful specific points identified | None |
| Exact-quoted generic words | At least 20 |
| Generic-word coverage of the whole answer | At least 70% |
| Relevant question/source supplied | Yes |
| Candidate and reference text within the provider's input limits | Yes |

ALL conditions are required. Confidence is a model judgement, not a calibrated
probability. A weak answer with some relevant content is not automatically zero
under this semantic gate; the task rubric still determines its marks.

Below-threshold, uncertain, missing-source or truncated-context cases are flagged
for review instead of receiving this hard-zero override. The new assessment is
not required below the configured minimum length; other integrity and rubric
rules remain active.

A missing or structurally invalid assessment on an eligible response triggers
the existing bounded output-repair path. If it remains invalid, evaluation fails
rather than publishing a score with the required check silently omitted.

Unusable quotations (not exact, too short, missing a reason, or generic quotes
overlapping specific ones) also trigger that repair. If the repaired output
still contains them, they are dropped and recorded in `dropped_evidence` instead
of failing the evaluation. Dropping can only make the outcome more lenient: a
verdict that loses specific evidence, or a substantive verdict left without
any, becomes `uncertain` and is flagged for review, never zeroed.
Language-only audits cannot erase an already-valid template assessment.

Set `TEMPLATE_CONTENT_DETECTION_ENABLED=false` to disable only this semantic check.
`python manage.py check_evaluation_runtime` reports whether it is enabled.
`TEMPLATE_CONTENT_CONFIG` in Django settings can override `minimum_words`,
`essay_minimum_words`, `minimum_generic_words`, `hard_ratio` and
`minimum_confidence`. Most thresholds are code/settings configuration, not new
admin-dashboard fields.

## Results, Evidence and Cache Behaviour

| Check | Evidence Location in `evaluation_result` | Override Code |
| --- | --- | --- |
| Repetition | `integrity_checks.repetition` | `repetitive_template_answer` |
| Known template | `integrity_checks.known_template` | `known_template_dominated` |
| Question-grounded template content | `integrity_checks.template_content` | `template_content_dominated` |
| Copied question, separate Essay/Situation rule | `integrity_checks.prompt_copy` | `copied_question_answer` |

When an override applies, every criterion's awarded score becomes zero. Existing
score compilation therefore produces zero skill contributions. Maxima remain
unchanged. `score_overrides` preserves original marks and the reason for the
override. Multiple integrity checks preserve the same original assessment.

A semantic hard zero also replaces the feedback summary with the explanation
for the zero. It is an answer-integrity decision, not an invented grammar or
pronunciation error.

The prompt version has advanced to `pte-evaluation-prompt-v6`, preventing reuse
of old-prompt cache entries. New cache entries keep validated rubric scores and
assessment evidence before the semantic override. The current semantic policy
is reapplied on cache reads, so cached raw marks cannot bypass the check.

## Examples for Trainers

| Submission | Treatment |
| --- | --- |
| A reusable paragraph praising how informative any image is, with no actual observations | Hard zero when evidence/threshold conditions are met |
| An unfamiliar generic script expressed once, without repeated phrases | New semantic check can catch it |
| A coherent chart description using real labels, comparisons and trends | Normal evaluation, even with a familiar opening |
| A polite request that actually asks for the specified change and explains why | Normal evaluation |
| A source summary that attributes real viewpoints to the speakers | Normal evaluation |
| A few topic nouns inserted into mostly generic prose | Topic nouns alone are not meaningful specific points |
| A partly relevant answer with thin reasoning | Rubric scoring; possible review, not a blanket semantic zero |
| Correct Read Aloud or Repeat Sentence reproduction | Template gates do not run |

## Testing and Deployment

Automated tests cover unfamiliar scripts, substantive responses, all seven
eligible tasks, exclusions, quote validation, overlap counting, uncertainty,
source/context safeguards, cache reuse, language-audit preservation, and both
UserResponse and SingleResponse scoring paths.

Run the focused suite on a configured backend test database:

```bash
python manage.py test \
  examinor.test_template_content \
  examinor.test_known_answer_templates \
  examinor.test_repetitive_answer \
  examinor.test_prompt_copy \
  examinor.test_evaluation_context
```

The staff-only `POST /mocktest/answer-integrity-test/` endpoint still runs the
deterministic repetition/library checks on arbitrary text. It does NOT run the
new semantic check: that needs the actual question/source and AI evaluation.
Use normal single-question practice with the correct source to test that path.

The template change needs a backend deployment and Django/Celery restart, not a new
database migration or a frontend build. When deploying together with the strict
Form policy, install its new `pysbd` dependency first. Existing stored results are NOT changed
automatically. Selected historical cases require a controlled evaluation retry;
the existing completed-response guard still applies.

## Limitations and Acceptance

- This is not internet-wide plagiarism detection or proof of memorization.
- Semantic relevance is still AI-assisted. Exact quotation validation establishes
  that evidence exists, not that the model interpreted it perfectly.
- The known-template library is finite; a missing library match is not proof of originality.
- Repetition is an independent gate and can still apply to a repetitive answer
  containing some correct information.
- Text matching cannot repair an incorrect audio transcript. Transcription must
  be verified separately when the spoken words are disputed.
- Schema repair can add provider calls. The normal semantic assessment adds
  output tokens within the existing evaluation call; it is not cost-free.
- Mocked-provider automated tests verify integration and policy behaviour, not
  real-model detection accuracy. Before client sign-off, trainers should compare
  a labelled set of genuine, weak, partly relevant and template-heavy responses
  across the covered tasks, including deliberately paraphrased scripts.
