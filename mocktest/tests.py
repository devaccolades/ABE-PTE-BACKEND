from io import StringIO
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubSection,
    SubQuestion,
    UserMockTestSession,
    UserResponse,
    SingleResponse,
)
from mocktest.services.pdf_service import build_session_pdf_context
from mocktest.serializers import QuestionSerializer
from mocktest.services.evaluation_queue import (
    EvaluationInputUnavailable,
    EvaluationQueueUnavailable,
    queue_response_evaluation,
)
from mocktest.tasks import evaluate_user_response, recover_stale_evaluations


class SessionPdfContextTests(TestCase):
    def test_context_and_template_include_sections_subsections_and_questions(self):
        mock_test = MockTest.objects.create(title="PTE Mock Test")
        section = Section.objects.create(name="Speaking")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="read_aloud",
            order=1,
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="RA-1",
            text="Read this sentence aloud.",
            speaking_score_max=6,
        )
        session = UserMockTestSession.objects.create(
            name="Student One",
            session_id="session-1",
            mock_test=mock_test,
            speaking_score_awarded=6,
            total_score=6,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "Read aloud answer"},
            speaking_score_awarded=6,
            evaluation_result={
                "evaluation": {
                    "scores": {"fluency": {"score": 3}, "content": {"score": 3}},
                    "feedback": {"fluency": "Good pace."},
                }
            },
            evaluated=True,
        )

        context = build_session_pdf_context(session)

        self.assertEqual(context["sections"][0]["title"], "Speaking")
        self.assertEqual(
            context["sections"][0]["subsections"][0]["title"],
            "Read Aloud",
        )
        self.assertEqual(
            context["sections"][0]["subsections"][0]["responses"][0]["question"],
            "Read this sentence aloud.",
        )

        html = render_to_string("pdf/session_report.html", context)

        self.assertIn("Speaking", html)
        self.assertIn("Read Aloud", html)
        self.assertIn("Read this sentence aloud.", html)
        self.assertIn("Read aloud answer", html)
        self.assertIn("Speaking: 6.0", html)
        self.assertIn("Writing: 0.0", html)
        self.assertIn("Reading: 0.0", html)
        self.assertIn("Listening: 0.0", html)
        self.assertIn("Fluency: 3", html)
        self.assertIn("Good pace.", html)
        self.assertIn("Score:</strong> 6.00 /\n                    6.00", html)

    def test_skill_cards_are_normalized_to_ninety(self):
        mock_test = MockTest.objects.create(title="PTE Mock Test")
        section = Section.objects.create(name="Reading")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            reading_score_max=4,
        )
        session = UserMockTestSession.objects.create(
            name="Reader",
            session_id="normalized-reading-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            reading_score_awarded=2,
            evaluated=True,
            evaluation_status="completed",
        )

        context = build_session_pdf_context(session)

        self.assertEqual(context["skills"]["reading"], 45.0)


    def test_context_and_template_show_incomplete_evaluation_warning(self):
        mock_test = MockTest.objects.create(title="PTE Mock Test")
        section = Section.objects.create(name="Writing")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="WE-1",
            text="Write an essay.",
        )
        session = UserMockTestSession.objects.create(
            name="Student Two",
            session_id="session-2",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "Essay answer"},
            evaluated=False,
            evaluation_status="failed",
            evaluation_stage="scoring",
            evaluation_error="Evaluation returned no score data.",
        )

        context = build_session_pdf_context(session)

        self.assertFalse(context["evaluation_summary"]["is_complete"])
        self.assertEqual(context["evaluation_summary"]["failed"], 1)

        html = render_to_string("pdf/session_report.html", context)

        self.assertIn("Evaluation incomplete.", html)
        self.assertIn("Failed: 1", html)
        self.assertIn("Evaluation returned no score data.", html)

    def test_context_and_template_show_duplicate_response_warning(self):
        mock_test = MockTest.objects.create(title="PTE Mock Test")
        section = Section.objects.create(name="Writing")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="WE-1",
            text="Write an essay.",
        )
        session = UserMockTestSession.objects.create(
            name="Student Duplicate",
            session_id="duplicate-pdf-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "First answer"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "Second answer"},
            evaluated=True,
            evaluation_status="completed",
        )

        context = build_session_pdf_context(session)

        self.assertEqual(context["evaluation_summary"]["duplicate_groups"], 1)
        self.assertEqual(context["evaluation_summary"]["duplicate_rows"], 1)
        responses = context["sections"][0]["subsections"][0]["responses"]
        self.assertTrue(all(response["is_duplicate"] for response in responses))

        html = render_to_string("pdf/session_report.html", context)

        self.assertIn("Duplicate responses detected.", html)
        self.assertIn("Duplicate response row.", html)
        self.assertIn("Duplicate count for this question: 2", html)


class PublicQuestionSerializerTests(TestCase):
    def test_correctness_metadata_is_not_exposed(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(section=section, name="fib_dropdown")
        question = Question.objects.create(subsection=subsection, correct_answer="secret")
        blank = SubQuestion.objects.create(
            question=question,
            blank_number=1,
            correct_answer="hidden answer",
        )
        QuestionOption.objects.create(
            sub_question=blank,
            option_text="Option",
            is_correct=True,
            order_position=1,
        )

        data = QuestionSerializer(question).data
        option = data["sub_questions"][0]["options"][0]

        self.assertNotIn("correct_answer", data["sub_questions"][0])
        self.assertNotIn("is_correct", option)
        self.assertNotIn("order_position", option)
        self.assertEqual(set(option), {"id", "option_text"})


class ReevaluateRuleResponsesCommandTests(TestCase):
    def test_dry_run_then_confirm_recalculates_stored_answer(self):
        mock_test = MockTest.objects.create(title="PTE Mock Test")
        section = Section.objects.create(name="Reading")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
            trait_skill_map={"reading": ["reading"]},
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            reading_score_max=1,
        )
        correct = QuestionOption.objects.create(
            question=question,
            option_text="Correct",
            is_correct=True,
        )
        session = UserMockTestSession.objects.create(
            name="Reader",
            session_id="rule-repair-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data=correct.id,
            evaluated=True,
            evaluation_status="completed",
        )

        stdout = StringIO()
        call_command(
            "reevaluate_rule_responses",
            "--session-pk",
            str(session.pk),
            stdout=stdout,
        )
        response.refresh_from_db()
        self.assertEqual(response.reading_score_awarded, 0)
        self.assertIn("Dry run only", stdout.getvalue())

        call_command(
            "reevaluate_rule_responses",
            "--session-pk",
            str(session.pk),
            "--confirm",
        )
        response.refresh_from_db()
        session.refresh_from_db()

        self.assertEqual(response.reading_score_awarded, 1)
        self.assertEqual(session.reading_score_awarded, 1)
        self.assertEqual(session.total_score, 90)


class RuleQuestionConfigCommandTests(TestCase):
    def test_reports_invalid_drag_drop_configuration(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section,
            name="fib_drag_drop",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
        )
        question = Question.objects.create(subsection=subsection)
        QuestionOption.objects.create(
            question=question,
            option_text="Ambiguous option",
            order_position=1,
        )

        with self.assertRaises(CommandError):
            call_command("check_rule_question_config", "--section", "Reading")

    def test_accepts_valid_single_choice_configuration(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
            evaluation_type="rule",
            rubric={"reading": {"max": 1}},
        )
        question = Question.objects.create(subsection=subsection)
        QuestionOption.objects.create(
            question=question,
            option_text="Correct",
            is_correct=True,
        )
        stdout = StringIO()

        call_command(
            "check_rule_question_config",
            "--section",
            "Reading",
            stdout=stdout,
        )

        self.assertIn("looks healthy", stdout.getvalue())


class UserResponseSubmissionTests(TestCase):
    def _create_question_set(self, mock_test, section_name, question_name):
        section = Section.objects.create(name=section_name)
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
        )
        return Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name=question_name,
            text=f"{section_name} question",
        )

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_question_lookup_is_scoped_to_session_mock_test(self, mock_delay):
        first_mock_test = MockTest.objects.create(title="First")
        second_mock_test = MockTest.objects.create(title="Second")
        first_question = self._create_question_set(first_mock_test, "Writing", "Q-1")
        self._create_question_set(second_mock_test, "Other Writing", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="scoped-session",
            mock_test=first_mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_name": "Q-1",
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["evaluation"]["queued"])
        self.assertEqual(response.json()["evaluation"]["status"], "pending")
        saved = UserResponse.objects.get()
        self.assertEqual(saved.question_id, first_question.id)
        mock_delay.assert_called_once_with(saved.id, first_question.id)

    @patch(
        "mocktest.services.evaluation_queue.evaluate_user_response.delay",
        side_effect=ConnectionError("Redis unavailable"),
    )
    def test_user_response_is_preserved_when_queue_is_unavailable(self, mock_delay):
        mock_test = MockTest.objects.create(title="Queue Failure Test")
        question = self._create_question_set(mock_test, "Writing", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="queue-failure-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": question.id,
                "answer": {"text": "preserve this answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        evaluation = response.json()["evaluation"]
        self.assertFalse(evaluation["queued"])
        self.assertTrue(evaluation["retryable"])
        self.assertEqual(evaluation["status"], "failed")
        self.assertEqual(evaluation["stage"], "queueing")

        saved = UserResponse.objects.get()
        self.assertEqual(saved.answer_data, {"text": "preserve this answer"})
        self.assertEqual(saved.evaluation_status, "failed")
        self.assertEqual(saved.evaluation_stage, "queueing")
        self.assertIn("Evaluation queue unavailable", saved.evaluation_error)
        mock_delay.assert_called_once_with(saved.id, question.id)

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_duplicate_question_names_in_same_mock_test_are_rejected(self, mock_delay):
        mock_test = MockTest.objects.create(title="Duplicate Test")
        self._create_question_set(mock_test, "Writing One", "Q-1")
        self._create_question_set(mock_test, "Writing Two", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_name": "Q-1",
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(UserResponse.objects.exists())
        mock_delay.assert_not_called()

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_can_submit_by_question_id_when_names_duplicate(self, mock_delay):
        mock_test = MockTest.objects.create(title="Duplicate Test")
        first_question = self._create_question_set(mock_test, "Writing One", "Q-1")
        self._create_question_set(mock_test, "Writing Two", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="question-id-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": first_question.id,
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        saved = UserResponse.objects.get()
        self.assertEqual(saved.question_id, first_question.id)
        mock_delay.assert_called_once_with(saved.id, first_question.id)

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_rejects_duplicate_submission_for_same_session_question(self, mock_delay):
        mock_test = MockTest.objects.create(title="Duplicate Submission Test")
        question = self._create_question_set(mock_test, "Writing", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-submission-session",
            mock_test=mock_test,
        )

        first_response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": question.id,
                "answer": {"text": "first answer"},
            },
            content_type="application/json",
        )
        second_response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": question.id,
                "answer": {"text": "second answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(UserResponse.objects.count(), 1)
        self.assertEqual(second_response.json()["response_id"], UserResponse.objects.get().id)
        mock_delay.assert_called_once()

    def test_user_response_declares_session_question_unique_constraint(self):
        constraint = next(
            constraint
            for constraint in UserResponse._meta.constraints
            if constraint.name == "uniq_userresp_session_question"
        )

        self.assertEqual(tuple(constraint.fields), ("user_session", "question"))

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_requires_question_identifier(self, mock_delay):
        mock_test = MockTest.objects.create(title="Missing Question")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="missing-question-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserResponse.objects.exists())
        mock_delay.assert_not_called()

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_rejects_invalid_question_id(self, mock_delay):
        mock_test = MockTest.objects.create(title="Bad Question ID")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="bad-question-id-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": "not-a-number",
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserResponse.objects.exists())
        mock_delay.assert_not_called()

    @patch("mocktest.services.evaluation_queue.evaluate_single_response.delay")
    def test_single_response_rejects_duplicate_question_names_without_id(self, mock_delay):
        first_mock_test = MockTest.objects.create(title="First")
        second_mock_test = MockTest.objects.create(title="Second")
        self._create_question_set(first_mock_test, "Writing One", "Q-1")
        self._create_question_set(second_mock_test, "Writing Two", "Q-1")

        response = self.client.post(
            "/mocktest/single-response/",
            {
                "name": "Student",
                "question_name": "Q-1",
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(SingleResponse.objects.exists())
        mock_delay.assert_not_called()

    @patch("mocktest.services.evaluation_queue.evaluate_single_response.delay")
    def test_single_response_can_submit_by_question_id(self, mock_delay):
        mock_test = MockTest.objects.create(title="Single Test")
        question = self._create_question_set(mock_test, "Writing", "Q-1")

        response = self.client.post(
            "/mocktest/single-response/",
            {
                "name": "Student",
                "question_id": question.id,
                "answer": {"text": "answer"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["evaluation"]["queued"])
        self.assertEqual(response.json()["evaluation"]["status"], "pending")
        saved = SingleResponse.objects.get()
        self.assertEqual(saved.question_id, question.id)
        mock_delay.assert_called_once_with(saved.id, question.id)

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_user_response_requires_audio_file_for_audio_question(self, mock_delay):
        mock_test = MockTest.objects.create(title="Audio Test")
        question = self._create_question_set(mock_test, "Speaking", "RA-1")
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="missing-audio-session",
            mock_test=mock_test,
        )

        response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": question.id,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "audio_upload_required")
        self.assertIn("answer_audio", response.json()["error"])
        self.assertFalse(UserResponse.objects.exists())
        mock_delay.assert_not_called()

    def test_question_api_declares_audio_input_requirement(self):
        mock_test = MockTest.objects.create(title="Audio Contract Test")
        question = self._create_question_set(mock_test, "Speaking", "RA-1")
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="audio-contract-session",
            mock_test=mock_test,
        )

        response = self.client.get(
            "/mocktest/get-question/",
            {"session_id": session.session_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["ai_input_type"], "audio")

    @patch("mocktest.services.evaluation_queue.chain")
    def test_audio_upload_is_stored_and_survives_response_updates(self, mock_chain):
        mock_test = MockTest.objects.create(title="Audio Storage Test")
        question = self._create_question_set(mock_test, "Speaking", "RA-1")
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="audio-storage-session",
            mock_test=mock_test,
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    "/mocktest/user-response/",
                    {
                        "session_id": session.session_id,
                        "question_id": question.id,
                        "answer": "{}",
                        "answer_audio": SimpleUploadedFile(
                            "answer.webm",
                            b"recorded audio bytes",
                            content_type="audio/webm",
                        ),
                    },
                )

                saved = UserResponse.objects.get()
                self.assertEqual(response.status_code, 201)
                self.assertEqual(saved.answer_data, {})
                self.assertTrue(saved.answer_audio.name.startswith("response/audio/"))
                self.assertTrue(saved.answer_audio.storage.exists(saved.answer_audio.name))
                self.assertEqual(saved.answer_audio.read(), b"recorded audio bytes")

                saved.transcribed_audio_data = {"text": "transcribed"}
                saved.evaluation_status = "evaluating"
                saved.save(
                    update_fields=["transcribed_audio_data", "evaluation_status"],
                )
                saved.refresh_from_db()

                self.assertTrue(saved.answer_audio)
                self.assertTrue(saved.answer_audio.storage.exists(saved.answer_audio.name))
                mock_chain.return_value.delay.assert_called_once()

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_final_answer_marks_session_completed(self, mock_delay):
        mock_test = MockTest.objects.create(title="Completion Test")
        first_question = self._create_question_set(mock_test, "Writing One", "Q-1")
        final_question = self._create_question_set(mock_test, "Writing Two", "Q-2")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="completion-session",
            mock_test=mock_test,
        )

        first_response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": first_question.id,
                "answer": {"text": "first"},
            },
            content_type="application/json",
        )
        session.refresh_from_db()
        self.assertEqual(first_response.status_code, 201)
        self.assertFalse(session.is_completed)
        self.assertIsNone(session.completed_at)

        final_response = self.client.post(
            "/mocktest/user-response/",
            {
                "session_id": session.session_id,
                "question_id": final_question.id,
                "answer": {"text": "final"},
            },
            content_type="application/json",
        )

        session.refresh_from_db()
        self.assertEqual(final_response.status_code, 201)
        self.assertTrue(final_response.json()["session"]["is_completed"])
        self.assertTrue(session.is_completed)
        self.assertIsNotNone(session.completed_at)

    def test_complete_session_endpoint_is_idempotent(self):
        mock_test = MockTest.objects.create(title="Completion Endpoint Test")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="completion-endpoint-session",
            mock_test=mock_test,
        )

        first_response = self.client.post(
            "/mocktest/complete-session/",
            {"session_id": session.session_id},
            content_type="application/json",
        )
        session.refresh_from_db()
        completed_at = session.completed_at

        second_response = self.client.post(
            "/mocktest/complete-session/",
            {"session_id": session.session_id},
            content_type="application/json",
        )
        session.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertFalse(first_response.json()["already_completed"])
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()["already_completed"])
        self.assertEqual(session.completed_at, completed_at)

    def test_timer_exit_from_final_section_marks_session_completed(self):
        mock_test = MockTest.objects.create(title="Timer Completion Test")
        question = self._create_question_set(mock_test, "Listening", "Q-1")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="timer-completion-session",
            mock_test=mock_test,
            current_mocktest_section=question.mock_test_section,
        )

        response = self.client.get(
            "/mocktest/question/",
            {"session_id": session.session_id},
            HTTP_TIMER_EXCEEDED="true",
        )

        session.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_completed"])
        self.assertTrue(session.is_completed)
        self.assertIsNotNone(session.completed_at)

    @patch("mocktest.services.evaluation_queue.evaluate_single_response.delay")
    def test_single_response_requires_audio_file_for_audio_question(self, mock_delay):
        mock_test = MockTest.objects.create(title="Single Audio Test")
        question = self._create_question_set(mock_test, "Speaking", "RA-1")
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])

        response = self.client.post(
            "/mocktest/single-response/",
            {"name": "Student", "question_id": question.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "audio_upload_required")
        self.assertIn("answer_audio", response.json()["error"])
        self.assertFalse(SingleResponse.objects.exists())
        mock_delay.assert_not_called()

    def test_session_evaluation_status_reports_progress(self):
        mock_test = MockTest.objects.create(title="Status Test")
        first_question = self._create_question_set(mock_test, "Writing One", "Q-1")
        second_question = self._create_question_set(mock_test, "Writing Two", "Q-2")
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="status-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=first_question,
            answer_data={"text": "answer"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=second_question,
            answer_data={"text": "answer"},
            evaluated=False,
            evaluation_status="failed",
            evaluation_error="OpenAI API timeout",
        )

        response = self.client.get(
            "/mocktest/session-evaluation-status/",
            {"session_id": session.session_id, "include_responses": "true"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_responses"], 2)
        self.assertEqual(data["completed"], 1)
        self.assertEqual(data["failed"], 1)
        self.assertFalse(data["is_complete"])
        self.assertTrue(data["has_failures"])
        self.assertFalse(data["can_download_final_pdf"])
        self.assertEqual(len(data["responses"]), 2)

    def test_session_evaluation_status_requires_session_id(self):
        response = self.client.get("/mocktest/session-evaluation-status/")

        self.assertEqual(response.status_code, 400)


class EvaluationRepairToolTests(TestCase):
    def _create_question(self):
        mock_test = MockTest.objects.create(title="Repair Test")
        section = Section.objects.create(name="Writing")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="write_essay",
            order=1,
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="WE-1",
            text="Write an essay.",
        )
        return mock_test, question

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_queue_helper_requeues_user_response(self, mock_delay):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="repair-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            evaluation_status="failed",
            evaluation_stage="evaluation",
            evaluation_error="Previous failure",
        )

        mode = queue_response_evaluation(response)

        response.refresh_from_db()
        self.assertEqual(mode, "evaluation")
        self.assertEqual(response.evaluation_status, "pending")
        self.assertEqual(response.evaluation_stage, "")
        self.assertEqual(response.evaluation_error, "")
        mock_delay.assert_called_once_with(response.id, question.id)

    @patch("mocktest.services.evaluation_queue.evaluate_single_response.delay")
    def test_queue_helper_requeues_single_response(self, mock_delay):
        _, question = self._create_question()
        response = SingleResponse.objects.create(
            name="Student",
            question=question,
            answer_data={"text": "answer"},
            evaluation_status="failed",
            evaluation_stage="evaluation",
            evaluation_error="Previous failure",
        )

        mode = queue_response_evaluation(response)

        response.refresh_from_db()
        self.assertEqual(mode, "evaluation")
        self.assertEqual(response.evaluation_status, "pending")
        self.assertEqual(response.evaluation_stage, "")
        self.assertEqual(response.evaluation_error, "")
        mock_delay.assert_called_once_with(response.id, question.id)

    @patch(
        "mocktest.services.evaluation_queue.evaluate_user_response.delay",
        side_effect=ConnectionError("Redis unavailable"),
    )
    def test_queue_helper_records_dispatch_failure(self, mock_delay):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="queue-helper-failure-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
        )

        with self.assertRaises(EvaluationQueueUnavailable):
            queue_response_evaluation(response)

        response.refresh_from_db()
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "queueing")
        self.assertIn("Evaluation queue unavailable", response.evaluation_error)
        self.assertEqual(response.evaluation_result["stage"], "queueing")

    @patch("mocktest.services.evaluation_queue.evaluate_user_response.delay")
    def test_queue_helper_rejects_audio_response_without_audio(self, mock_delay):
        mock_test, question = self._create_question()
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="queue-missing-audio-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
        )

        with self.assertRaises(EvaluationInputUnavailable):
            queue_response_evaluation(response)

        response.refresh_from_db()
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "submission")
        self.assertIn("Audio answer file is missing", response.evaluation_error)
        mock_delay.assert_not_called()

    def test_evaluation_task_persists_question_id_mismatch_failure(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="question-mismatch-repair-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
        )

        result = evaluate_user_response.apply(args=(response.id, question.id + 999))

        response.refresh_from_db()
        self.assertTrue(result.failed())
        self.assertIn("does not match", str(result.result))
        self.assertFalse(response.evaluated)
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "evaluation")
        self.assertIn("does not match", response.evaluation_error)

    def test_evaluation_task_persists_invalid_queued_question_id_failure(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="invalid-question-id-repair-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
        )

        result = evaluate_user_response.apply(args=(response.id, "not-a-number"))

        response.refresh_from_db()
        self.assertTrue(result.failed())
        self.assertIn("not a valid integer", str(result.result))
        self.assertFalse(response.evaluated)
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "evaluation")
        self.assertIn("not a valid integer", response.evaluation_error)

    def test_evaluation_task_reports_missing_audio_as_celery_failure(self):
        mock_test, question = self._create_question()
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="task-missing-audio-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
        )

        result = evaluate_user_response.apply(args=(response.id, question.id))

        response.refresh_from_db()
        self.assertTrue(result.failed())
        self.assertIn("Audio answer file is missing", str(result.result))
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "transcription")
        self.assertIn("Audio answer file is missing", response.evaluation_error)

    def test_single_evaluation_task_persists_question_id_mismatch_failure(self):
        _, question = self._create_question()
        response = SingleResponse.objects.create(
            name="Student",
            question=question,
            answer_data={"text": "answer"},
        )

        from mocktest.tasks import evaluate_single_response

        result = evaluate_single_response.apply(args=(response.id, question.id + 999))

        response.refresh_from_db()
        self.assertTrue(result.failed())
        self.assertIn("does not match", str(result.result))
        self.assertFalse(response.evaluated)
        self.assertEqual(response.evaluation_status, "failed")
        self.assertEqual(response.evaluation_stage, "evaluation")
        self.assertIn("does not match", response.evaluation_error)

    def test_inspect_evaluations_supports_single_responses(self):
        _, question = self._create_question()
        SingleResponse.objects.create(
            name="Single Student",
            question=question,
            answer_data={"text": "answer"},
            evaluated=False,
            evaluation_status="failed",
            evaluation_stage="evaluation",
            evaluation_error="OpenAI API timeout",
        )

        stdout = StringIO()
        call_command("inspect_evaluations", "--single", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("Total responses: 1", output)
        self.assertIn("Status failed: 1", output)
        self.assertIn("student=Single Student", output)
        self.assertIn("error=OpenAI API timeout", output)

    def test_inspect_evaluations_filters_by_status_and_age(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="filtered-inspection-session",
            mock_test=mock_test,
        )
        old_failed = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "old failed"},
            evaluated=False,
            evaluation_status="failed",
            evaluation_error="Old failure",
        )
        fresh_failed = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "fresh failed"},
            evaluated=False,
            evaluation_status="failed",
            evaluation_error="Fresh failure",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "old pending"},
            evaluated=False,
            evaluation_status="pending",
        )
        old_time = timezone.now() - timezone.timedelta(hours=2)
        UserResponse.objects.filter(id=old_failed.id).update(
            last_evaluation_attempt_at=old_time,
        )
        UserResponse.objects.filter(id=fresh_failed.id).update(
            last_evaluation_attempt_at=timezone.now(),
        )

        stdout = StringIO()
        call_command(
            "inspect_evaluations",
            "--status",
            "failed",
            "--older-than-minutes",
            "60",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Total responses: 1", output)
        self.assertIn(f"id={old_failed.id}", output)
        self.assertNotIn(f"id={fresh_failed.id}", output)

    @patch("mocktest.management.commands.requeue_pending_evaluations.queue_response_evaluation")
    def test_requeue_command_filters_by_status_and_age(self, mock_queue):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="filtered-requeue-session",
            mock_test=mock_test,
        )
        old_failed = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "old failed"},
            evaluated=False,
            evaluation_status="failed",
        )
        fresh_failed = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "fresh failed"},
            evaluated=False,
            evaluation_status="failed",
        )
        old_pending = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "old pending"},
            evaluated=False,
            evaluation_status="pending",
        )
        old_time = timezone.now() - timezone.timedelta(hours=2)
        UserResponse.objects.filter(id__in=[old_failed.id, old_pending.id]).update(
            last_evaluation_attempt_at=old_time,
        )
        UserResponse.objects.filter(id=fresh_failed.id).update(
            last_evaluation_attempt_at=timezone.now(),
        )

        stdout = StringIO()
        call_command(
            "requeue_pending_evaluations",
            "--status",
            "failed",
            "--older-than-minutes",
            "60",
            stdout=stdout,
        )

        self.assertEqual(mock_queue.call_count, 1)
        self.assertEqual(mock_queue.call_args.args[0].id, old_failed.id)
        self.assertIn("1 responses queued.", stdout.getvalue())

    @patch("mocktest.services.evaluation_queue.queue_response_evaluation")
    def test_recovery_task_only_requeues_stale_active_responses(self, mock_queue):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="stale-recovery-session",
            mock_test=mock_test,
        )
        old_time = timezone.now() - timezone.timedelta(minutes=30)

        stale_evaluating = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            evaluation_status="evaluating",
            last_evaluation_attempt_at=old_time,
        )
        stale_transcribing = SingleResponse.objects.create(
            question=question,
            evaluation_status="transcribing",
            last_evaluation_attempt_at=old_time,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            evaluation_status="evaluating",
            last_evaluation_attempt_at=timezone.now(),
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            evaluation_status="pending",
            last_evaluation_attempt_at=old_time,
        )

        result = recover_stale_evaluations(
            stale_after_minutes=20,
            batch_size=100,
        )

        queued_ids = {call.args[0].id for call in mock_queue.call_args_list}
        self.assertEqual(mock_queue.call_count, 2)
        self.assertEqual(queued_ids, {stale_evaluating.id, stale_transcribing.id})
        self.assertEqual(result["recovered"], 2)
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["queue_failures"], 0)

    def test_inspect_duplicate_responses_reports_duplicate_session_question_pairs(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-history-session",
            mock_test=mock_test,
        )
        first = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "first"},
            evaluated=True,
            evaluation_status="completed",
        )
        second = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "second"},
            evaluated=False,
            evaluation_status="failed",
        )

        stdout = StringIO()
        call_command("inspect_duplicate_responses", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("Duplicate groups: 1", output)
        self.assertIn("Extra duplicate rows: 1", output)
        self.assertIn("session=duplicate-history-session", output)
        self.assertIn(f"recommended_keep_id={first.id}", output)
        self.assertIn(f"candidate_duplicate_ids={second.id}", output)
        self.assertIn(f"id={first.id}", output)
        self.assertIn(f"id={second.id}", output)
        self.assertEqual(UserResponse.objects.count(), 2)

    def test_cleanup_duplicate_responses_dry_run_keeps_rows(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-cleanup-dry-run-session",
            mock_test=mock_test,
        )
        keep = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "keep"},
            evaluated=True,
            evaluation_status="completed",
        )
        delete_candidate = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "delete"},
            evaluated=False,
            evaluation_status="failed",
        )

        stdout = StringIO()
        call_command("cleanup_duplicate_responses", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("Mode: dry-run", output)
        self.assertIn(f"keep_id={keep.id}", output)
        self.assertIn(f"delete_ids={delete_candidate.id}", output)
        self.assertIn("Dry run only. 1 duplicate rows would be deleted.", output)
        self.assertEqual(UserResponse.objects.count(), 2)

    def test_cleanup_duplicate_responses_rejects_invalid_limit(self):
        with self.assertRaises(CommandError):
            call_command("cleanup_duplicate_responses", "--limit", "0")

    def test_cleanup_duplicate_responses_deletes_candidates_when_confirmed(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-cleanup-confirm-session",
            mock_test=mock_test,
        )
        keep = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "keep"},
            evaluated=True,
            evaluation_status="completed",
        )
        delete_candidate = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "delete"},
            evaluated=False,
            evaluation_status="failed",
        )

        stdout = StringIO()
        call_command(
            "cleanup_duplicate_responses",
            "--confirm-delete",
            stdout=stdout,
        )

        self.assertIn("Deleted 1 duplicate rows.", stdout.getvalue())
        self.assertTrue(UserResponse.objects.filter(id=keep.id).exists())
        self.assertFalse(UserResponse.objects.filter(id=delete_candidate.id).exists())

    def test_cleanup_duplicate_responses_can_recalculate_affected_sessions(self):
        mock_test, question = self._create_question()
        question.writing_score_max = 2
        question.save(update_fields=["writing_score_max"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="duplicate-cleanup-recalculate-session",
            mock_test=mock_test,
            total_score=90,
        )
        keep = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "keep"},
            evaluated=True,
            evaluation_status="completed",
            writing_score_awarded=1,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "delete"},
            evaluated=False,
            evaluation_status="failed",
            writing_score_awarded=1,
        )

        stdout = StringIO()
        call_command(
            "cleanup_duplicate_responses",
            "--confirm-delete",
            "--recalculate",
            stdout=stdout,
        )

        session.refresh_from_db()
        self.assertTrue(UserResponse.objects.filter(id=keep.id).exists())
        self.assertEqual(UserResponse.objects.count(), 1)
        self.assertEqual(session.total_score, 45.0)
        self.assertIn("Recalculated 1 affected sessions.", stdout.getvalue())

    def test_recalculate_session_scores_preserves_decimal_total(self):
        mock_test, question = self._create_question()
        question.writing_score_max = 3
        question.save(update_fields=["writing_score_max"])
        question.subsection.trait_skill_map = {"content": ["writing"]}
        question.subsection.save(update_fields=["trait_skill_map"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="decimal-score-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            writing_score_awarded=1,
            evaluated=True,
            evaluation_status="completed",
        )

        call_command("recalculate_session_scores", "--session-id", session.session_id)

        session.refresh_from_db()
        self.assertEqual(session.total_score, 30.0)

    def test_recalculate_session_scores_only_complete_skips_pending_sessions(self):
        mock_test, question = self._create_question()
        complete_session = UserMockTestSession.objects.create(
            name="Complete Student",
            session_id="complete-score-session",
            mock_test=mock_test,
        )
        incomplete_session = UserMockTestSession.objects.create(
            name="Incomplete Student",
            session_id="incomplete-score-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=complete_session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=incomplete_session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=incomplete_session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "pending"},
            evaluated=False,
            evaluation_status="failed",
        )

        stdout = StringIO()
        call_command(
            "recalculate_session_scores",
            "--only-complete",
            "--dry-run",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("session=complete-score-session", output)
        self.assertIn("status=complete", output)
        self.assertNotIn("session=incomplete-score-session", output)
        self.assertIn("1 sessions would be recalculated.", output)

    def test_recalculate_session_scores_reports_incomplete_counts(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Incomplete Student",
            session_id="incomplete-count-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "pending"},
            evaluated=False,
            evaluation_status="failed",
        )

        stdout = StringIO()
        call_command(
            "recalculate_session_scores",
            "--session-id",
            session.session_id,
            "--dry-run",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("responses=2", output)
        self.assertIn("evaluated=1", output)
        self.assertIn("pending=1", output)
        self.assertIn("failed=1", output)
        self.assertIn("status=incomplete", output)

    def test_recalculate_session_scores_reports_duplicate_groups(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Duplicate Student",
            session_id="duplicate-recalc-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "first"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "second"},
            evaluated=True,
            evaluation_status="completed",
        )

        stdout = StringIO()
        call_command(
            "recalculate_session_scores",
            "--session-id",
            session.session_id,
            "--dry-run",
            stdout=stdout,
        )

        self.assertIn("duplicate_groups=1", stdout.getvalue())

    def test_recalculate_session_scores_can_skip_duplicate_groups(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Duplicate Student",
            session_id="skip-duplicate-recalc-session",
            mock_test=mock_test,
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "first"},
            evaluated=True,
            evaluation_status="completed",
        )
        UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "second"},
            evaluated=True,
            evaluation_status="completed",
        )

        stdout = StringIO()
        call_command(
            "recalculate_session_scores",
            "--session-id",
            session.session_id,
            "--skip-duplicates",
            "--dry-run",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("status=skipped_duplicate_responses", output)
        self.assertIn("0 sessions would be recalculated.", output)

    def test_evaluate_response_now_dry_run_reports_current_state(self):
        mock_test, question = self._create_question()
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="diagnostic-dry-run-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            evaluation_status="failed",
            evaluation_stage="evaluation",
            evaluation_error="Previous failure",
        )

        stdout = StringIO()
        call_command(
            "evaluate_response_now",
            str(response.id),
            "--dry-run",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Current status: failed", output)
        self.assertIn("Current stage: evaluation", output)
        self.assertIn("Current error: Previous failure", output)
        self.assertIn("Needs transcription: False", output)

    def test_evaluate_response_now_force_transcription_marks_audio_as_needed(self):
        mock_test, question = self._create_question()
        question.subsection.ai_input_type = "audio"
        question.subsection.save(update_fields=["ai_input_type"])
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="force-transcription-dry-run-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data={"text": "answer"},
            answer_audio="response/audio/example.wav",
            transcribed_audio_data={"transcription": {"text": "old transcript"}},
        )

        stdout = StringIO()
        call_command(
            "evaluate_response_now",
            str(response.id),
            "--dry-run",
            "--force-transcription",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Has audio: True", output)
        self.assertIn("Has transcription: True", output)
        self.assertIn("Needs transcription: True", output)

    @override_settings(
        OPENAI_API_KEY="test-openai-key",
        OPENAI_WHISPER_API_KEY="test-whisper-key",
    )
    def test_runtime_check_can_skip_external_services(self):
        stdout = StringIO()

        call_command(
            "check_evaluation_runtime",
            "--skip-redis",
            "--skip-celery",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("OPENAI_API_KEY=set", output)
        self.assertIn("OPENAI_WHISPER_API_KEY=set", output)
        self.assertIn("CELERY_EVALUATION_QUEUE=evaluation", output)
        self.assertIn("CELERY_TRANSCRIPTION_QUEUE=transcription", output)
        self.assertIn("Evaluation runtime looks healthy.", output)

    def test_celery_routes_split_evaluation_and_transcription_queues(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["mocktest.tasks.evaluate_user_response"]["queue"],
            settings.CELERY_EVALUATION_QUEUE,
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["mocktest.tasks.evaluate_single_response"]["queue"],
            settings.CELERY_EVALUATION_QUEUE,
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["mocktest.tasks.transcribe_task"]["queue"],
            settings.CELERY_TRANSCRIPTION_QUEUE,
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["mocktest.tasks.transcribe_single_task"]["queue"],
            settings.CELERY_TRANSCRIPTION_QUEUE,
        )

    def test_celery_durability_defaults_are_enabled(self):
        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertTrue(settings.CELERY_TASK_REJECT_ON_WORKER_LOST)
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)
        self.assertTrue(settings.CELERY_TASK_TRACK_STARTED)
        self.assertLess(
            settings.CELERY_TASK_SOFT_TIME_LIMIT,
            settings.CELERY_TASK_TIME_LIMIT,
        )
        self.assertGreaterEqual(
            settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"],
            settings.CELERY_TASK_TIME_LIMIT,
        )

    @override_settings(
        OPENAI_API_KEY="",
        OPENAI_WHISPER_API_KEY="test-whisper-key",
    )
    def test_runtime_check_fails_when_openai_key_missing(self):
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "check_evaluation_runtime",
                "--skip-redis",
                "--skip-celery",
                stdout=stdout,
            )

        self.assertIn("OPENAI_API_KEY=missing", stdout.getvalue())

    @override_settings(
        OPENAI_API_KEY="test-openai-key",
        OPENAI_WHISPER_API_KEY="test-whisper-key",
    )
    @patch("mocktest.management.commands.check_evaluation_runtime.current_app")
    def test_runtime_check_fails_when_no_celery_workers_respond(self, mock_celery):
        inspector = mock_celery.control.inspect.return_value
        inspector.ping.return_value = {}
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "check_evaluation_runtime",
                "--skip-redis",
                stdout=stdout,
            )

        self.assertIn("workers=0", stdout.getvalue())

    @override_settings(
        OPENAI_API_KEY="test-openai-key",
        OPENAI_WHISPER_API_KEY="test-whisper-key",
    )
    @patch("mocktest.management.commands.check_evaluation_runtime.current_app")
    def test_runtime_check_reports_worker_queues(self, mock_celery):
        inspector = mock_celery.control.inspect.return_value
        inspector.ping.return_value = {"worker-evaluation": {"ok": "pong"}}
        inspector.active_queues.return_value = {
            "worker-evaluation": [
                {"name": "evaluation"},
                {"name": "transcription"},
            ]
        }
        stdout = StringIO()

        call_command(
            "check_evaluation_runtime",
            "--skip-redis",
            stdout=stdout,
        )

        output = stdout.getvalue()
        self.assertIn("Worker queues", output)
        self.assertIn("- worker-evaluation: evaluation, transcription", output)

    @override_settings(
        OPENAI_API_KEY="test-openai-key",
        OPENAI_WHISPER_API_KEY="test-whisper-key",
    )
    @patch("mocktest.management.commands.check_evaluation_runtime.current_app")
    def test_runtime_check_fails_when_expected_queue_missing(self, mock_celery):
        inspector = mock_celery.control.inspect.return_value
        inspector.ping.return_value = {"worker-evaluation": {"ok": "pong"}}
        inspector.active_queues.return_value = {
            "worker-evaluation": [
                {"name": "evaluation"},
            ]
        }
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "check_evaluation_runtime",
                "--skip-redis",
                stdout=stdout,
            )

        self.assertIn("Worker queues", stdout.getvalue())
