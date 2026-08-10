import threading
from unittest import skipUnless
from unittest.mock import patch

from django.db.models.deletion import ProtectedError
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SessionQuestion,
    SessionResult,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.evaluation_queue import queue_response_evaluation
from mocktest.services.evaluation_status import can_download_session_pdf
from mocktest.services.pdf_service import build_session_pdf_context
from mocktest.services.session_finalization import (
    create_session_manifest,
    mark_session_question_answered,
    recalculate_session_state,
)


class SessionFinalizationTests(TestCase):
    def setUp(self):
        self.mock_test = MockTest.objects.create(title="Versioned exam")
        self.section = Section.objects.create(name="Reading")
        self.mock_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=self.section,
            order=1,
        )
        self.subsection = SubSection.objects.create(
            section=self.section,
            name="mc_single",
            order=1,
            evaluation_type="rule",
        )
        self.first_question = self._question("Q-1", reading_max=2)
        self.second_question = self._question("Q-2", reading_max=2)
        MockTest.objects.filter(pk=self.mock_test.pk).update(is_active=True)

    def _question(self, name, *, reading_max=1, mock_test_section=None):
        return Question.objects.create(
            mock_test_section=mock_test_section or self.mock_test_section,
            subsection=self.subsection,
            name=name,
            text=f"Prompt for {name}",
            reading_score_max=reading_max,
        )

    def _start(self):
        response = self.client.post(
            "/mocktest/start-test/",
            {
                "name": "Candidate",
                "mocktest_id": str(self.mock_test.pk),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return UserMockTestSession.objects.get(
            session_id=response.json()["session_id"]
        )

    def _submit(self, session, question):
        return self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": question.pk,
                "answer": question.options.first().pk if question.options.exists() else 1,
            },
            content_type="application/json",
        )

    def test_start_creates_immutable_ordered_question_manifest(self):
        session = self._start()

        rows = list(session.question_manifest.order_by("order"))

        self.assertEqual(session.manifest_version, "session-manifest-v1")
        self.assertEqual(session.mock_test_snapshot["title"], "Versioned exam")
        self.assertEqual(session.expected_question_count, 2)
        self.assertEqual([row.question_id_snapshot for row in rows], [
            self.first_question.pk,
            self.second_question.pk,
        ])
        self.assertEqual(rows[0].question_snapshot["text"], "Prompt for Q-1")
        self.assertEqual(rows[0].skill_maxima_snapshot["reading"], 2)

        self.first_question.text = "Changed after session start"
        with self.assertRaises(ValidationError):
            self.first_question.save(update_fields=["text"])
        Question.objects.filter(pk=self.first_question.pk).update(
            text="Forced database mutation",
            reading_score_max=100,
        )

        added_later = self._question("Q-3")
        question_response = self.client.get(
            "/mocktest/get-question/",
            {"session_id": session.session_id},
        )

        rows[0].refresh_from_db()
        self.assertEqual(rows[0].question_snapshot["text"], "Prompt for Q-1")
        self.assertEqual(rows[0].skill_maxima_snapshot["reading"], 2)
        self.assertEqual(question_response.status_code, 200)
        self.assertEqual(question_response.json()["count"], 2)
        self.assertEqual(
            question_response.json()["results"][0]["text"],
            "Prompt for Q-1",
        )
        self.assertNotIn(
            added_later.pk,
            [item["id"] for item in question_response.json()["results"]],
        )

        with self.assertRaises(ProtectedError):
            self.first_question.delete()

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_submitting_last_question_first_does_not_finish_submission(
        self,
        mock_delay,
    ):
        session = self._start()

        response = self._submit(session, self.second_question)
        session.refresh_from_db()

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(session.submission_completed_at)
        self.assertFalse(session.is_completed)
        self.assertEqual(
            list(session.question_manifest.values_list("status", flat=True)),
            ["pending", "answered"],
        )

        response = self._submit(session, self.first_question)
        session.refresh_from_db()

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(session.submission_completed_at)
        self.assertFalse(session.is_completed)
        self.assertEqual(mock_delay.call_count, 2)

    def test_timer_expiry_resolves_questions_and_finalizes_zero_score(self):
        second_section = Section.objects.create(name="Listening")
        second_mock_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=second_section,
            order=2,
        )
        self._question("Q-3", mock_test_section=second_mock_test_section)
        session = self._start()

        first = self.client.get(
            "/mocktest/question/",
            {"session_id": session.session_id},
            HTTP_TIMER_EXCEEDED="true",
        )
        session.refresh_from_db()

        self.assertEqual(first.status_code, 200)
        self.assertIsNone(session.submission_completed_at)
        self.assertEqual(
            SessionQuestion.objects.filter(
                session=session,
                section_order=1,
                status="timed_out",
            ).count(),
            2,
        )

        second = self.client.get(
            "/mocktest/question/",
            {"session_id": session.session_id},
            HTTP_TIMER_EXCEEDED="true",
        )
        session.refresh_from_db()

        self.assertEqual(second.status_code, 200)
        self.assertTrue(session.is_completed)
        self.assertEqual(session.total_score, 0)


        self.assertEqual(session.finalized_result_version, 1)
        self.assertTrue(can_download_session_pdf(session))

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_finalization_uses_snapshot_maxima_and_versions_score_changes(
        self,
        mock_delay,
    ):
        self.second_question.delete()
        session = self._start()
        response = self._submit(session, self.first_question)
        self.assertEqual(response.status_code, 201)
        saved = UserResponse.objects.get(user_session=session)

        Question.objects.filter(pk=self.first_question.pk).update(
            reading_score_max=100,
        )
        saved.reading_score_awarded = 1
        saved.evaluated = True
        saved.evaluation_status = "completed"
        saved.save(
            update_fields=[
                "reading_score_awarded",
                "evaluated",
                "evaluation_status",
            ]
        )
        session.aggregate_scores()
        session.refresh_from_db()

        self.assertTrue(session.is_completed)
        self.assertEqual(session.total_score, 45)
        self.assertEqual(session.finalized_result_version, 1)
        self.assertEqual(SessionResult.objects.count(), 1)

        saved.reading_score_awarded = 2
        saved.save(update_fields=["reading_score_awarded"])
        session.aggregate_scores()
        session.refresh_from_db()

        self.assertEqual(session.total_score, 90)
        self.assertEqual(session.finalized_result_version, 2)
        self.assertEqual(SessionResult.objects.count(), 2)

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_only_last_completed_evaluation_finalizes_locked_session(
        self,
        mock_delay,
    ):
        session = self._start()
        self._submit(session, self.first_question)
        self._submit(session, self.second_question)
        responses = list(
            UserResponse.objects.filter(user_session=session).order_by("question_id")
        )

        responses[0].evaluated = True
        responses[0].evaluation_status = "completed"
        responses[0].reading_score_awarded = 1
        responses[0].save(
            update_fields=[
                "evaluated",
                "evaluation_status",
                "reading_score_awarded",
            ]
        )
        session.aggregate_scores()
        session.refresh_from_db()

        self.assertFalse(session.is_completed)
        self.assertEqual(SessionResult.objects.count(), 0)

        responses[1].evaluated = True
        responses[1].evaluation_status = "completed"
        responses[1].reading_score_awarded = 1
        responses[1].save(
            update_fields=[
                "evaluated",
                "evaluation_status",
                "reading_score_awarded",
            ]
        )
        session.aggregate_scores()
        session.refresh_from_db()

        self.assertTrue(session.is_completed)
        self.assertEqual(session.total_score, 45)
        self.assertEqual(SessionResult.objects.count(), 1)

        status_response = self.client.get(
            "/mocktest/session-evaluation-status/",
            {
                "session_id": session.session_id,
                "include_responses": "true",
            },
        )
        payload = status_response.json()
        self.assertEqual(payload["expected_questions"], 2)
        self.assertEqual(payload["resolved_questions"], 2)
        self.assertEqual(payload["answered_questions"], 2)
        self.assertEqual(payload["pending_questions"], 0)
        self.assertEqual(payload["finalized_result_version"], 1)
        self.assertTrue(payload["can_download_final_pdf"])

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_retry_immediately_blocks_final_pdf_until_refinalized(self, mock_delay):
        self.second_question.delete()
        session = self._start()
        self._submit(session, self.first_question)
        saved = UserResponse.objects.get(user_session=session)
        saved.evaluated = True
        saved.evaluation_status = "completed"
        saved.save(update_fields=["evaluated", "evaluation_status"])
        session.aggregate_scores()
        session.refresh_from_db()
        self.assertTrue(can_download_session_pdf(session))

        queue_response_evaluation(saved)
        session.refresh_from_db()

        self.assertFalse(session.is_completed)
        self.assertFalse(can_download_session_pdf(session))
        self.assertEqual(session.finalized_result_version, 1)

    @patch("mocktest.tasks.evaluate_user_response.delay")
    def test_finalized_pdf_context_uses_immutable_result_snapshot(self, mock_delay):
        self.second_question.delete()
        session = self._start()
        self._submit(session, self.first_question)
        saved = UserResponse.objects.get(user_session=session)
        saved.answer_data = {"text": "Original answer"}
        saved.reading_score_awarded = 1
        saved.evaluated = True
        saved.evaluation_status = "completed"
        saved.evaluation_result = {
            "ok": True,
            "evaluation": {"scores": {}, "feedback": {}},
        }
        saved.save(
            update_fields=[
                "answer_data",
                "reading_score_awarded",
                "evaluated",
                "evaluation_status",
                "evaluation_result",
            ]
        )
        session.aggregate_scores()
        session.refresh_from_db()
        before = build_session_pdf_context(session)

        Question.objects.filter(pk=self.first_question.pk).update(
            text="Mutated live question",
        )
        MockTest.objects.filter(pk=self.mock_test.pk).update(
            title="Mutated live exam title",
        )
        saved.answer_data = {"text": "Mutated live answer"}
        saved.reading_score_awarded = 2
        saved.save(update_fields=["answer_data", "reading_score_awarded"])
        after = build_session_pdf_context(session)

        self.assertEqual(before, after)
        self.assertEqual(
            after["sections"][0]["subsections"][0]["responses"][0]["question"],
            "Prompt for Q-1",
        )
        self.assertEqual(after["skills"]["reading"], 45)
        self.assertEqual(after["meta"]["result_version"], 1)

    def test_explicit_completion_marks_unanswered_questions_not_reached(self):
        session = self._start()

        response = self.client.post(
            "/mocktest/complete-session/",
            {"session_id": session.session_id},
            content_type="application/json",
        )
        session.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(session.is_completed)
        self.assertEqual(
            session.question_manifest.filter(status="not_reached").count(),
            2,
        )
        self.assertEqual(session.total_score, 0)


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locks")
class SessionFinalizationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_parallel_finalizers_promote_one_consistent_result(self):
        mock_test = MockTest.objects.create(title="Concurrent finalization")
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
        questions = [
            Question.objects.create(
                mock_test_section=mock_test_section,
                subsection=subsection,
                name=f"Q-{number}",
                reading_score_max=1,
            )
            for number in (1, 2)
        ]
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="parallel-finalization",
            mock_test=mock_test,
        )
        create_session_manifest(session.pk)
        for question in questions:
            response = UserResponse.objects.create(
                user_session=session,
                mock_test=mock_test,
                question=question,
                evaluated=False,
                evaluation_status="pending",
            )
            mark_session_question_answered(
                session.pk,
                question.pk,
                response.pk,
            )

        UserResponse.objects.filter(user_session=session).update(
            evaluated=True,
            evaluation_status="completed",
            reading_score_awarded=1,
        )

        barrier = threading.Barrier(2)
        errors = []

        def finalize():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                recalculate_session_state(session.pk)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=finalize) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        session.refresh_from_db()
        self.assertEqual(errors, [])
        self.assertTrue(session.is_completed)
        self.assertEqual(session.total_score, 90)
        self.assertEqual(session.finalized_result_version, 1)
        self.assertEqual(SessionResult.objects.count(), 1)
