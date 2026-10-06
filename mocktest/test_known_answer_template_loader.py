from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from mocktest.models import AnswerTemplate
from mocktest.services.known_answer_template_catalog import (
    EXPERT_ANSWER_TEMPLATES,
)


class KnownAnswerTemplateLoaderTests(TestCase):
    def test_dry_run_does_not_create_templates(self):
        output = StringIO()

        call_command(
            "load_known_answer_templates",
            stdout=output,
        )

        self.assertEqual(AnswerTemplate.objects.count(), 0)
        self.assertIn("Dry run only", output.getvalue())

    def test_confirm_loads_catalog_idempotently(self):
        call_command(
            "load_known_answer_templates",
            "--confirm",
            "--expected-count",
            str(len(EXPERT_ANSWER_TEMPLATES)),
            stdout=StringIO(),
        )
        call_command(
            "load_known_answer_templates",
            "--confirm",
            "--expected-count",
            str(len(EXPERT_ANSWER_TEMPLATES)),
            stdout=StringIO(),
        )

        self.assertEqual(
            AnswerTemplate.objects.count(),
            len(EXPERT_ANSWER_TEMPLATES),
        )
        self.assertFalse(
            AnswerTemplate.objects.exclude(
                source="Expert evaluator - Universal templates PTE.docx"
            ).exists()
        )

    def test_expected_count_guard_rejects_catalog_mismatch(self):
        with self.assertRaises(CommandError):
            call_command(
                "load_known_answer_templates",
                "--confirm",
                "--expected-count",
                "99",
                stdout=StringIO(),
            )

        self.assertEqual(AnswerTemplate.objects.count(), 0)
