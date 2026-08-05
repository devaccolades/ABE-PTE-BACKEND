from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from examinor.scoring.task_contracts import (
    PayloadStatus,
    inspect_answer_payload,
)
from examinor.scoring.validators import validate_and_normalize_evaluation_result
from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import SingleResponse, UserMockTestSession, UserResponse


JSON_ISSUE = "json_encoded_answer"
JSON_RULE_SUBSECTIONS = (
    "fib_dropdown",
    "fib_drag_drop",
    "reorder_paragraphs",
    "mc_multiple",
    "l_mc_multiple",
)


class Command(BaseCommand):
    help = (
        "Normalize JSON-encoded deterministic answers and recompute only those "
        "evaluations. Dry-run unless --confirm is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=("all", "user", "single"),
            default="all",
            help="Response model to inspect (default: all).",
        )
        parser.add_argument(
            "--subsection",
            choices=("all", *JSON_RULE_SUBSECTIONS),
            default="all",
            help="Rule subsection to inspect (default: all supported types).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Persist canonical answers and corrected deterministic scores.",
        )
        parser.add_argument(
            "--expected-count",
            type=int,
            help="Required with --confirm; write only when the eligible count matches.",
        )

    def handle(self, *args, **options):
        if options["confirm"] and options["expected_count"] is None:
            raise CommandError("--expected-count is required with --confirm.")
        if options["expected_count"] is not None and options["expected_count"] < 0:
            raise CommandError("--expected-count cannot be negative.")

        if options["confirm"]:
            with transaction.atomic():
                candidates = self._collect_candidates(options, lock=True)
                self._report(candidates)
                self._check_expected_count(candidates, options["expected_count"])
                self._apply(candidates)
            return

        candidates = self._collect_candidates(options, lock=False)
        self._report(candidates)
        self.stdout.write("Dry run only. No responses or scores were changed.")

    def _querysets(self, options, *, lock):
        models = []
        if options["model"] in {"all", "user"}:
            models.append(UserResponse)
        if options["model"] in {"all", "single"}:
            models.append(SingleResponse)

        subsection_names = (
            JSON_RULE_SUBSECTIONS
            if options["subsection"] == "all"
            else (options["subsection"],)
        )
        for model in models:
            queryset = (
                model.objects.filter(
                    question__subsection__name__in=subsection_names,
                )
                .select_related("question__subsection")
                .prefetch_related(
                    "question__options",
                    "question__sub_questions__options",
                )
                .order_by("id")
            )
            if lock:
                queryset = queryset.select_for_update()
            yield model, queryset

    def _collect_candidates(self, options, *, lock):
        candidates = []
        errors = []

        for model, queryset in self._querysets(options, lock=lock):
            for response in queryset:
                subsection = response.question.subsection
                inspection = inspect_answer_payload(
                    subsection.name,
                    response.answer_data,
                )
                issue_codes = {issue.code for issue in inspection.issues}
                if (
                    inspection.status != PayloadStatus.LEGACY_COMPATIBLE
                    or JSON_ISSUE not in issue_codes
                ):
                    continue

                ownership_errors = self._ownership_errors(
                    response,
                    inspection.normalized,
                )
                if ownership_errors:
                    errors.extend(
                        f"{model.__name__} response={response.pk}: {error}"
                        for error in ownership_errors
                    )
                    continue

                result = run_rule_evaluation(
                    user_answer=SimpleNamespace(answer_data=inspection.normalized),
                    question=response.question,
                    subsection=subsection,
                )
                is_valid, normalized_result, error = (
                    validate_and_normalize_evaluation_result(
                        result,
                        subsection.rubric,
                    )
                )
                if not is_valid:
                    errors.append(f"{model.__name__} response={response.pk}: {error}")
                    continue

                candidates.append({
                    "response": response,
                    "answer_data": inspection.normalized,
                    "evaluation_result": normalized_result,
                    "old_score": self._evaluation_score(response.evaluation_result),
                    "new_score": self._evaluation_score(normalized_result),
                })

        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError("No changes made because candidate validation failed.")
        return candidates

    def _ownership_errors(self, response, normalized_answer):
        subsection_name = response.question.subsection.name
        if subsection_name == "fib_dropdown":
            return self._dropdown_ownership_errors(
                response.question,
                normalized_answer,
            )

        valid_ids = {option.id for option in response.question.options.all()}
        if isinstance(normalized_answer, dict):
            selected_ids = set(normalized_answer.values())
        else:
            selected_ids = set(normalized_answer)
        unknown_ids = sorted(selected_ids - valid_ids)
        if not unknown_ids:
            return []
        return [
            f"option IDs outside question {response.question_id}: {unknown_ids}"
        ]

    @staticmethod
    def _dropdown_ownership_errors(question, normalized_answer):
        subquestions = list(question.sub_questions.all())
        by_blank = {subquestion.blank_number: subquestion for subquestion in subquestions}
        by_id = {subquestion.id: subquestion for subquestion in subquestions}
        errors = []

        for raw_position, option_id in normalized_answer.items():
            position = int(raw_position)
            blank_match = by_blank.get(position)
            id_match = by_id.get(position)
            if blank_match and id_match and blank_match.pk != id_match.pk:
                errors.append(
                    f"position {position} ambiguously matches a blank and subquestion"
                )
                continue

            subquestion = blank_match or id_match
            if not subquestion:
                errors.append(f"unknown blank or subquestion {position}")
                continue

            valid_ids = {option.id for option in subquestion.options.all()}
            if option_id not in valid_ids:
                errors.append(
                    f"option {option_id} does not belong to blank {position}"
                )
        return errors

    @staticmethod
    def _evaluation_score(result):
        scores = (result or {}).get("evaluation", {}).get("scores", {})
        return sum(
            float(payload.get("score", 0) or 0)
            for payload in scores.values()
            if isinstance(payload, dict)
        )

    def _report(self, candidates):
        changed_scores = sum(
            candidate["old_score"] != candidate["new_score"]
            for candidate in candidates
        )
        self.stdout.write("JSON-encoded rule response repair")
        self.stdout.write("=================================")
        self.stdout.write(f"Eligible responses: {len(candidates)}")
        self.stdout.write(f"Score-changing responses: {changed_scores}")
        for candidate in candidates:
            response = candidate["response"]
            self.stdout.write(
                f"model={response.__class__.__name__} | response={response.pk} | "
                f"question={response.question_id} | "
                f"subsection={response.question.subsection.name} | "
                f"normalized={candidate['answer_data']} | "
                f"old_score={candidate['old_score']:.6g} | "
                f"new_score={candidate['new_score']:.6g}"
            )

    @staticmethod
    def _check_expected_count(candidates, expected_count):
        if len(candidates) != expected_count:
            raise CommandError(
                f"Eligible count changed: expected {expected_count}, "
                f"found {len(candidates)}. No changes made."
            )

    def _apply(self, candidates):
        affected_session_ids = set()
        for candidate in candidates:
            response = candidate["response"]
            response.answer_data = candidate["answer_data"]
            response.evaluation_result = candidate["evaluation_result"]
            response.evaluation_status = "completed"
            response.evaluation_stage = "scoring"
            response.evaluation_error = ""
            response.save(update_fields=[
                "answer_data",
                "evaluation_result",
                "evaluation_status",
                "evaluation_stage",
                "evaluation_error",
            ])
            response.apply_skill_scores()
            if isinstance(response, UserResponse):
                affected_session_ids.add(response.user_session_id)

        for session in UserMockTestSession.objects.select_for_update().filter(
            pk__in=affected_session_ids
        ):
            session.aggregate_scores()

        self.stdout.write(
            self.style.SUCCESS(
                f"Repaired {len(candidates)} response(s) and recalculated "
                f"{len(affected_session_ids)} session(s)."
            )
        )
