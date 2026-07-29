from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from examinor.scoring.validators import validate_and_normalize_evaluation_result
from examinor.services.rule_evaluator import (
    AI_ONLY_SUBSECTIONS,
    RULE_QUESTION_CONFIG,
    run_rule_evaluation,
)
from mocktest.models import UserMockTestSession


class Command(BaseCommand):
    help = (
        "Re-evaluate a session's rule-based responses from stored answers. "
        "Runs as a dry run unless --confirm is supplied."
    )

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--session-pk", type=int)
        target.add_argument("--session-id")
        parser.add_argument(
            "--section",
            default="Reading",
            help="Section name to re-evaluate (default: Reading).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Persist new evaluations and aggregate the session scores.",
        )

    def handle(self, *args, **options):
        session = self._get_session(options)
        responses = list(
            session.userresponse_set.filter(
                question__subsection__section__name__iexact=options["section"],
            ).filter(
                Q(question__subsection__evaluation_type="rule")
                | Q(question__subsection__name__in=RULE_QUESTION_CONFIG)
            ).exclude(
                question__subsection__name__in=AI_ONLY_SUBSECTIONS,
            ).select_related("question__subsection__section")
        )

        if not responses:
            raise CommandError(
                f"No rule-based {options['section']} responses found for session {session.pk}."
            )

        evaluated = []
        errors = []
        for response in responses:
            subsection = response.question.subsection
            result = run_rule_evaluation(
                user_answer=response,
                question=response.question,
                subsection=subsection,
            )
            is_valid, normalized, error = validate_and_normalize_evaluation_result(
                result,
                subsection.rubric,
            )
            if not is_valid:
                errors.append(f"response={response.pk}: {error}")
                continue
            evaluated.append((response, normalized))

        self.stdout.write(f"Session: {session.pk} ({session.session_id})")
        self.stdout.write(f"Section: {options['section']}")
        self.stdout.write(f"Responses found: {len(responses)}")
        self.stdout.write(f"Responses ready: {len(evaluated)}")

        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError("No changes made because one or more evaluations were invalid.")

        if not options["confirm"]:
            self.stdout.write("Dry run only. Re-run with --confirm to persist changes.")
            return

        with transaction.atomic():
            for response, normalized in evaluated:
                response.evaluation_result = normalized
                response.evaluation_status = "completed"
                response.evaluation_stage = "scoring"
                response.evaluation_error = ""
                response.save(
                    update_fields=[
                        "evaluation_result",
                        "evaluation_status",
                        "evaluation_stage",
                        "evaluation_error",
                    ]
                )
                response.apply_skill_scores()

            session.aggregate_scores()

        self.stdout.write(
            self.style.SUCCESS(
                f"Re-evaluated {len(evaluated)} responses and recalculated session {session.pk}."
            )
        )

    def _get_session(self, options):
        lookup = (
            {"pk": options["session_pk"]}
            if options["session_pk"] is not None
            else {"session_id": options["session_id"]}
        )
        try:
            return UserMockTestSession.objects.get(**lookup)
        except UserMockTestSession.DoesNotExist as exc:
            raise CommandError("Session not found.") from exc
