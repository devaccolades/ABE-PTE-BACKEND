import csv
from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from mocktest.models import MockTest
from mocktest.services.question_bank_validation import (
    QuestionBankAuditor,
    question_bank_queryset,
)


class Command(BaseCommand):
    help = "Audit the complete question bank and write a handoff-ready CSV report."

    def add_arguments(self, parser):
        parser.add_argument("--section", help="Only inspect one section name.")
        parser.add_argument("--subsection", help="Only inspect one subsection name.")
        parser.add_argument(
            "--mock-test",
            help="Only inspect one mock test by UUID or exact title.",
        )
        parser.add_argument(
            "--output",
            default="question_bank_audit.csv",
            help="CSV report path (default: question_bank_audit.csv).",
        )
        parser.add_argument(
            "--skip-media-check",
            action="store_true",
            help="Check media field configuration without checking storage.",
        )
        parser.add_argument(
            "--warnings-as-errors",
            action="store_true",
            help="Return a failing exit code when warnings are present.",
        )

    def handle(self, *args, **options):
        mock_test = self._mock_test(options["mock_test"])
        questions = question_bank_queryset(
            section=options["section"],
            subsection=options["subsection"],
            mock_test=mock_test,
        )
        question_count = questions.count()
        issues = QuestionBankAuditor(
            check_storage=not options["skip_media_check"],
        ).audit(questions)

        self._write_report(options["output"], issues)
        counts = Counter(issue["severity"] for issue in issues)
        affected = len(
            {issue["question_id"] for issue in issues if issue["question_id"]}
        )

        self.stdout.write("Question bank audit")
        self.stdout.write("===================")
        self.stdout.write(f"Questions checked: {question_count}")
        self.stdout.write(f"Affected questions: {affected}")
        self.stdout.write(f"Errors: {counts['error']}")
        self.stdout.write(f"Warnings: {counts['warning']}")
        self.stdout.write(f"Report: {Path(options['output']).resolve()}")

        for issue in issues:
            self.stdout.write(
                " | ".join(
                    [
                        issue["severity"].upper(),
                        f"mock_test={issue['mock_test']}",
                        f"question={issue['question_id']} ({issue['question_name']})",
                        f"section={issue['section']}",
                        f"subsection={issue['subsection']}",
                        f"code={issue['code']}",
                        issue["problem"],
                    ]
                )
            )

        should_fail = counts["error"] or (
            options["warnings_as_errors"] and counts["warning"]
        )
        if should_fail:
            raise CommandError("Question bank audit found configuration problems.")

        self.stdout.write(self.style.SUCCESS("Question bank configuration looks healthy."))

    def _mock_test(self, identifier):
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

    def _write_report(self, output, issues):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = [
            "severity",
            "code",
            "mock_test",
            "mock_test_id",
            "question_id",
            "question_name",
            "section",
            "subsection",
            "affected_session_count",
            "affected_sessions",
            "problem",
            "manual_fix",
        ]
        with path.open("w", newline="", encoding="utf-8") as report:
            writer = csv.DictWriter(report, fieldnames=columns)
            writer.writeheader()
            writer.writerows(issues)
