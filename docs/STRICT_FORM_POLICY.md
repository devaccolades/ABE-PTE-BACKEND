# Company Strict Form Policy

Approved company decision: full Form eligibility or zero for the whole answer.
Updated: 20 October 2026.

## Active Rules

| Task | Inclusive Allowed Word Count | Additional Form Requirement |
| --- | --- | --- |
| Summarize Spoken Text | 50-70 | Must meet the remaining task Form requirements |
| Summarize Written Text | 5-75 | One single, complete sentence |
| Write Essay | 200-300 | Must meet the remaining task Form requirements |

Outside these word limits, ALL awarded criterion scores and skill contributions
for that answer become zero. There is no partial-credit word-count band under
this company policy. The entire exam is not zeroed.

Examples:

- SST: 49 words = zero; 50-70 = eligible; 71 words = zero.
- SWT: 4 words = zero; 5-75 in one complete sentence = eligible; 76 = zero.
- Essay: 199 words = zero; 200-300 = eligible; 301 words = zero.
- An otherwise eligible answer still receives zero when its validated Form
  criterion is below the rubric maximum.
- Full Form eligibility does not guarantee full content, grammar or other marks.

## Company Policy, Not Pearson's Partial-Credit Policy

Pearson allows reduced Form credit for SST answers of 40-49 or 71-100 words and
Essay answers of 120-199 or 301-380 words. The company has deliberately chosen
not to award those intermediate bands. SWT has no intermediate Form band.

Sources: [Pearson SST Form table, page 42](https://www.pearsonpte.com/content/dam/ELL/pte/pearsonpte/resources/PTE-Academic-Test-Taker-Score-Guide.pdf#page=42),
[Essay Form table, page 35](https://www.pearsonpte.com/content/dam/ELL/pte/pearsonpte/resources/PTE-Academic-Test-Taker-Score-Guide.pdf#page=35),
[SWT Form table, page 33](https://www.pearsonpte.com/content/dam/ELL/pte/pearsonpte/resources/PTE-Academic-Test-Taker-Score-Guide.pdf#page=33).

## Backend Enforcement

The shared service is `examinor/services/strict_form.py`.

1. Candidate text is extracted using the same canonical answer extractor as AI
   grading. This supports typed strings and supported answer-data wrappers.
2. Word counts are checked before AI evaluation or cache lookup. Clearly invalid
   answers complete with a policy zero and explanation, without an AI call.
3. SWT sentence boundaries are checked using `pysbd==0.3.4`, rather than splitting
   on every full stop. Abbreviations and decimal numbers are handled by the
   sentence-boundary library. Grammatical sentence completeness still needs the
   task rubric; a segmenter does not prove a phrase is a complete sentence.
4. The AI prompt receives the backend's word count and the company policy. The
   remaining Form requirements are evaluated against the supplied rubric.
5. Any assessed Form score below its maximum triggers the whole-answer zero.
   The same policy is reapplied to cache hits and at final response validation.
6. Original marks are retained in the override history. If a different integrity
   gate already zeroed the scores, its synthetic Form zero is not misreported
   as a new Form-eligibility failure.

Both full exams and single-question practice use this service. Legacy, shadow
and V2 score compilation receive zeroed criterion scores when it triggers.
Other task types are unchanged.

### Word Counting Convention

The backend normalizes Unicode compatibility characters and splits on whitespace.
A token counts as a word when it contains a letter or digit. Contractions and
hyphenated terms without spaces count as one token. Punctuation-only tokens do
not count. Unicode spaces are recognized. This is our explicit implementation
convention, not a claim to reproduce Pearson's unpublished tokenizer exactly.

### Evidence

`evaluation_result.integrity_checks.strict_form` includes:

- `policy_source`: `company`.
- `detector_version`: `company-strict-form-v1`.
- Measured word count and permitted minimum/maximum.
- SWT sentence count where applicable.
- Original assessed Form, if available.
- Violations and an explanation.

An applied override uses `score_overrides[].code = company_strict_form` and
preserves original marks. Feedback explains that the zero comes from company
policy. A preflight zero records `provider_called=false`; it is not an AI mark.

## Configuration and Deployment

The policy is enabled by default. Emergency rollback switch:

```env
STRICT_FORM_POLICY_ENABLED=false
```

`python manage.py check_evaluation_runtime` reports its state. Disabling it does
not disable template, repetition or other scoring gates.

Install the new dependency in the server virtual environment before restarting:

```bash
/home/ubuntu/venv/bin/python -m pip install "pysbd==0.3.4"
/home/ubuntu/venv/bin/python manage.py check
/home/ubuntu/venv/bin/python manage.py test examinor.test_strict_form
```

Then restart Django and Celery during an appropriate deployment window, checking
active/reserved jobs before restarting the worker. No new database migration or
frontend build is required. A frontend word counter or warning has not been
changed as part of this backend task.

Existing saved results are not automatically rewritten. Newly evaluated answers
use the active policy, including new answers in existing sessions: this is a
global company gate, not a newly session-pinned scoring-mode version. Historical
changes require an explicitly approved retry/repair, with result/PDF version
impacts reviewed separately.
