from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.throttling import ScopedRateThrottle

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SingleResponse,
    SubSection,
    UserMockTestSession,
)


class RequestLimitTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        section = Section.objects.create(name="Speaking")
        self.mock_test = MockTest.objects.create(title="Limits Paper", is_active=False)
        mock_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=section,
            order=1,
        )
        self.audio_question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=SubSection.objects.create(
                section=section,
                name="read_aloud",
                order=1,
                evaluation_type="ai",
                ai_input_type="audio",
            ),
            name="Read Aloud 1",
            text="Prompt",
        )
        self.text_question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=SubSection.objects.create(
                section=section,
                name="write_essay",
                order=2,
                evaluation_type="ai",
                ai_input_type="text",
            ),
            name="Essay 1",
            text="Discuss both views.",
        )
        MockTest.objects.filter(pk=self.mock_test.pk).update(is_active=True)

    def _post_audio(self, audio, **extra):
        return self.client.post(
            "/mocktest/single-response/",
            {"name": "Student", "question_id": self.audio_question.id, "answer_audio": audio},
            **extra,
        )

    def _post_text(self, **extra):
        return self.client.post(
            "/mocktest/single-response/",
            {"name": "Student", "question_id": self.text_question.id, "answer": "An essay."},
            **extra,
        )


@patch("mocktest.views.dispatch_prepared_evaluation")
class AudioUploadLimitTests(RequestLimitTestCase):
    @override_settings(AUDIO_UPLOAD_MAX_BYTES=4)
    def test_oversized_audio_is_rejected_before_saving(self, mock_dispatch):
        response = self._post_audio(
            SimpleUploadedFile("answer.webm", b"12345", content_type="audio/webm"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "audio_upload_too_large")
        self.assertFalse(SingleResponse.objects.exists())
        mock_dispatch.assert_not_called()

    def test_non_audio_upload_is_rejected_before_saving(self, mock_dispatch):
        response = self._post_audio(
            SimpleUploadedFile("answer.pdf", b"%PDF-1.7", content_type="application/pdf"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "audio_upload_invalid_type")
        self.assertFalse(SingleResponse.objects.exists())
        mock_dispatch.assert_not_called()

    def test_browser_recording_types_are_accepted(self, mock_dispatch):
        for content_type in ("audio/webm", "video/webm", "audio/mp4", "application/octet-stream"):
            with self.subTest(content_type=content_type):
                response = self._post_audio(
                    SimpleUploadedFile("blob", b"recorded audio", content_type=content_type),
                )

                self.assertEqual(response.status_code, 201)

        self.assertEqual(SingleResponse.objects.count(), 4)


@patch("mocktest.views.dispatch_prepared_evaluation")
class EndpointThrottleTests(RequestLimitTestCase):
    def test_single_practice_is_throttled_per_client(self, mock_dispatch):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"single_practice": "2/hour"}):
            statuses = [self._post_text().status_code for _ in range(3)]

        self.assertEqual(statuses, [201, 201, 429])
        self.assertEqual(SingleResponse.objects.count(), 2)
        self.assertEqual(mock_dispatch.call_count, 2)

    def test_forwarded_for_prefix_cannot_reset_the_limit(self, mock_dispatch):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"single_practice": "1/hour"}):
            first = self._post_text(HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.9")
            spoofed = self._post_text(HTTP_X_FORWARDED_FOR="2.2.2.2, 203.0.113.9")
            other_client = self._post_text(HTTP_X_FORWARDED_FOR="203.0.113.10")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(spoofed.status_code, 429)
        self.assertEqual(other_client.status_code, 201)

    def test_session_start_is_throttled(self, mock_dispatch):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"session_start": "1/hour"}):
            statuses = [
                self.client.post(
                    "/mocktest/start-test/",
                    {"name": "Student", "mocktest_id": self.mock_test.pk},
                ).status_code
                for _ in range(2)
            ]

        self.assertEqual(statuses, [201, 429])
        self.assertEqual(UserMockTestSession.objects.count(), 1)

    def test_answer_submission_and_pdf_are_throttled(self, mock_dispatch):
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="throttled-session",
            mock_test=self.mock_test,
        )
        rates = {"answer_submit": "0/hour", "session_pdf": "0/hour"}
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, rates):
            answer = self.client.post(
                "/mocktest/user-response/",
                {"session_id": session.session_id, "question_id": self.text_question.id},
            )
            pdf = self.client.get(f"/mocktest/sessions/{session.session_id}/pdf/")

        self.assertEqual(answer.status_code, 429)
        self.assertEqual(pdf.status_code, 429)
