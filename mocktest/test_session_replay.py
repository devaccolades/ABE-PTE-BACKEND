import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from mocktest.models import (
    EvaluationJob,
    EvaluationOutbox,
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.session_finalization import (
    create_session_manifest,
    mark_session_question_answered,
)


class ReplayMockTestSessionTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()

        self.mock_test = MockTest.objects.create(title="Replay paper")
        reading = Section.objects.create(name="Reading")
        speaking = Section.objects.create(name="Speaking")
        reading_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=reading,
            order=1,
        )
        speaking_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=speaking,
            order=2,
        )
        single_choice = SubSection.objects.create(
            section=reading,
            name="mc_single",
            order=1,
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
            trait_skill_map={"reading": ["reading"]},
        )
        read_aloud = SubSection.objects.create(
            section=speaking,
            name="read_aloud",
            order=1,
            evaluation_type="ai",
            rubric={"content": {"max": 6}},
            trait_skill_map={"content": ["reading", "speaking"]},
        )
        self.text_question = Question.objects.create(
            mock_test_section=reading_section,
            subsection=single_choice,
            name="Replay text",
            text="Choose one.",
            reading_score_max=1,
        )
        self.correct_option = QuestionOption.objects.create(
            question=self.text_question,
            option_text="Correct",
            is_correct=True,
        )
        self.audio_question = Question.objects.create(
            mock_test_section=speaking_section,
            subsection=read_aloud,
            name="Replay audio",
            text="Read this text.",
            reading_score_max=6,
            speaking_score_max=6,
        )
        MockTest.objects.filter(pk=self.mock_test.pk).update(
            is_active=True,
            scoring_mode="v2",
        )
        self.mock_test.refresh_from_db()

        self.source = UserMockTestSession.objects.create(
            name="Original candidate",
            session_id="source-replay-session",
            mock_test=self.mock_test,
            scoring_mode="shadow",
        )
        create_session_manifest(self.source.pk)
        self.text_response = self._completed_response(
            self.text_question,
            self.correct_option.pk,
        )
        self.audio_response = self._completed_response(
            self.audio_question,
            {},
            audio=SimpleUploadedFile(
                "source-answer.webm",
                b"test-audio-content",
                content_type="audio/webm",
            ),
        )
        mark_session_question_answered(
            self.source.pk,
            self.text_question.pk,
            self.text_response.pk,
        )
        mark_session_question_answered(
            self.source.pk,
            self.audio_question.pk,
            self.audio_response.pk,
        )
        self.source.refresh_from_db()

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def _completed_response(self, question, answer, *, audio=None):
        return UserResponse.objects.create(
            user_session=self.source,
            mock_test=self.mock_test,
            question=question,
            answer_data=answer,
            answer_audio=audio,
            transcribed_audio_data=(
                {"text": "Stored source transcript"} if audio else None
            ),
            evaluated=True,
            evaluation_status="completed",
            evaluation_stage="scoring",
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {"content": {"score": 1, "max": 1}},
                },
            },
        )

    def test_dry_run_validates_inputs_without_creating_data(self):
        output = StringIO()

        call_command(
            "replay_mock_test_session",
            "--source-session",
            str(self.source.pk),
            "--name",
            "QA replay dry run",
            stdout=output,
        )

        self.assertEqual(UserMockTestSession.objects.count(), 1)
        self.assertEqual(UserResponse.objects.count(), 2)
        self.assertEqual(EvaluationJob.objects.count(), 0)
        self.assertIn("Replay scoring mode: v2", output.getvalue())
        self.assertIn("Inputs: audio=1 | text=1", output.getvalue())
        self.assertIn("Evaluation engines: ai=1 | rule=1", output.getvalue())
        self.assertIn("Dry run only", output.getvalue())

    @patch(
        "mocktest.management.commands.replay_mock_test_session."
        "dispatch_prepared_evaluation",
        return_value="evaluation",
    )
    def test_confirm_creates_independent_inputs_and_fresh_jobs(self, dispatch):
        output = StringIO()

        call_command(
            "replay_mock_test_session",
            "--source-session",
            str(self.source.pk),
            "--name",
            "QA replay confirmed",
            "--expected-response-count",
            "2",
            "--expected-audio-count",
            "1",
            "--expected-source-result-version",
            str(self.source.finalized_result_version),
            "--confirm",
            stdout=output,
        )

        target = UserMockTestSession.objects.exclude(pk=self.source.pk).get()
        target_responses = list(target.userresponse_set.order_by("question_id"))
        target_audio = next(
            response
            for response in target_responses
            if response.question_id == self.audio_question.pk
        )
        target_text = next(
            response
            for response in target_responses
            if response.question_id == self.text_question.pk
        )

        self.assertEqual(target.name, "QA replay confirmed")
        self.assertEqual(target.scoring_mode, "v2")
        self.assertFalse(target.is_completed)
        self.assertIsNotNone(target.submission_completed_at)
        self.assertEqual(target.expected_question_count, 2)
        self.assertEqual(
            target.mock_test_snapshot["qa_replay"]["source_session_pk"],
            self.source.pk,
        )
        self.assertEqual(
            list(target.question_manifest.values_list("status", flat=True)),
            ["answered", "answered"],
        )
        self.assertEqual(target_text.answer_data, self.text_response.answer_data)
        self.assertEqual(target_audio.answer_data, self.audio_response.answer_data)
        self.assertIsNone(target_audio.transcribed_audio_data)
        self.assertNotEqual(
            target_audio.answer_audio.name,
            self.audio_response.answer_audio.name,
        )
        with target_audio.answer_audio.storage.open(
            target_audio.answer_audio.name,
            "rb",
        ) as replayed:
            self.assertEqual(replayed.read(), b"test-audio-content")
        self.assertEqual(EvaluationJob.objects.count(), 2)
        self.assertEqual(EvaluationOutbox.objects.count(), 2)
        self.assertEqual(dispatch.call_count, 2)
        self.assertIn("Created QA replay session", output.getvalue())
        self.assertIn("2 dispatched", output.getvalue())

        self.source.refresh_from_db()
        self.assertTrue(self.source.is_completed)
        self.assertEqual(self.source.userresponse_set.count(), 2)

    def test_missing_source_audio_fails_without_creating_session(self):
        self.audio_response.answer_audio.storage.delete(
            self.audio_response.answer_audio.name
        )

        with self.assertRaisesRegex(CommandError, "validation failed"):
            call_command(
                "replay_mock_test_session",
                "--source-session",
                str(self.source.pk),
                "--name",
                "QA replay missing audio",
                stdout=StringIO(),
                stderr=StringIO(),
            )

        self.assertEqual(UserMockTestSession.objects.count(), 1)
        self.assertEqual(EvaluationJob.objects.count(), 0)

    def test_confirmation_count_mismatch_fails_before_creation(self):
        with self.assertRaisesRegex(CommandError, "expectations changed"):
            call_command(
                "replay_mock_test_session",
                "--source-session",
                str(self.source.pk),
                "--name",
                "QA replay wrong count",
                "--expected-response-count",
                "999",
                "--expected-audio-count",
                "1",
                "--expected-source-result-version",
                str(self.source.finalized_result_version),
                "--confirm",
                stdout=StringIO(),
            )

        self.assertEqual(UserMockTestSession.objects.count(), 1)
        self.assertEqual(EvaluationJob.objects.count(), 0)
