from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from mocktest.models import (
    EvaluationJob,
    EvaluationOutbox,
    MockTest,
    MockTestSection,
    Question,
    Section,
    SingleResponse,
    SubSection,
)


class SinglePracticeQuestionListTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Speaking")
        self.subsection = SubSection.objects.create(
            section=self.section,
            name="read_aloud",
            order=1,
            evaluation_type="ai",
            ai_input_type="audio",
        )

    def _mock_test(self, title, *, active=True, question_count=1):
        mock_test = MockTest.objects.create(title=title, is_active=False)
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=self.section,
            order=1,
        )
        for number in range(question_count):
            Question.objects.create(
                mock_test_section=mock_test_section,
                subsection=self.subsection,
                name=f"{title} Read Aloud {number + 1}",
                text=f"Prompt {number + 1}",
            )
        if active:
            MockTest.objects.filter(pk=mock_test.pk).update(is_active=True)
        return mock_test

    def test_questions_are_grouped_by_active_mock_test_without_ten_item_limit(self):
        alpha = self._mock_test("Alpha Paper", question_count=11)
        beta = self._mock_test("Beta Paper", question_count=2)
        self._mock_test("Draft Paper", active=False, question_count=3)

        response = self.client.get("/mocktest/all_questions/read_aloud/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mock_test_count"], 2)
        self.assertEqual(payload["question_count"], 13)
        self.assertEqual(
            [item["title"] for item in payload["mock_tests"]],
            ["Alpha Paper", "Beta Paper"],
        )
        self.assertEqual(payload["mock_tests"][0]["id"], str(alpha.pk))
        self.assertEqual(payload["mock_tests"][0]["question_count"], 11)
        self.assertEqual(payload["mock_tests"][1]["id"], str(beta.pk))
        self.assertEqual(len(payload["mock_tests"][1]["questions"]), 2)

    def test_invalid_subsection_returns_not_found(self):
        response = self.client.get("/mocktest/all_questions/not-a-subsection/")

        self.assertEqual(response.status_code, 404)


class SinglePracticeEvaluationStatusTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Writing")
        self.subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
            evaluation_type="ai",
            ai_input_type="text",
        )
        mock_test = MockTest.objects.create(title="Practice Paper")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=self.subsection,
            name="Practice essay",
            text="Write about public transport.",
        )

    def _tracked_response(self, *, job_status="completed", response_status="completed"):
        response = SingleResponse.objects.create(
            name="Candidate",
            question=self.question,
            answer_data="Public transport should be improved.",
            evaluated=response_status == "completed",
            evaluation_status=response_status,
            evaluation_stage="evaluation",
            evaluation_result={
                "ok": True,
                "evaluation": {
                    "scores": {
                        "content": {"score": 2, "max": 3},
                    },
                    "weighted_score": 2,
                    "max_score": 3,
                    "feedback": {
                        "summary": "The response addresses the topic clearly.",
                        "strengths": "The main position is easy to identify.",
                        "improvements": "Add a concrete supporting example.",
                        "details": [
                            {
                                "label": "Development",
                                "status": "needs_work",
                                "selected": "General support",
                                "correct": "A specific example",
                            }
                        ],
                        "errors": [
                            {
                                "type": "grammar",
                                "text": "should improved",
                                "suggestion": "should be improved",
                                "explanation": "The passive form needs be.",
                            }
                        ],
                        "explanation": "A stronger example would improve development.",
                    },
                },
            },
            transcribed_audio_data={"transcription": {"text": "Spoken answer"}},
        )
        job = EvaluationJob.objects.create(
            response_type="single",
            response_id=response.pk,
            question_id=self.question.pk,
            input_hash="a" * 64,
            engine_version="test-engine",
            status=job_status,
            input_snapshot={},
        )
        event = EvaluationOutbox.objects.create(
            job=job,
            published_at=timezone.now(),
        )
        return response, job, event

    def test_status_returns_feedback_but_no_scores(self):
        saved, _, event = self._tracked_response()

        response = self.client.get(
            f"/mocktest/single-response-status/{event.event_id}/"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response_id"], saved.pk)
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["terminal"])
        self.assertEqual(
            payload["feedback"]["summary"],
            "The response addresses the topic clearly.",
        )
        self.assertEqual(payload["feedback"]["details"][0]["label"], "Development")
        self.assertEqual(payload["feedback"]["errors"][0]["type"], "grammar")
        self.assertEqual(payload["feedback"]["observations"][0]["label"], "Strengths")
        self.assertEqual(payload["transcript"], "Spoken answer")
        self.assertNotIn("scores", str(payload).lower())
        self.assertNotIn("weighted_score", str(payload).lower())

    def test_retrying_job_remains_non_terminal(self):
        _, _, event = self._tracked_response(
            job_status="waiting_retry",
            response_status="failed",
        )

        response = self.client.get(
            f"/mocktest/single-response-status/{event.event_id}/"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "retrying")
        self.assertFalse(payload["terminal"])
        self.assertTrue(payload["retrying"])

    @patch("mocktest.views.dispatch_prepared_evaluation", return_value="evaluation")
    def test_submission_returns_unpredictable_tracking_id(self, dispatch):
        response = self.client.post(
            "/mocktest/single-response/",
            {
                "name": "Candidate",
                "question_id": self.question.pk,
                "answer": "Public transport should be improved.",
            },
        )

        self.assertEqual(response.status_code, 201)
        tracking_id = response.json()["evaluation"]["tracking_id"]
        self.assertEqual(
            str(EvaluationOutbox.objects.get().event_id),
            tracking_id,
        )
        dispatch.assert_called_once()

    def test_unknown_tracking_id_returns_not_found(self):
        response = self.client.get(
            "/mocktest/single-response-status/00000000-0000-0000-0000-000000000000/"
        )

        self.assertEqual(response.status_code, 404)
