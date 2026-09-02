import math
from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from examinor.scoring.contracts import VALID_SKILLS
from examinor.scoring.response_scores import (
    compile_response_score_evidence,
    promoted_skill_values,
    response_scoring_mode,
)
from mocktest.models import MockTest, SingleResponse, UserMockTestSession, UserResponse
from mocktest.services.question_bank_validation import (
    publication_errors,
    question_bank_queryset,
)
from mocktest.services.question_maximum_policy import maximum_policy_rows


class Command(BaseCommand):
    help = (
        "Validate and promote one active mock test from shadow scoring to V2. "
        "Dry-run by default; existing sessions remain pinned to their current mode."
    )

    def add_arguments(self, parser):
        parser.add_argument("mock_test", help="Mock test UUID or exact title.")
        parser.add_argument(
            "--expected-current-mode",
            default="shadow",
            choices=("legacy", "shadow"),
        )
        parser.add_argument("--expected-question-count", type=int)
        parser.add_argument("--expected-session-count", type=int)
        parser.add_argument("--expected-user-response-count", type=int)
        parser.add_argument("--expected-single-response-count", type=int)
        parser.add_argument("--expected-reference-difference-count", type=int)
        parser.add_argument("--expected-review-required-count", type=int)
        parser.add_argument(
            "--acknowledge-policy-warnings",
            action="store_true",
            help=(
                "Explicitly acknowledge reviewed question-weight reference "
                "differences and tasks without a universal reference."
            ),
        )
        parser.add_argument("--reason")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        mock_test = self._mock_test(options["mock_test"])
        audit = self._audit(mock_test)
        self._print_audit(mock_test, audit)
        self._validate_rollout(mock_test, audit, options)

        if not options["confirm"]:
            self.stdout.write(
                "Dry run only. The mock test and all session scores are unchanged."
            )
            return

        self._check_expected_counts(audit, options)
        with transaction.atomic():
            locked = MockTest.objects.select_for_update().get(pk=mock_test.pk)
            if locked.scoring_mode != options["expected_current_mode"]:
                raise CommandError(
                    f"Current scoring mode changed to {locked.scoring_mode!r}; "
                    f"expected {options['expected_current_mode']!r}. Nothing was changed."
                )
            locked.scoring_mode = "v2"
            locked.save(update_fields=["scoring_mode"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Mock test {mock_test.title!r} now assigns V2 scoring to newly "
                f"started sessions. {audit['session_count']} existing session(s) "
                "remain pinned to their previous scoring mode; no response or "
                "session score was changed."
            )
        )
        self.stdout.write(f"Rollout reason: {options['reason']}")

    def _audit(self, mock_test):
        questions = list(
            question_bank_queryset(mock_test=mock_test).select_related("subsection")
        )
        policy_statuses = Counter()
        for question in questions:
            policy_statuses.update(
                row["status"] for row in maximum_policy_rows(question)
            )

        user_responses = list(
            UserResponse.objects.filter(
                mock_test=mock_test,
                evaluated=True,
                evaluation_result__isnull=False,
            ).select_related("question__subsection", "user_session")
        )
        single_responses = list(
            SingleResponse.objects.filter(
                question__mock_test_section__mock_test=mock_test,
                evaluated=True,
                evaluation_result__isnull=False,
            ).select_related("question__subsection")
        )

        compile_errors = []
        stored_mismatches = []
        for response in user_responses:
            try:
                v2_evidence = compile_response_score_evidence(
                    response.question,
                    response.evaluation_result,
                    mode="v2",
                )
                current_evidence = compile_response_score_evidence(
                    response.question,
                    response.evaluation_result,
                    mode=response_scoring_mode(response),
                )
            except (TypeError, ValueError) as exc:
                compile_errors.append(f"UserResponse {response.pk}: {exc}")
                continue
            self._collect_mismatch(response, current_evidence, stored_mismatches)
            if v2_evidence["v2"] is None:
                compile_errors.append(
                    f"UserResponse {response.pk}: missing V2 score evidence"
                )

        for response in single_responses:
            try:
                evidence = compile_response_score_evidence(
                    response.question,
                    response.evaluation_result,
                    mode="v2",
                )
            except (TypeError, ValueError) as exc:
                compile_errors.append(f"SingleResponse {response.pk}: {exc}")
                continue
            if evidence["v2"] is None:
                compile_errors.append(
                    f"SingleResponse {response.pk}: missing V2 score evidence"
                )

        sessions = UserMockTestSession.objects.filter(mock_test=mock_test)
        return {
            "question_count": len(questions),
            "session_count": sessions.count(),
            "open_session_count": sessions.filter(is_completed=False).count(),
            "user_response_count": len(user_responses),
            "single_response_count": len(single_responses),
            "reference_difference_count": policy_statuses["reference_difference"],
            "review_required_count": policy_statuses["review_required"],
            "peer_outlier_count": policy_statuses["peer_outlier"],
            "publication_errors": publication_errors(mock_test),
            "compile_errors": compile_errors,
            "stored_mismatches": stored_mismatches,
        }

    @staticmethod
    def _collect_mismatch(response, evidence, mismatches):
        expected = promoted_skill_values(evidence)
        actual = {
            skill: float(getattr(response, f"{skill}_score_awarded") or 0)
            for skill in VALID_SKILLS
        }
        if any(
            not math.isclose(
                actual[skill],
                expected[skill],
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
            for skill in VALID_SKILLS
        ):
            mismatches.append(response.pk)

    def _print_audit(self, mock_test, audit):
        self.stdout.write("Mock-test V2 scoring rollout")
        self.stdout.write("============================")
        self.stdout.write(f"Mock test: {mock_test.title} ({mock_test.pk})")
        self.stdout.write(f"Active: {'yes' if mock_test.is_active else 'no'}")
        self.stdout.write(f"Current scoring mode: {mock_test.scoring_mode}")
        self.stdout.write(f"Questions: {audit['question_count']}")
        self.stdout.write(f"Existing sessions: {audit['session_count']}")
        self.stdout.write(f"Open existing sessions: {audit['open_session_count']}")
        self.stdout.write(
            f"Evaluated UserResponses: {audit['user_response_count']}"
        )
        self.stdout.write(
            f"Evaluated SingleResponses: {audit['single_response_count']}"
        )
        self.stdout.write(
            "Question-weight reference differences: "
            f"{audit['reference_difference_count']}"
        )
        self.stdout.write(
            f"Question weights requiring owner review: "
            f"{audit['review_required_count']}"
        )
        self.stdout.write(f"Publication errors: {len(audit['publication_errors'])}")
        self.stdout.write(f"V2 compile errors: {len(audit['compile_errors'])}")
        self.stdout.write(
            f"Stored promoted-score mismatches: {len(audit['stored_mismatches'])}"
        )

    @staticmethod
    def _validate_rollout(mock_test, audit, options):
        if not mock_test.is_active:
            raise CommandError("The mock test is inactive. Nothing was changed.")
        if mock_test.scoring_mode != options["expected_current_mode"]:
            raise CommandError(
                f"Current scoring mode is {mock_test.scoring_mode!r}; expected "
                f"{options['expected_current_mode']!r}. Nothing was changed."
            )
        if audit["publication_errors"]:
            details = "; ".join(
                issue["problem"] for issue in audit["publication_errors"][:5]
            )
            raise CommandError(f"Publication validation failed: {details}")
        if audit["compile_errors"]:
            raise CommandError(
                f"V2 compilation failed for {len(audit['compile_errors'])} "
                f"response(s): {audit['compile_errors'][0]}"
            )
        if audit["stored_mismatches"]:
            raise CommandError(
                "Stored promoted scores do not match their pinned scoring mode for "
                f"{len(audit['stored_mismatches'])} response(s)."
            )
        if options["confirm"] and not options["reason"]:
            raise CommandError("--reason is required with --confirm.")
        policy_warning_count = (
            audit["reference_difference_count"] + audit["review_required_count"]
        )
        if options["confirm"] and policy_warning_count:
            if not options["acknowledge_policy_warnings"]:
                raise CommandError(
                    f"{policy_warning_count} question-weight policy warning(s) "
                    "require --acknowledge-policy-warnings after owner review."
                )

    @staticmethod
    def _check_expected_counts(audit, options):
        guards = {
            "expected_question_count": "question_count",
            "expected_session_count": "session_count",
            "expected_user_response_count": "user_response_count",
            "expected_single_response_count": "single_response_count",
            "expected_reference_difference_count": "reference_difference_count",
            "expected_review_required_count": "review_required_count",
        }
        for option_name, audit_name in guards.items():
            expected = options[option_name]
            if expected is None or expected < 0:
                raise CommandError(
                    f"--{option_name.replace('_', '-')} is required with --confirm."
                )
            actual = audit[audit_name]
            if expected != actual:
                raise CommandError(
                    f"{audit_name.replace('_', ' ').title()} changed: expected "
                    f"{expected}, found {actual}. Nothing was changed."
                )

    @staticmethod
    def _mock_test(identifier):
        try:
            by_id = MockTest.objects.filter(pk=identifier).first()
        except (TypeError, ValueError, ValidationError):
            by_id = None
        if by_id:
            return by_id
        matches = MockTest.objects.filter(title=identifier)
        if matches.count() != 1:
            raise CommandError(
                "Mock test must match exactly one UUID or exact title."
            )
        return matches.get()
