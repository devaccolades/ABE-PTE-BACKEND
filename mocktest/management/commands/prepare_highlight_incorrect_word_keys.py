import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from examinor.services.highlight_incorrect_words import (
    HighlightIncorrectWordsError,
    compare_displayed_text_to_source,
    ensure_scorable_comparison,
)
from mocktest.models import Question
from mocktest.services.transcription import transcribe_audio


REPORT_VERSION = 1


class Command(BaseCommand):
    help = (
        "Generate and safely apply reviewed source transcripts for Highlight "
        "Incorrect Words questions."
    )

    def add_arguments(self, parser):
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument(
            "--generate-report",
            action="store_true",
            help="Transcribe missing source audio and write a review-only JSON report.",
        )
        action.add_argument(
            "--apply-report",
            help="Apply approved entries from a previously generated JSON report.",
        )
        parser.add_argument("--output", help="Output path for --generate-report.")
        parser.add_argument(
            "--active",
            action="store_true",
            help="Only include questions belonging to active mock tests.",
        )
        parser.add_argument(
            "--question-id",
            action="append",
            type=int,
            help="Limit generation to one or more question IDs.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required when applying an approved report.",
        )
        parser.add_argument(
            "--expected-count",
            type=int,
            help="Required approved-entry count when applying a report.",
        )

    def handle(self, *args, **options):
        if options["generate_report"]:
            return self._generate(options)
        return self._apply(options)

    def _questions(self, options):
        questions = Question.objects.filter(
            subsection__name="highlight_incorrect_words",
        ).select_related(
            "mock_test_section__mock_test",
        ).order_by(
            "mock_test_section__mock_test__title",
            "pk",
        )
        if options["active"]:
            questions = questions.filter(mock_test_section__mock_test__is_active=True)
        if options["question_id"]:
            questions = questions.filter(pk__in=options["question_id"])
        return questions

    def _generate(self, options):
        if not options["output"]:
            raise CommandError("--output is required with --generate-report.")

        questions = list(self._questions(options))
        if not questions:
            raise CommandError("No Highlight Incorrect Words questions matched.")

        entries = []
        transcribed = 0
        ready = 0
        errors = 0
        for question in questions:
            entry = self._base_entry(question)
            try:
                source_transcript = str(question.correct_answer or "").strip()
                if source_transcript:
                    entry["transcript_source"] = "stored_correct_answer"
                else:
                    if not question.audio or not question.audio.name:
                        raise HighlightIncorrectWordsError(
                            "The question has no source audio."
                        )
                    if not question.audio.storage.exists(question.audio.name):
                        raise HighlightIncorrectWordsError(
                            "The configured source audio file does not exist."
                        )
                    source_transcript, _timestamps = transcribe_audio(
                        question.audio.path,
                    )
                    source_transcript = source_transcript.strip()
                    entry["transcript_source"] = "generated_from_audio"
                    transcribed += 1

                comparison = compare_displayed_text_to_source(
                    question.text,
                    source_transcript,
                )
                entry.update({
                    "status": "ready_for_review",
                    "source_transcript": source_transcript,
                    "source_transcript_sha256": self._text_hash(source_transcript),
                    "comparison": comparison.as_dict(),
                })
                ready += 1
            except Exception as exc:
                entry.update({
                    "status": "error",
                    "error": str(exc),
                    "source_transcript": "",
                    "source_transcript_sha256": "",
                    "comparison": None,
                })
                errors += 1
            entries.append(entry)
            self.stdout.write(
                f"question={question.pk} | name={question.name} | status={entry['status']}"
            )

        report = {
            "report_version": REPORT_VERSION,
            "generated_at": timezone.now().isoformat(),
            "review_instructions": (
                "Compare source_transcript with the audio and comparison with the "
                "displayed text. Set approved=true only for reviewed entries."
            ),
            "summary": {
                "questions": len(entries),
                "transcribed": transcribed,
                "ready_for_review": ready,
                "errors": errors,
            },
            "questions": entries,
        }
        output_path = Path(options["output"]).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self.stdout.write("Highlight Incorrect Words key preparation")
        self.stdout.write("=========================================")
        self.stdout.write(f"Questions checked: {len(entries)}")
        self.stdout.write(f"Audio files transcribed: {transcribed}")
        self.stdout.write(f"Ready for review: {ready}")
        self.stdout.write(f"Errors: {errors}")
        self.stdout.write(f"Report: {output_path}")
        self.stdout.write("No question or response data was changed.")

    def _base_entry(self, question):
        mock_test = (
            question.mock_test_section.mock_test
            if question.mock_test_section and question.mock_test_section.mock_test
            else None
        )
        audio_exists = bool(
            question.audio
            and question.audio.name
            and question.audio.storage.exists(question.audio.name)
        )
        return {
            "question_id": question.pk,
            "question_name": question.name or "",
            "mock_test": mock_test.title if mock_test else "Unassigned",
            "mock_test_id": str(mock_test.pk) if mock_test else "",
            "active": bool(mock_test and mock_test.is_active),
            "audio_name": question.audio.name if question.audio else "",
            "audio_sha256": self._file_hash(question.audio) if audio_exists else "",
            "displayed_text": question.text or "",
            "displayed_text_sha256": self._text_hash(question.text or ""),
            "approved": False,
        }

    def _apply(self, options):
        if not options["confirm"]:
            raise CommandError("--confirm is required to apply a reviewed report.")
        if options["expected_count"] is None:
            raise CommandError("--expected-count is required when applying a report.")

        report_path = Path(options["apply_report"]).expanduser().resolve()
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Could not read report: {exc}") from exc
        if report.get("report_version") != REPORT_VERSION:
            raise CommandError("Unsupported or missing report_version.")

        approved = [
            entry
            for entry in report.get("questions", [])
            if entry.get("approved") is True
        ]
        if len(approved) != options["expected_count"]:
            raise CommandError(
                f"Approved entry count is {len(approved)}, not "
                f"--expected-count {options['expected_count']}."
            )
        if not approved:
            raise CommandError("The report contains no approved entries.")

        errors = []
        updates = []
        with transaction.atomic():
            questions = {
                question.pk: question
                for question in Question.objects.select_for_update().filter(
                    pk__in=[entry.get("question_id") for entry in approved],
                ).select_related("subsection")
            }
            for entry in approved:
                question = questions.get(entry.get("question_id"))
                error = self._validate_apply_entry(question, entry)
                if error:
                    errors.append(error)
                    continue
                updates.append((question, entry["source_transcript"].strip()))

            if errors:
                raise CommandError(
                    "No changes made:\n- " + "\n- ".join(errors)
                )

            for question, transcript in updates:
                # This guarded repair intentionally bypasses the normal immutable-
                # session save hook; the reviewed report remains the audit artifact.
                Question.objects.filter(pk=question.pk).update(
                    correct_answer=transcript,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {len(updates)} reviewed HIW source transcript(s)."
            )
        )
        self.stdout.write("No stored responses were re-evaluated.")

    def _validate_apply_entry(self, question, entry):
        question_id = entry.get("question_id")
        if question is None:
            return f"question={question_id}: question does not exist."
        if not question.subsection or question.subsection.name != "highlight_incorrect_words":
            return f"question={question_id}: subsection is not highlight_incorrect_words."
        if self._text_hash(question.text or "") != entry.get("displayed_text_sha256"):
            return f"question={question_id}: displayed text changed after report generation."
        audio_name = question.audio.name if question.audio else ""
        if audio_name != entry.get("audio_name"):
            return f"question={question_id}: audio changed after report generation."
        if not audio_name or not question.audio.storage.exists(audio_name):
            return f"question={question_id}: source audio is missing."
        if self._file_hash(question.audio) != entry.get("audio_sha256"):
            return f"question={question_id}: audio content changed after report generation."

        transcript = str(entry.get("source_transcript") or "").strip()
        if not transcript:
            return f"question={question_id}: approved transcript is empty."
        current = str(question.correct_answer or "").strip()
        if current and current != transcript:
            return f"question={question_id}: correct_answer is already different."
        try:
            comparison = compare_displayed_text_to_source(
                question.text,
                transcript,
            )
            ensure_scorable_comparison(comparison)
        except HighlightIncorrectWordsError as exc:
            return f"question={question_id}: {exc}"
        return ""

    @staticmethod
    def _text_hash(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_hash(field_file):
        if not field_file or not field_file.name:
            return ""
        digest = hashlib.sha256()
        field_file.open("rb")
        try:
            for chunk in field_file.chunks():
                digest.update(chunk)
        finally:
            field_file.close()
        return digest.hexdigest()
