from django.core.management.base import BaseCommand, CommandError

from examinor.services.rule_evaluator import run_rule_evaluation
from mocktest.models import Question


class EmptyAnswer:
    answer_data = {}


class Command(BaseCommand):
    help = "Validate correctness metadata for rule-based questions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--section",
            help="Only inspect one section name, such as Reading.",
        )

    def handle(self, *args, **options):
        questions = Question.objects.filter(
            subsection__evaluation_type="rule",
        ).select_related("subsection__section")

        if options["section"]:
            questions = questions.filter(
                subsection__section__name__iexact=options["section"],
            )

        errors = []
        total = 0
        for question in questions.order_by("pk"):
            total += 1
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

        self.stdout.write("Rule question configuration check")
        self.stdout.write("=================================")
        self.stdout.write(f"Questions checked: {total}")
        self.stdout.write(f"Configuration errors: {len(errors)}")

        for error in errors:
            self.stderr.write(error)

        if errors:
            raise CommandError("Rule question configuration is not healthy.")

        self.stdout.write(self.style.SUCCESS("Rule question configuration looks healthy."))
