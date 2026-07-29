from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from examinor.services.rule_evaluator import listening_fill_blank_segments
from mocktest.models import Question, SubQuestion


class Command(BaseCommand):
    help = (
        "Create or update ordered answer rows for one Listening Fill in the Blanks "
        "question. The command is a dry run unless --apply is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument("question_id", type=int)
        parser.add_argument(
            "--answer",
            action="append",
            dest="answers",
            required=True,
            help="Correct text for one blank, in order. Repeat for every blank.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the displayed changes.",
        )

    def handle(self, *args, **options):
        question = (
            Question.objects.select_related("subsection")
            .filter(pk=options["question_id"])
            .first()
        )
        if question is None:
            raise CommandError(f"Question {options['question_id']} does not exist.")
        if not question.subsection or question.subsection.name != "l_fill_in_blanks":
            raise CommandError(
                f"Question {question.pk} is not a Listening Fill in the Blanks question."
            )

        segments = listening_fill_blank_segments(question.text)
        blank_count = len(segments) - 1
        answers = [answer.strip() for answer in options["answers"]]

        if blank_count < 1:
            raise CommandError(f"Question {question.pk} has no visible blanks.")
        if any(not answer for answer in answers):
            raise CommandError("Answers cannot be empty.")
        if len(answers) != blank_count:
            raise CommandError(
                f"Question {question.pk} has {blank_count} visible blank(s), but "
                f"{len(answers)} answer(s) were supplied."
            )

        existing_rows = list(
            question.sub_questions.order_by("blank_number", "id")
        )
        existing_numbers = [row.blank_number for row in existing_rows]
        duplicates = sorted(
            number
            for number in set(existing_numbers)
            if existing_numbers.count(number) > 1
        )
        if duplicates:
            raise CommandError(
                "Duplicate existing blank number(s): "
                f"{', '.join(str(number) for number in duplicates)}. "
                "Review these rows in Django admin before applying this repair."
            )

        existing = {row.blank_number: row for row in existing_rows}
        unexpected = sorted(set(existing) - set(range(1, blank_count + 1)))
        if unexpected:
            raise CommandError(
                "Unexpected existing blank number(s): "
                f"{', '.join(str(number) for number in unexpected)}. "
                "Review these rows in Django admin before applying this repair."
            )

        self.stdout.write("Listening Fill in the Blanks configuration")
        self.stdout.write("===========================================")
        self.stdout.write(f"Question: {question.pk}")
        self.stdout.write(f"Visible blanks: {blank_count}")
        for number, answer in enumerate(answers, start=1):
            action = "update" if number in existing else "create"
            self.stdout.write(f"blank={number} action={action} answer={answer}")

        if not options["apply"]:
            self.stdout.write("Dry run only. Re-run with --apply to persist changes.")
            return

        with transaction.atomic():
            for index, answer in enumerate(answers):
                number = index + 1
                SubQuestion.objects.update_or_create(
                    question=question,
                    blank_number=number,
                    defaults={
                        "text_before_blank": segments[index].strip(),
                        "text_after_blank": segments[index + 1].strip(),
                        "correct_answer": answer,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Configured {blank_count} answer(s) for question {question.pk}."
            )
        )
