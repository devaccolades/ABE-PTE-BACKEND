# Session Finalization Contract

## Scope

This contract applies to mock-test sessions created after the session-manifest
deployment. Historical sessions without a `manifest_version` continue through
the legacy compatibility path.

## Session Start

`POST /mocktest/start-test/` creates the session and its immutable question
manifest in one transaction.

The manifest freezes:

- question and section order;
- question text, instructions, media names, options, and blanks;
- rubric and trait-to-skill map;
- expected input type;
- per-skill maximum scores;
- mock-test title and metadata.

Questions added to or edited in the live question bank after session start do
not change the candidate's session. Question-bank records used by versioned
sessions cannot be edited or deleted through normal Django model/admin paths;
create a new mock-test version for future candidates.

## Question States

Every expected question has exactly one state:

- `pending`: not resolved yet;
- `answered`: linked to one saved `UserResponse`;
- `skipped`: explicitly skipped by policy;
- `timed_out`: unresolved when its section timer expired;
- `not_reached`: unresolved when the exam was explicitly submitted.

Skipped, timed-out, and not-reached questions receive zero awarded points while
their snapshotted maxima remain in the denominator.

## Submission And Completion

`submission_completed_at` means the candidate cannot provide more normal exam
answers. It is set when every manifest question is resolved or when
`POST /mocktest/complete-session/` resolves the remaining questions as
`not_reached`.

`is_completed` means one immutable `SessionResult` has been finalized. It does
not mean that the last numbered question was submitted.

Finalization requires:

- submission is complete;
- every expected question is resolved;
- every answered question has exactly one response;
- every answered response has completed evaluation;
- no duplicate response group exists.

Finalization locks the session row, calculates all skill and overall totals,
and promotes a versioned `SessionResult` in one transaction. Repeating the same
finalization is idempotent. A changed re-evaluation creates the next result
version instead of overwriting the previous result.

## Frontend Contract

The frontend must:

1. Use the ordered questions returned for the session rather than rebuilding
   order from the live mock-test definition.
2. Send `timer-exceeded: true` when a section timer expires.
3. Call `POST /mocktest/complete-session/` when the candidate explicitly ends
   the exam or leaves remaining questions unanswered.
4. Poll `GET /mocktest/session-evaluation-status/?session_id=...` until
   `is_complete` is true.
5. Enable PDF download only when `can_download_final_pdf` is true.

The status response distinguishes:

- `submission_completed_at`;
- `finalized_at` and `finalized_result_version`;
- expected, resolved, answered, skipped, timed-out, not-reached, and pending
  question counts;
- response evaluation counts and errors.

## PDF Contract

A final PDF is unavailable while any required evaluation is pending or failed.
Once finalized, its title, questions, answers, feedback, skill scores, and
overall score are rendered from the immutable `SessionResult` snapshot.

Queuing a retry immediately sets `is_completed` false and blocks PDF download.
Successful re-evaluation promotes either the same content version or a new
version when the result changed.

## Deployment And Compatibility

The migration is additive. It creates `SessionQuestion` and `SessionResult`,
adds finalization metadata to `UserMockTestSession`, and protects response-linked
questions from deletion. It does not backfill or rewrite historical sessions.

After deployment, verify a newly started test creates the expected manifest
count before reopening broad candidate testing.
