# Evaluation Cases

A suite of realistic student submissions for every question type, each with the
outcome company policy expects. It runs submissions through the real
`evaluate_single_response` task (retries included) against the production question
bank, so it catches problems that unit tests with mocked AI output cannot, such as
the AI evaluator rejecting its own output or a gate zeroing a valid answer.

Cases live in `mocktest/evaluation_cases/` (`speaking.py`, `writing.py`,
`reading.py`, `listening.py`). Each names a real question by id and name, the
student's answer and the expectation.

## Getting the question bank

The bank contains every answer key, so it is gitignored and never committed.
On the server:

```bash
python manage.py backup_question_bank --skip-media --output-dir /tmp/qb
cp /tmp/qb/*/question_bank.json /home/ubuntu/question_bank.json
chown ubuntu:ubuntu /home/ubuntu/question_bank.json
```

Download it with `scp` or SFTP into the project root, then delete both server
copies. Never place it under `media/` or `static/`: nginx serves those publicly.

Describe Image cases need the question images; with `--skip-media` they are
reported as skipped.

## Running

```bash
python manage.py run_evaluation_cases --rule-only        # objective types only, free, seconds
python manage.py run_evaluation_cases                    # everything; AI cases call OpenAI
python manage.py run_evaluation_cases --task summarize_written_text --repeat 3
python manage.py run_evaluation_cases --case swt-good --verbose
python manage.py run_evaluation_cases --list
```

The bank is loaded into a temporary database that is deleted afterwards; your
local database and production are never touched. Local migrations must be up to
date (`makemigrations`) because the temporary database is built from them.

AI results vary between runs. Use `--repeat` before trusting a pass or a fix:
a case that passes some runs and not others is reported as `FLAKY`.
`--report path.json` saves every run's scores, overrides and errors.

## Reading the report

| Verdict | Meaning |
| --- | --- |
| `PASS` | Every run met the expectation. |
| `FAIL` / `FLAKY` | No run / only some runs met it. The command exits non-zero. |
| `KNOWN` | Fails, but the case documents this as a known issue. |
| `FIXED?` | A known-issue case now passes. Confirm with `--repeat`, then remove its `known_issue`. |
| `SKIPPED` | Inputs unavailable (Describe Image without media). |

## Adding a case

Add an entry to the relevant module. Expectations (all optional):

- `status`: final status, `"completed"` (default) or `"failed"`.
- `zero`: `True` when the whole answer must score zero, `False` when it must not.
- `override`: an applied override code, e.g. `source_fidelity_failed`,
  `company_strict_form`, `template_content_dominated`, `copied_question_answer`.
- `no_override`: no score override may apply.
- `ratio`: `(low, high)` bounds on total / maximum.
- `traits`: `{"content": (low, high)}` bounds on raw trait scores.

Spoken cases supply a transcript without audio measurements, so never assert
pronunciation or fluency. For objective types, `KeyAnswer("correct")` and the
other variants in `answers.py` build the exact payload the frontend sends from the
answer key. Link trainer reports with `trainer_ref` (see
[Trainer Evaluation Review](TRAINER_EVALUATION_REVIEW.md)) and record a current
defect with `known_issue` rather than loosening the expectation.

`mocktest/test_evaluation_cases.py` runs in the normal test suite and checks that
every task type has cases and every definition is well formed.
