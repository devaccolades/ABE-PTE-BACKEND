import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from examinor.scoring.response_scores import (
    compile_response_score_evidence,
    promoted_skill_values,
    response_scoring_mode,
)
from examinor.scoring.task_contracts import PayloadStatus, inspect_answer_payload
from examinor.scoring.validators import validate_and_normalize_evaluation_result
from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import SingleResponse, UserMockTestSession, UserResponse


MULTIPLE_ANSWER_SUBSECTIONS = ("mc_multiple", "l_mc_multiple")


class Command(BaseCommand):
    help = (
        "Recalculate completed multiple-answer responses with exact negative "
        "marking and proportional question-paper maxima. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=("all", "user", "single"),
            default="all",
        )
        parser.add_argument(
            "--mock-test",
            help="Limit the repair to an exact mock-test title or UUID.",
        )
        parser.add_argument(
            "--detail-limit",
            type=int,
            default=100,
            help="Maximum response details to print; use 0 for none.",
        )
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--expected-count", type=int)
        parser.add_argument("--expected-changing-count", type=int)

    def handle(self, *args, **options):
        self._validate_options(options)
        if options["confirm"]:
            with transaction.atomic():
                candidates, skipped_legacy = self._collect(options, lock=True)
                changing = self._report(candidates, skipped_legacy, options)
                self._check_counts(candidates, changing, options)
                self._apply(candidates)
            return

        candidates, skipped_legacy = self._collect(options, lock=False)
        self._report(candidates, skipped_legacy, options)
        self.stdout.write("Dry run only. No response or session scores were changed.")

    @staticmethod
    def _validate_options(options):
        if options["detail_limit"] < 0:
            raise CommandError("--detail-limit cannot be negative.")
        if options["confirm"] and (
            options["expected_count"] is None
            or options["expected_changing_count"] is None
        ):
            raise CommandError(
                "--expected-count and --expected-changing-count are required "
                "with --confirm."
            )
        for name in ("expected_count", "expected_changing_count"):
            value = options[name]
            if value is not None and value < 0:
                raise CommandError(f"--{name.replace('_', '-')} cannot be negative.")

    def _querysets(self, options, *, lock):
        models = []
        if options["model"] in {"all", "user"}:
            models.append(UserResponse)
        if options["model"] in {"all", "single"}:
            models.append(SingleResponse)

        for model in models:
            queryset = model.objects.filter(
                question__subsection__name__in=MULTIPLE_ANSWER_SUBSECTIONS,
                evaluated=True,
                evaluation_status="completed",
            ).order_by("pk")
            mock_test = str(options.get("mock_test") or "").strip()
            if mock_test:
                selector = Q(
                    question__mock_test_section__mock_test__title=mock_test
                )
                try:
                    mock_test_id = uuid.UUID(mock_test)
                except ValueError:
                    pass
                else:
                    selector |= Q(
                        question__mock_test_section__mock_test_id=mock_test_id
                    )
                queryset = queryset.filter(selector)
            if lock:
                queryset = queryset.select_for_update()
            else:
                queryset = queryset.select_related(
                    "question__subsection",
                    "question__mock_test_section__mock_test",
                )
            queryset = queryset.prefetch_related("question__options")
            yield model, queryset

    def _collect(self, options, *, lock):
        candidates = []
        errors = []
        skipped_legacy = 0

        for model, queryset in self._querysets(options, lock=lock):
            for response in queryset:
                mode = response_scoring_mode(response)
                if mode == "legacy":
                    skipped_legacy += 1
                    continue

                question = response.question
                subsection = question.subsection
                inspection = inspect_answer_payload(
                    subsection.name,
                    response.answer_data,
                )
                if inspection.status == PayloadStatus.INVALID:
                    errors.append(
                        f"{model.__name__} response={response.pk} has an invalid "
                        "answer payload."
                    )
                    continue

                selected_ids = set(inspection.normalized or [])
                valid_option_ids = {option.id for option in question.options.all()}
                unknown_ids = sorted(selected_ids - valid_option_ids)
                if unknown_ids:
                    errors.append(
                        f"{model.__name__} response={response.pk} has option IDs "
                        f"outside question {question.pk}: {unknown_ids}"
                    )
                    continue

                result = run_rule_evaluation(
                    user_answer=response,
                    question=question,
                    subsection=subsection,
                )
                valid, normalized, error = validate_and_normalize_evaluation_result(
                    result,
                    subsection.rubric,
                )
                if not valid:
                    errors.append(
                        f"{model.__name__} response={response.pk}: {error}"
                    )
                    continue

                try:
                    evidence = compile_response_score_evidence(
                        question,
                        normalized,
                        mode=mode,
                    )
                    proposed = promoted_skill_values(evidence)
                except (TypeError, ValueError) as exc:
                    errors.append(
                        f"{model.__name__} response={response.pk}: {exc}"
                    )
                    continue

                skill = (
                    "reading" if subsection.name == "mc_multiple" else "listening"
                )
                current_score = float(
                    getattr(response, f"{skill}_score_awarded") or 0
                )
                proposed_score = float(proposed[skill])
                candidates.append(
                    {
                        "response": response,
                        "evaluation_result": normalized,
                        "mode": mode,
                        "skill": skill,
                        "current_score": current_score,
                        "proposed_score": proposed_score,
                        "changes": abs(current_score - proposed_score) > 0.000001,
                    }
                )

        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError("No changes made because response validation failed.")
        return candidates, skipped_legacy

    def _report(self, candidates, skipped_legacy, options):
        changing = sum(candidate["changes"] for candidate in candidates)
        self.stdout.write("Multiple-answer proportional scoring repair")
        self.stdout.write("===========================================")
        self.stdout.write(f"Eligible responses: {len(candidates)}")
        self.stdout.write(f"Score-changing responses: {changing}")
        self.stdout.write(f"Explicit legacy responses skipped: {skipped_legacy}")

        for candidate in candidates[: options["detail_limit"]]:
            response = candidate["response"]
            answer_scoring = candidate["evaluation_result"]["evaluation"].get(
                "answer_scoring",
                {},
            )
            self.stdout.write(
                f"model={response.__class__.__name__} | response={response.pk} | "
                f"question={response.question_id} | mode={candidate['mode']} | "
                f"raw={answer_scoring.get('raw_points', 0)}/"
                f"{answer_scoring.get('maximum_raw_points', 0)} | "
                f"skill={candidate['skill']} | "
                f"old={candidate['current_score']:.6g} | "
                f"new={candidate['proposed_score']:.6g}"
            )
        hidden = len(candidates) - options["detail_limit"]
        if options["detail_limit"] and hidden > 0:
            self.stdout.write(f"... {hidden} additional response(s) omitted.")
        return changing

    @staticmethod
    def _check_counts(candidates, changing, options):
        if len(candidates) != options["expected_count"]:
            raise CommandError(
                f"Eligible count changed: expected {options['expected_count']}, "
                f"found {len(candidates)}. No changes made."
            )
        if changing != options["expected_changing_count"]:
            raise CommandError(
                "Score-changing count changed: expected "
                f"{options['expected_changing_count']}, found {changing}. "
                "No changes made."
            )

    def _apply(self, candidates):
        affected_session_ids = set()
        for candidate in candidates:
            response = candidate["response"]
            response.evaluation_result = candidate["evaluation_result"]
            response.evaluation_stage = "scoring"
            response.evaluation_error = ""
            response.save(
                update_fields=[
                    "evaluation_result",
                    "evaluation_stage",
                    "evaluation_error",
                ]
            )
            response.apply_skill_scores()
            if isinstance(response, UserResponse):
                affected_session_ids.add(response.user_session_id)

        for session in UserMockTestSession.objects.select_for_update().filter(
            pk__in=affected_session_ids
        ):
            session.aggregate_scores()

        self.stdout.write(
            self.style.SUCCESS(
                f"Recalculated {len(candidates)} response(s) and "
                f"{len(affected_session_ids)} session(s). No AI provider was called."
            )
        )
