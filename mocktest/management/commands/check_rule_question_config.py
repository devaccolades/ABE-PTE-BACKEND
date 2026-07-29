from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from examinor.services.rule_evaluator import (
    AI_ONLY_SUBSECTIONS,
    RULE_QUESTION_CONFIG,
    run_rule_evaluation,
)
from mocktest.models import Question


class EmptyAnswer:
    answer_data = {}


class Command(BaseCommand):
    help = "Validate correctness metadata for deterministic questions and AI references."

    def add_arguments(self, parser):
        parser.add_argument(
            "--section",
            help="Only inspect one section name, such as Reading.",
        )
        parser.add_argument(
            "--subsection",
            help="Only inspect one subsection name, such as l_fill_in_blanks.",
        )

    def handle(self, *args, **options):
        questions = Question.objects.filter(
            (
                Q(subsection__evaluation_type="rule")
                & ~Q(subsection__name__in=AI_ONLY_SUBSECTIONS)
            )
            | Q(subsection__name__in=RULE_QUESTION_CONFIG)
            | Q(subsection__name="summarize_spoken_text"),
        ).select_related("subsection__section").distinct()

        if options["section"]:
            questions = questions.filter(
                subsection__section__name__iexact=options["section"],
            )
        if options["subsection"]:
            questions = questions.filter(
                subsection__name__iexact=options["subsection"],
            )

        errors = []
        total = 0
        for question in questions.order_by("pk"):
            total += 1
            if question.subsection.name == "summarize_spoken_text":
                if not question.correct_answer:
                    errors.append(
                        f"question={question.pk} subsection=summarize_spoken_text: "
                        "Missing reference transcript, model answer, or key points "
                        "in question.correct_answer."
                    )
                continue

            result = run_rule_evaluation(
                user_answer=EmptyAnswer(),
                question=question,
                subsection=question.subsection,
            )
            if not result.get("ok", False):
                errors.append(
                    f"question={question.pk} subsection={question.subsection.name}: "
                    f"{result.get('error', 'Invalid rule configuration')}"
                )

        self.stdout.write("Question evaluation configuration check")
        self.stdout.write("=======================================")
        self.stdout.write(f"Questions checked: {total}")
        self.stdout.write(f"Configuration errors: {len(errors)}")

        for error in errors:
            self.stderr.write(error)

        if errors:
            raise CommandError("Question evaluation configuration is not healthy.")

        self.stdout.write(
            self.style.SUCCESS("Question evaluation configuration looks healthy.")
        )
