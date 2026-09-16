import math
from copy import deepcopy

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from examinor.scoring.contracts import VALID_SKILLS
from examinor.scoring.response_scores import (
    compile_response_score_evidence,
    promoted_skill_values,
    response_scoring_mode,
)
from mocktest.models import SingleResponse, UserMockTestSession, UserResponse


class Command(BaseCommand):
    help = (
        "Correct one confirmed grammar/spelling annotation and its criterion "
        "scores without calling an AI provider. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--response-id", type=int, required=True)
        parser.add_argument("--single", action="store_true")
        parser.add_argument("--question-id", type=int, required=True)
        parser.add_argument("--error-text", required=True)
        parser.add_argument("--expected-suggestion", required=True)
        parser.add_argument(
            "--expected-type",
            choices=("grammar", "spelling"),
            required=True,
        )
        parser.add_argument(
            "--new-type",
            choices=("grammar", "spelling"),
            required=True,
        )
        parser.add_argument("--expected-grammar-score", type=float, required=True)
        parser.add_argument("--new-grammar-score", type=float, required=True)
        parser.add_argument("--expected-spelling-score", type=float, required=True)
        parser.add_argument("--new-spelling-score", type=float, required=True)
        parser.add_argument("--reason")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        self._validate_options(options)
        response = self._get_response(options, lock=False)
        corrected_result = self._corrected_result(response, options)
        before = self._awarded_scores(response)
        after = self._proposed_awards(response, corrected_result)
        self._print_plan(response, options, before, after)

        if not options["confirm"]:
            self.stdout.write("Dry run only. No response or session score was changed.")
            return

        with transaction.atomic():
            response = self._get_response(options, lock=True)
            corrected_result = self._corrected_result(response, options)
            before = self._awarded_scores(response)
            response.evaluation_result = corrected_result
            response.apply_skill_scores()
            after = self._awarded_scores(response)
            self._record_history(response, options, before, after)

            session_count = 0
            if isinstance(response, UserResponse):
                session = UserMockTestSession.objects.select_for_update().get(
                    pk=response.user_session_id,
                )
                session.aggregate_scores()
                session_count = 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Corrected response {response.pk} from "
                f"{options['expected_type']} to {options['new_type']}; "
                f"recalculated {session_count} session(s). "
                "No AI provider was called."
            )
        )

    @staticmethod
    def _validate_options(options):
        if options["expected_type"] == options["new_type"]:
            raise CommandError("--expected-type and --new-type must differ.")
        if options["confirm"] and not options["reason"]:
            raise CommandError("--reason is required with --confirm.")
        for key in (
            "expected_grammar_score",
            "new_grammar_score",
            "expected_spelling_score",
            "new_spelling_score",
        ):
            value = options[key]
            if not math.isfinite(value) or value < 0:
                raise CommandError(
                    f"--{key.replace('_', '-')} must be finite and non-negative."
                )

    @staticmethod
    def _model(options):
        return SingleResponse if options["single"] else UserResponse

    def _get_response(self, options, *, lock):
        query = self._model(options).objects
        if lock:
            query = query.select_for_update()
        try:
            response = query.get(pk=options["response_id"])
        except self._model(options).DoesNotExist as exc:
            raise CommandError(
                f"{self._model(options).__name__} {options['response_id']} does not exist."
            ) from exc

        if response.question_id != options["question_id"]:
            raise CommandError(
                f"Response question_id is {response.question_id}, not "
                f"{options['question_id']}."
            )
        if not response.evaluated or response.evaluation_status != "completed":
            raise CommandError("Response must have a completed evaluation.")
        return response

    def _corrected_result(self, response, options):
        result = deepcopy(response.evaluation_result or {})
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise CommandError("Response has no stored evaluation payload.")
        scores = evaluation.get("scores")
        feedback = evaluation.get("feedback")
        errors = feedback.get("errors") if isinstance(feedback, dict) else None
        if not isinstance(scores, dict) or not isinstance(errors, list):
            raise CommandError("Response has no structured language feedback.")

        matches = [
            error
            for error in errors
            if isinstance(error, dict)
            and str(error.get("text") or error.get("original") or "").strip()
            == options["error_text"]
            and str(error.get("suggestion") or "").strip()
            == options["expected_suggestion"]
            and str(error.get("type") or "").strip().lower()
            == options["expected_type"]
        ]
        if len(matches) != 1:
            raise CommandError(
                "Expected exactly one matching language annotation; "
                f"found {len(matches)}."
            )

        expected_scores = {
            "grammar": options["expected_grammar_score"],
            "spelling": options["expected_spelling_score"],
        }
        new_scores = {
            "grammar": options["new_grammar_score"],
            "spelling": options["new_spelling_score"],
        }
        for criterion, expected in expected_scores.items():
            payload = scores.get(criterion)
            if not isinstance(payload, dict):
                raise CommandError(f"Response has no {criterion} score.")
            current = float(payload.get("score") or 0)
            maximum = float(payload.get("max", payload.get("maximum")) or 0)
            if not math.isclose(current, expected, rel_tol=1e-9, abs_tol=1e-9):
                raise CommandError(
                    f"Current {criterion} score is {current:g}, not {expected:g}."
                )
            if new_scores[criterion] > maximum:
                raise CommandError(
                    f"New {criterion} score exceeds maximum {maximum:g}."
                )

        matches[0]["type"] = options["new_type"]
        scores["grammar"]["score"] = options["new_grammar_score"]
        scores["spelling"]["score"] = options["new_spelling_score"]
        evaluation["weighted_score"] = sum(
            float(payload.get("score") or 0)
            for payload in scores.values()
            if isinstance(payload, dict)
        )
        return result

    @staticmethod
    def _proposed_awards(response, result):
        evidence = compile_response_score_evidence(
            response.question,
            result,
            mode=response_scoring_mode(response),
        )
        return promoted_skill_values(evidence)

    @staticmethod
    def _awarded_scores(response):
        return {
            skill: float(getattr(response, f"{skill}_score_awarded") or 0)
            for skill in VALID_SKILLS
        }

    def _print_plan(self, response, options, before, after):
        self.stdout.write("Language error classification correction")
        self.stdout.write("========================================")
        self.stdout.write(f"Response: {response.pk}")
        self.stdout.write(f"Question: {response.question_id}")
        if isinstance(response, UserResponse):
            self.stdout.write(f"Session: {response.user_session_id}")
        self.stdout.write(f"Error: {options['error_text']!r}")
        self.stdout.write(f"Suggestion: {options['expected_suggestion']!r}")
        self.stdout.write(
            f"Classification: {options['expected_type']} -> {options['new_type']}"
        )
        self.stdout.write(
            "Grammar score: "
            f"{options['expected_grammar_score']:g} -> "
            f"{options['new_grammar_score']:g}"
        )
        self.stdout.write(
            "Spelling score: "
            f"{options['expected_spelling_score']:g} -> "
            f"{options['new_spelling_score']:g}"
        )
        self.stdout.write(f"Skill awards before: {before}")
        self.stdout.write(f"Skill awards after: {after}")

    @staticmethod
    def _record_history(response, options, before, after):
        result = dict(response.evaluation_result or {})
        history = list(result.get("evaluation_corrections") or [])
        history.append({
            "corrected_at": timezone.now().isoformat(),
            "source": "correct_language_error_classification",
            "question_id": response.question_id,
            "error_text": options["error_text"],
            "suggestion": options["expected_suggestion"],
            "type_before": options["expected_type"],
            "type_after": options["new_type"],
            "grammar_score_before": options["expected_grammar_score"],
            "grammar_score_after": options["new_grammar_score"],
            "spelling_score_before": options["expected_spelling_score"],
            "spelling_score_after": options["new_spelling_score"],
            "skill_awards_before": before,
            "skill_awards_after": after,
            "reason": options["reason"],
        })
        result["evaluation_corrections"] = history
        response.evaluation_result = result
        response.save(update_fields=["evaluation_result"])
