import csv
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from mocktest.models import MockTest
from mocktest.services.question_bank_validation import question_bank_queryset
from mocktest.services.question_maximum_policy import maximum_policy_rows


class Command(BaseCommand):
    help = "Write a read-only task-specific question skill maximum audit."

    def add_arguments(self, parser):
        parser.add_argument("--section")
        parser.add_argument("--subsection")
        parser.add_argument(
            "--mock-test",
            help="Inspect one mock test by UUID or exact title.",
        )
        parser.add_argument(
            "--active",
            action="store_true",
            help="Inspect questions in every active mock test.",
        )
        parser.add_argument(
            "--output",
            default="question_skill_maxima_audit.csv",
        )
        parser.add_argument(
            "--fail-on-error",
            action="store_true",
            help="Return a failing exit code when authoritative mismatches exist.",
        )

    def handle(self, *args, **options):
        if options["mock_test"] and options["active"]:
            raise CommandError("Use --mock-test or --active, not both.")

        mock_test = self._mock_test(options["mock_test"])
        questions = question_bank_queryset(
            section=options["section"],
            subsection=options["subsection"],
            mock_test=mock_test,
        )
        if options["active"]:
            questions = questions.filter(mock_test_section__mock_test__is_active=True)

        rows = []
        question_count = questions.count()
        covered_questions = set()
        review_questions = set()
        for question in questions:
            context = self._context(question)
            policy_rows = maximum_policy_rows(question)
            if any(row["status"] == "review_required" for row in policy_rows):
                review_questions.add(question.pk)
            else:
                covered_questions.add(question.pk)
            rows.extend({**context, **row} for row in policy_rows)

        self._write_report(options["output"], rows)
        statuses = Counter(row["status"] for row in rows)
        error_count = sum(row["severity"] == "error" for row in rows)

        self.stdout.write("Question skill maximum policy audit")
        self.stdout.write("===================================")
        self.stdout.write(f"Questions checked: {question_count}")
        self.stdout.write(f"Policy-covered questions: {len(covered_questions)}")
        self.stdout.write(f"Policy-review questions: {len(review_questions)}")
        self.stdout.write(f"Matching maxima: {statuses['match']}")
        self.stdout.write(f"Authoritative errors: {error_count}")
        self.stdout.write(f"Report: {Path(options['output']).resolve()}")
        self.stdout.write("Read-only audit. No question or score data was changed.")

        if options["fail_on_error"] and error_count:
            raise CommandError("Question skill maximum policy audit found errors.")

    @staticmethod
    def _context(question):
        mock_test = (
            question.mock_test_section.mock_test
            if question.mock_test_section_id
            else None
        )
        subsection = question.subsection
        section = subsection.section if subsection else None
        return {
            "mock_test": mock_test.title if mock_test else "Unassigned",
            "mock_test_id": str(mock_test.pk) if mock_test else "",
            "question_id": question.pk,
            "question_name": question.name or "-",
            "section": section.name if section else "Unassigned",
            "subsection": subsection.name if subsection else "Unassigned",
        }

    @staticmethod
    def _mock_test(identifier):
        if not identifier:
            return None
        try:
            by_id = MockTest.objects.filter(pk=identifier).first()
        except (TypeError, ValueError, ValidationError):
            by_id = None
        if by_id:
            return by_id
        matches = MockTest.objects.filter(title=identifier)
        if matches.count() != 1:
            raise CommandError(
                "--mock-test must match exactly one mock test UUID or title."
            )
        return matches.get()

    @staticmethod
    def _write_report(output, rows):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "status",
            "severity",
            "mock_test",
            "mock_test_id",
            "question_id",
            "question_name",
            "section",
            "subsection",
            "skill",
            "configured_maximum",
            "expected_maximum",
            "delta",
            "basis",
            "manual_action",
        ]
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
