from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from mocktest.models import MockTest
from mocktest.services.question_bank_validation import publication_errors


class Command(BaseCommand):
    help = "Check whether one or all active mock tests satisfy the publication contract."

    def add_arguments(self, parser):
        parser.add_argument(
            "identifier",
            nargs="?",
            help="Mock test UUID or exact title. Omit with --active.",
        )
        parser.add_argument(
            "--active",
            action="store_true",
            help="Check every currently active mock test.",
        )
        parser.add_argument(
            "--skip-media-check",
            action="store_true",
            help="Require media fields without checking the storage backend.",
        )

    def handle(self, *args, **options):
        tests = self._tests(options["identifier"], options["active"])
        total_errors = 0

        self.stdout.write("Mock-test publication check")
        self.stdout.write("===========================")
        for mock_test in tests:
            errors = publication_errors(
                mock_test,
                check_storage=not options["skip_media_check"],
            )
            total_errors += len(errors)
            state = "PASS" if not errors else f"FAIL ({len(errors)} errors)"
            self.stdout.write(
                f"mock_test={mock_test.title} | id={mock_test.pk} | {state}"
            )
            for issue in errors:
                question = (
                    f"question={issue['question_id']} ({issue['question_name']}) | "
                    if issue["question_id"]
                    else ""
                )
                self.stdout.write(
                    f"  {question}code={issue['code']} | {issue['problem']}"
                )

        self.stdout.write(f"Mock tests checked: {len(tests)}")
        self.stdout.write(f"Publication errors: {total_errors}")
        if total_errors:
            raise CommandError("Mock-test publication configuration is not healthy.")
        self.stdout.write(self.style.SUCCESS("Mock-test publication configuration is healthy."))

    def _tests(self, identifier, active):
        if bool(identifier) == bool(active):
            raise CommandError("Provide one identifier or use --active.")
        if active:
            return list(MockTest.objects.filter(is_active=True).order_by("title"))

        try:
            by_id = MockTest.objects.filter(pk=identifier).first()
        except (TypeError, ValueError, ValidationError):
            by_id = None
        if by_id:
            return [by_id]
        matches = list(MockTest.objects.filter(title=identifier))
        if len(matches) != 1:
            raise CommandError("Identifier must match exactly one mock test UUID or title.")
        return matches
