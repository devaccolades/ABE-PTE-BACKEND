import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from mocktest.models import MockTest, MockTestSection, Question, Section, SubSection


@override_settings(MEDIA_ROOT=None)
class HighlightIncorrectWordKeyPreparationTests(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

        mock_test = MockTest.objects.create(title="HIW Test", is_active=True)
        section = Section.objects.create(name="Listening")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="highlight_incorrect_words",
            rubric={"listening_and_reading": {"max": 2}},
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="HIW-Q1",
            text="The cat sat on the blue mat.",
            audio=SimpleUploadedFile("source.mp3", b"audio-data"),
        )

    @patch(
        "mocktest.management.commands.prepare_highlight_incorrect_word_keys.transcribe_audio"
    )
    def test_report_generation_is_read_only(self, transcribe_audio_mock):
        transcribe_audio_mock.return_value = (
            "The dog sat on the red mat.",
            [],
        )

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "hiw-report.json"
            call_command(
                "prepare_highlight_incorrect_word_keys",
                "--generate-report",
                "--active",
                "--output",
                str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.question.refresh_from_db()
        self.assertFalse(self.question.correct_answer)
        self.assertEqual(report["summary"]["ready_for_review"], 1)
        self.assertFalse(report["questions"][0]["approved"])
        self.assertEqual(
            [item["word"] for item in report["questions"][0]["comparison"]["incorrect_words"]],
            ["cat", "blue"],
        )

    @patch(
        "mocktest.management.commands.prepare_highlight_incorrect_word_keys.transcribe_audio"
    )
    def test_approved_report_requires_count_and_applies_transcript(self, transcribe_audio_mock):
        transcribe_audio_mock.return_value = (
            "The dog sat on the red mat.",
            [],
        )

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "hiw-report.json"
            call_command(
                "prepare_highlight_incorrect_word_keys",
                "--generate-report",
                "--output",
                str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["questions"][0]["approved"] = True
            report_path.write_text(json.dumps(report), encoding="utf-8")

            call_command(
                "prepare_highlight_incorrect_word_keys",
                "--apply-report",
                str(report_path),
                "--confirm",
                "--expected-count",
                "1",
            )

        self.question.refresh_from_db()
        self.assertEqual(
            self.question.correct_answer,
            "The dog sat on the red mat.",
        )

    @patch(
        "mocktest.management.commands.prepare_highlight_incorrect_word_keys.transcribe_audio"
    )
    def test_apply_rejects_unscorable_insertions_atomically(self, transcribe_audio_mock):
        transcribe_audio_mock.return_value = (
            "The small dog sat on the red mat.",
            [],
        )

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "hiw-report.json"
            call_command(
                "prepare_highlight_incorrect_word_keys",
                "--generate-report",
                "--output",
                str(report_path),
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["questions"][0]["comparison"]["scorable"])
            report["questions"][0]["approved"] = True
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(CommandError, "cannot be selected"):
                call_command(
                    "prepare_highlight_incorrect_word_keys",
                    "--apply-report",
                    str(report_path),
                    "--confirm",
                    "--expected-count",
                    "1",
                )

        self.question.refresh_from_db()
        self.assertFalse(self.question.correct_answer)
