from django.core.management.base import BaseCommand, CommandError

from examinor.services.explanation_drafter import draft_question_explanation
from mocktest.models import Question


class Command(BaseCommand):
    help = "Draft and store reusable explanations for Reading questions using OpenAI."

    def add_arguments(self, parser):
        parser.add_argument("--question-id", type=int, action="append")
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--overwrite", action="store_true")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Call OpenAI and save explanations. Without this flag, only list candidates.",
        )

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise CommandError("--limit must be greater than zero.")

        questions = Question.objects.filter(
            subsection__section__name__iexact="Reading",
            subsection__evaluation_type="rule",
        ).select_related("subsection")
        if options["question_id"]:
            questions = questions.filter(pk__in=options["question_id"])
        if not options["overwrite"]:
            questions = questions.filter(
                answer_explanation="",
                answer_explanation_draft="",
            )
        questions = list(questions.order_by("pk")[:options["limit"]])

        self.stdout.write(f"Questions selected: {len(questions)}")
        for question in questions:
            self.stdout.write(
                f"question={question.pk} subsection={question.subsection.name} "
                f"name={question.name or '-'}"
            )

        if not questions:
            self.stdout.write("No explanations need drafting.")
            return
        if not options["confirm"]:
            self.stdout.write("Dry run only. Re-run with --confirm to call OpenAI and save drafts.")
            return

        saved = 0
        failures = []
        for question in questions:
            try:
                question.answer_explanation_draft = draft_question_explanation(question)
                question.save(update_fields=["answer_explanation_draft"])
                saved += 1
                self.stdout.write(self.style.SUCCESS(f"Saved question {question.pk}."))
            except Exception as exc:
                failures.append(f"question={question.pk}: {exc}")
                self.stderr.write(failures[-1])

        self.stdout.write(f"Explanations saved: {saved}")
        self.stdout.write(f"Failures: {len(failures)}")
        if failures:
            raise CommandError("One or more explanation drafts failed.")
