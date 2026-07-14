# Question Bank Owner Messages

Generated from `question_bank_grouped_by_mock_test.xlsx` after excluding shared
trait-mapping and missing-score-maximum repairs handled centrally by the backend.

Do not delete questions or submitted responses. Update only the answer metadata
listed below, then notify the backend team so the audit and affected results can
be recalculated.

## Mock Test 6452

Hi, we completed the system-level corrections for **6452**. Please make these
remaining question-content corrections:

- Question `30` (Reorder Paragraphs): add at least two paragraphs and set their correct order.
- Question `411` (Reading Drag and Drop): mark the correct options and assign each correct blank position.
- Questions `420, 422` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `428, 437` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Anishya_T1

Hi Anishya, we completed the system-level corrections for **Anishya_T1**. Please
make these remaining question-content corrections:

- Questions `652, 655` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `635, 638` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Anupama

Hi Anupama, we completed the system-level corrections for **Anupama**. Please
make these remaining question-content corrections:

- Questions `334, 474, 476, 478, 479` (Reading Dropdown): ensure every blank has exactly one correct option.
- Question `491` (Reading Drag and Drop): remove duplicate blank positions and assign one correct option to each required position.
- Questions `500, 501` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `507, 508` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Athira

Hi Athira, we completed the system-level corrections for **Athira** and
**ATHIRA MT2**. ATHIRA MT2 has no remaining manual items. For **Athira**, please
make these corrections:

- Questions `31, 215` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `38, 205` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Bindu_T1

Hi Bindu, we completed the system-level corrections for **Bindu_T1**. Please
make these remaining question-content corrections:

- Questions `307, 308` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `309, 310` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Hitha Test 01

Hi Hitha, we completed the system-level corrections for **Hitha Test 01**.
Please make these remaining question-content corrections:

- Questions `399, 400, 401, 402` (Reading Drag and Drop): mark the correct options and assign each correct blank position.
- Questions `540, 541, 542` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `550, 551, 552` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.
- Question `556` (Write From Dictation): enter the exact spoken sentence in **Correct answer**.

## Paval_T1

Hi Paval, we completed the system-level corrections for **Paval_T1**. Please
make these remaining question-content corrections:

- Question `535` (Reading Dropdown): ensure the affected blank has exactly one correct option.
- Questions `651, 654` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `636, 639` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Salini

Hi Salini, we completed the system-level corrections for **Salini**. Please
make these remaining question-content corrections:

- Questions `76, 583` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `134, 607` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.
- Question `212` (Repeat Sentence): assign it to the correct mock-test section, or confirm it is intentionally unused.

## Santhi - T1

Hi Santhi, we completed the system-level corrections for **Santhi - T1**.
Please make these remaining question-content corrections:

- Question `533` (Reading Dropdown): ensure the affected blank has exactly one correct option.
- Questions `650, 653` (Listening Fill in the Blanks): add each missing word to the blank's **Correct answer** field in order.
- Questions `637, 640` (Highlight Incorrect Words): add the accurate transcript to **Correct answer**, or enter the incorrect displayed words separated by `|`.

## Backend Follow-Up

After owners finish:

1. Run `python manage.py check_question_bank --skip-media-check --output question_bank_audit_after_manual_fixes.csv`.
2. Resolve any remaining errors before conducting new exams.
3. Re-evaluate corrected rule-based responses and recalculate affected session scores.
