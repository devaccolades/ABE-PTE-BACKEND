import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SessionQuestion,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


class UnrecordedSpeakingAnswerTests(TestCase):
    def setUp(self):
        self.mock_test = MockTest.objects.create(title="Speaking exam")
        section = Section.objects.create(name="Speaking")
        mock_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="read_aloud",
            order=1,
            evaluation_type="ai",
        )
        self.first_question, self.second_question = (
            Question.objects.create(
                mock_test_section=mock_test_section,
                subsection=subsection,
                name=name,
                text=f"Read {name} aloud.",
                speaking_score_max=1.5,
            )
            for name in ("RA-1", "RA-2")
        )
        MockTest.objects.filter(pk=self.mock_test.pk).update(is_active=True)
        response = self.client.post(
            "/mocktest/start-test/",
            {"name": "Candidate", "mocktest_id": str(self.mock_test.pk)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.session = UserMockTestSession.objects.get(
            session_id=response.json()["session_id"]
        )

    def _skip(self, question, **extra):
        return self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": self.session.session_id,
                "question_name": question.name,
                "answer": "{}",
                "skipped": "true",
                "skip_reason": "no_recording",
                **extra,
            },
        )

    def _manifest_status(self, question):
        return SessionQuestion.objects.get(
            session=self.session,
            question_id_snapshot=question.pk,
        ).status

    @patch("mocktest.services.evaluation_jobs.chain")
    def test_unrecorded_answer_is_skipped_without_evaluation(self, mock_chain):
        response = self._skip(self.first_question)
        self.session.refresh_from_db()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["skipped"])
        self.assertIsNone(response.json()["session"]["completed_at"])
        self.assertEqual(self._manifest_status(self.first_question), "skipped")
        self.assertEqual(self._manifest_status(self.second_question), "pending")
        self.assertFalse(UserResponse.objects.exists())
        self.assertIsNone(self.session.submission_completed_at)
        mock_chain.assert_not_called()

    def test_skipping_the_last_open_question_completes_submission(self):
        self._skip(self.first_question)
        response = self._skip(self.second_question)
        self.session.refresh_from_db()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.json()["session"]["completed_at"])
        self.assertIsNotNone(self.session.submission_completed_at)
        self.assertTrue(self.session.is_completed)
        self.assertEqual(self.session.total_score, 0)

    def test_saved_answer_is_not_replaced_by_a_skip(self):
        saved = UserResponse.objects.create(
            user_session=self.session,
            question=self.first_question,
            mock_test=self.mock_test,
            answer_data={},
            answer_audio="response/audio/answer.webm",
        )

        response = self._skip(self.first_question)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["response_id"], saved.pk)
        self.assertEqual(self._manifest_status(self.first_question), "pending")

    @patch("mocktest.services.evaluation_jobs.chain")
    def test_recording_is_kept_when_sent_with_the_skip_flag(self, mock_chain):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self._skip(
                    self.first_question,
                    answer_audio=SimpleUploadedFile(
                        "answer.webm",
                        b"recorded audio bytes",
                        content_type="audio/webm",
                    ),
                )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self._manifest_status(self.first_question), "answered")
        mock_chain.return_value.delay.assert_called_once()

    def test_text_questions_cannot_be_skipped(self):
        mock_test = MockTest.objects.create(title="Reading exam")
        section = Section.objects.create(name="Reading")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
            order=1,
            evaluation_type="rule",
        )
        Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="MC-1",
            text="Choose one answer.",
            reading_score_max=1,
        )
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="text-skip-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_name": "MC-1",
                "skipped": "true",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "skip_not_supported")
        self.assertFalse(UserResponse.objects.exists())
