from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mocktest.models import Question, SingleResponse, SubSection, UserResponse
from mocktest.services.question_config import (
    canonical_trait_skill_map,
    expected_question_skill_maxima,
)


class Command(BaseCommand):
    help = (
        "Repair shared question-bank scoring configuration and derive missing "
        "question skill maxima. Dry-run unless --apply is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the reported configuration repairs.",
        )
        parser.add_argument(
            "--rescore-existing",
            action="store_true",
            help=(
                "Reapply stored evaluation scores and aggregate affected sessions. "
                "Does not call OpenAI. Requires --apply."
            ),
        )

    def handle(self, *args, **options):
        if options["rescore_existing"] and not options["apply"]:
            raise CommandError("--rescore-existing requires --apply.")

        subsection_repairs = []
        repaired_maps = {}
        for subsection in SubSection.objects.order_by("pk"):
            trait_map, changed = canonical_trait_skill_map(subsection)
            if changed:
                subsection_repairs.append((subsection, trait_map))
                repaired_maps[subsection.pk] = trait_map

        maximum_repairs = []
        changed_question_ids = set()
        questions = Question.objects.select_related("subsection").order_by("pk")
        for question in questions:
            subsection = question.subsection
            if not subsection:
                continue
            if subsection.pk in repaired_maps:
                subsection.trait_skill_map = repaired_maps[subsection.pk]
                changed_question_ids.add(question.pk)
            for skill, maximum in expected_question_skill_maxima(subsection).items():
                field = f"{skill}_score_max"
                if (getattr(question, field) or 0) <= 0:
                    maximum_repairs.append((question, field, maximum))
                    changed_question_ids.add(question.pk)

        self.stdout.write("Question-bank system configuration repair")
        self.stdout.write("=========================================")
        for subsection, trait_map in subsection_repairs:
            self.stdout.write(
                f"subsection={subsection.pk}:{subsection.name} "
                f"trait_skill_map={trait_map}"
            )
        for question, field, maximum in maximum_repairs:
            self.stdout.write(
                f"question={question.pk} set {field}={maximum:g}"
            )

        user_response_count = UserResponse.objects.filter(
            question_id__in=changed_question_ids,
            evaluated=True,
        ).count()
        single_response_count = SingleResponse.objects.filter(
            question_id__in=changed_question_ids,
            evaluated=True,
        ).count()

        self.stdout.write(f"Shared subsection repairs: {len(subsection_repairs)}")
        self.stdout.write(f"Missing maximum repairs: {len(maximum_repairs)}")
        self.stdout.write(f"Affected questions: {len(changed_question_ids)}")
        self.stdout.write(f"Stored user responses eligible for rescoring: {user_response_count}")
        self.stdout.write(f"Stored single responses eligible for rescoring: {single_response_count}")

        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply to persist repairs.")
            return

        with transaction.atomic():
            for subsection, trait_map in subsection_repairs:
                subsection.trait_skill_map = trait_map
                subsection.save(update_fields=["trait_skill_map"])

            for question, field, maximum in maximum_repairs:
                setattr(question, field, maximum)
                question.save(update_fields=[field])

            rescored_user = 0
            rescored_single = 0
            sessions = set()
            if options["rescore_existing"]:
                user_responses = UserResponse.objects.filter(
                    question_id__in=changed_question_ids,
                    evaluated=True,
                ).select_related("question__subsection", "user_session")
                for response in user_responses:
                    response.apply_skill_scores()
                    sessions.add(response.user_session)
                    rescored_user += 1

                single_responses = SingleResponse.objects.filter(
                    question_id__in=changed_question_ids,
                    evaluated=True,
                ).select_related("question__subsection")
                for response in single_responses:
                    response.apply_skill_scores()
                    rescored_single += 1

                for session in sessions:
                    session.aggregate_scores()

        self.stdout.write(
            self.style.SUCCESS(
                "Repairs applied. "
                f"Rescored {rescored_user} user response(s), "
                f"{rescored_single} single response(s), and "
                f"{len(sessions)} session(s)."
            )
        )
