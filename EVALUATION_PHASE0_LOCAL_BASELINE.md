# Evaluation Phase 0 Local Baseline

## Status

Phase 0 is in progress. This record captures the local baseline observed on
4 August 2026 before any migration-history repair.

No migration file, migration record, schema object, or application data was
changed while collecting this evidence.

## Local Application State

- Branch: `aswb`
- Commit: `1d6e8d5`
- Database engine: SQLite
- SQLite version: `3.45.1`
- Ordinary Django system check: passed
- Existing automated tests: 106 passed before Phase 0 implementation began
- Git-tracked application migrations: none
- Local application migration files: present but ignored by `.gitignore`

The worktree also contained a pre-existing change to `abe_pte/settings.py`. It
is outside Phase 0 and has not been modified by this work.

## Local Applied Migration Chain

```text
mocktest.0001_initial
mocktest.0002_alter_subquestion_options_and_more
mocktest.0003_singleresponse_evaluation_attempts_and_more
mocktest.0004_alter_usermocktestsession_total_score
mocktest.0005_response_repair_indexes
mocktest.0006_backfill_singleresponse_evaluation_status
mocktest.0007_question_answer_explanation_and_more

examinor.0001_initial
examinor.0002_evaluationcache_model_and_constraint
```

`migrate --plan` reports no unapplied local migration file.

## Confirmed Local Drift

`makemigrations --check --dry-run` detects one missing migration operation:

```text
mocktest/migrations/0008_userresponse_uniq_userresp_session_question.py
+ Create constraint uniq_userresp_session_question on model userresponse
```

Database introspection confirms that the local `mocktest_userresponse` table
does not currently contain that unique constraint, although the model declares
it. The evaluation-cache uniqueness constraint and evaluation lookup indexes do
exist locally.

## Production History Warning

Older server output shared during July showed a different migration chain,
including names such as `mocktest.0002_singleresponse` and
`mocktest.0007_userresponse_uniq_userresp_session_question`. That historical
output is useful evidence of divergence, but it is not accepted as the current
production baseline.

Do not generate, rename, delete, fake, or apply migrations on production until a
fresh production report has been collected and compared with this local record.

## Evidence Collector

The read-only command below records Git identity, migration file checksums,
applied migration rows, model drift, migration plan, and application-table
columns and constraints. It intentionally excludes database credentials and API
keys.

```bash
mkdir -p /home/ubuntu/abe-phase0
python manage.py collect_evaluation_baseline \
  --output /home/ubuntu/abe-phase0/production-baseline.json
sha256sum /home/ubuntu/abe-phase0/production-baseline.json
```

The production report and checksum must be reviewed before migration
reconciliation begins.

## Collector Verification

- Two focused collector tests passed.
- The complete test suite passed: 108 tests.
- `python manage.py check` passed.
- The local database SHA-256 checksum was identical before and after collection.
- The report detected the expected `0008` model drift without creating a file.

## Remaining Phase 0 Evidence

- Current production baseline report from the collector
- Full database backup metadata and checksum
- Successful isolated database restore evidence
- Media backup manifest and restore sample
- Current staging baseline, once the production clone exists
- Approved canonical migration mapping for local and production histories
- Fresh-database migration test using only Git-tracked files
- Production-clone upgrade rehearsal and rollback rehearsal
