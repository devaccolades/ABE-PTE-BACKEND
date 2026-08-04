import io
import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase


class CollectEvaluationBaselineTests(TestCase):
    def test_stdout_report_is_valid_and_secret_safe(self):
        stdout = io.StringIO()

        call_command("collect_evaluation_baseline", stdout=stdout)

        rendered = stdout.getvalue()
        report = json.loads(rendered)
        self.assertEqual(report["report_version"], 1)
        self.assertTrue(report["database"]["vendor"])
        self.assertTrue(report["database"]["engine"])
        self.assertIn("mocktest_userresponse", report["schema"]["tables"])
        self.assertTrue(report["migration_state"]["disk"])
        self.assertIn("model_drift", report)
        if settings.SECRET_KEY:
            self.assertNotIn(settings.SECRET_KEY, rendered)

        for setting_name in ("OPENAI_API_KEY", "OPENAI_WHISPER_API_KEY"):
            secret = getattr(settings, setting_name, "")
            if secret:
                self.assertNotIn(secret, rendered)

    def test_output_option_writes_report(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "phase0.json"
            call_command(
                "collect_evaluation_baseline",
                output=str(output_path),
                stdout=stdout,
            )

            report = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(report["report_version"], 1)
        self.assertIn("Baseline report written", stdout.getvalue())
