from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from examinor.scoring.response_scores import (
    compile_response_score_evidence,
    promoted_skill_values,
    response_scoring_mode,
)
from examinor.scoring.validators import validate_and_normalize_evaluation_result
from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import SingleResponse, UserResponse


ACTIVE_EVALUATION_STATUSES = {"transcribing", "evaluating"}
SKILLS = ("speaking", "writing", "reading", "listening")


class Command(BaseCommand):
    help = (
        "Re-evaluate Highlight Incorrect Words responses from reviewed source "
        "transcripts without calling an AI provider. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--question-id", action="append", type=int)
        parser.add_argument("--session-id")
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--expected-user-count", type=int)
        parser.add_argument("--expected-single-count", type=int)

    def handle(self, *args, **options):
        user_responses = UserResponse.objects.filter(
            question__subsection__name="highlight_incorrect_words",
            question__correct_answer__isnull=False,
        ).exclude(question__correct_answer="").select_related(
            "question__subsection",
            "user_session",
        ).order_by("pk")
        single_responses = SingleResponse.objects.filter(
            question__subsection__name="highlight_incorrect_words",
            question__correct_answer__isnull=False,
        ).exclude(question__correct_answer="").select_related(
            "question__subsection",
        ).order_by("pk")

        if options["question_id"]:
            user_responses = user_responses.filter(question_id__in=options["question_id"])
            single_responses = single_responses.filter(question_id__in=options["question_id"])
        if options["session_id"]:
            user_responses = user_responses.filter(
                user_session__session_id=options["session_id"],
            )
            single_responses = single_responses.none()

        user_responses = list(user_responses)
        single_responses = list(single_responses)
        active = [
            f"{type(response).__name__}:{response.pk}"
            for response in user_responses + single_responses
            if response.evaluation_status in ACTIVE_EVALUATION_STATUSES
        ]
        if active:
            raise CommandError(
                "Active evaluations must finish before repair: " + ", ".join(active[:20])
            )

        evaluated = []
        errors = []
        score_changes = 0
        for response in user_responses + single_responses:
            result = run_rule_evaluation(
                user_answer=response,
                question=response.question,
                subsection=response.question.subsection,
            )
            is_valid, normalized, error = validate_and_normalize_evaluation_result(
                result,
                response.question.subsection.rubric,
            )
            if not is_valid:
                errors.append(
                    f"{type(response).__name__} response={response.pk}: {error}"
                )
                continue
            evidence = compile_response_score_evidence(
                response.question,
                normalized,
                mode=response_scoring_mode(response),
            )
            projected = promoted_skill_values(evidence)
            current = {
                skill: float(getattr(response, f"{skill}_score_awarded") or 0)
                for skill in SKILLS
            }
            changed = any(
                abs(projected[skill] - current[skill]) > 0.000001
                for skill in SKILLS
            )
            score_changes += int(changed)
            evaluated.append((response, normalized, current, projected))
            self.stdout.write(
                f"model={type(response).__name__} | response={response.pk} | "
                f"question={response.question_id} | changed={str(changed).lower()} | "
                f"current={current} | proposed={projected}"
            )

        self.stdout.write("Highlight Incorrect Words response re-evaluation")
        self.stdout.write("================================================")
        self.stdout.write(f"UserResponses: {len(user_responses)}")
        self.stdout.write(f"SingleResponses: {len(single_responses)}")
        self.stdout.write(f"Score-changing responses: {score_changes}")
        self.stdout.write(f"Errors: {len(errors)}")
        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError("No changes made because re-evaluation errors were found.")

        if not options["confirm"]:
            self.stdout.write("Dry run only. No response or session data was changed.")
            return
        if options["expected_user_count"] != len(user_responses):
            raise CommandError(
                f"UserResponse count is {len(user_responses)}, not "
                f"--expected-user-count {options['expected_user_count']}."
            )
        if options["expected_single_count"] != len(single_responses):
            raise CommandError(
                f"SingleResponse count is {len(single_responses)}, not "
                f"--expected-single-count {options['expected_single_count']}."
            )

        affected_sessions = set()
        with transaction.atomic():
            for response, normalized, _current, _projected in evaluated:
                response.evaluation_result = normalized
                response.evaluated = True
                response.evaluation_status = "completed"
                response.evaluation_stage = "scoring"
                response.evaluation_error = ""
                response.save(update_fields=[
                    "evaluation_result",
                    "evaluated",
                    "evaluation_status",
                    "evaluation_stage",
                    "evaluation_error",
                ])
                response.apply_skill_scores()
                if isinstance(response, UserResponse):
                    affected_sessions.add(response.user_session_id)

            from mocktest.models import UserMockTestSession

            for session in UserMockTestSession.objects.filter(pk__in=affected_sessions):
                session.aggregate_scores()

        self.stdout.write(self.style.SUCCESS(
            f"Re-evaluated {len(user_responses)} UserResponse(s), "
            f"{len(single_responses)} SingleResponse(s), and "
            f"{len(affected_sessions)} session(s). No AI provider was called."
        ))
