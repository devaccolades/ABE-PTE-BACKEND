from django.core.exceptions import ValidationError
from django.test import TestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubSection,
    UserMockTestSession,
)
from mocktest.forms import QuestionAdminForm
from mocktest.services.session_finalization import (
    complete_session_submission,
    create_session_manifest,
)


class QuestionPaperEditingTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section,
            name="mc_single",
            evaluation_type="rule",
        )
        self.paper = MockTest.objects.create(title="Editable paper")
        self.paper_section = MockTestSection.objects.create(
            mock_test=self.paper,
            section=section,
            order=1,
        )
        self.question = Question.objects.create(
            mock_test_section=self.paper_section,
            subsection=subsection,
            name="Question 1",
            text="Original prompt",
            reading_score_max=1,
        )
        self.option = QuestionOption.objects.create(
            question=self.question,
            option_text="Original option",
            is_correct=True,
        )

    def _session(self, *, completed=False):
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id=f"editing-test-{completed}",
            mock_test=self.paper,
            scoring_mode="v2",
        )
        create_session_manifest(session.pk)
        if completed:
            UserMockTestSession.objects.filter(pk=session.pk).update(is_completed=True)
        return session

    def test_inactive_unused_paper_can_be_edited_directly(self):
        self.question.text = "Corrected prompt"
        self.question.save(update_fields=["text"])
        self.option.option_text = "Corrected option"
        self.option.save(update_fields=["option_text"])

        self.question.refresh_from_db()
        self.option.refresh_from_db()
        self.assertEqual(self.question.text, "Corrected prompt")
        self.assertEqual(self.option.option_text, "Corrected option")

    def test_active_paper_cannot_be_edited(self):
        MockTest.objects.filter(pk=self.paper.pk).update(is_active=True)
        self.question.text = "Unsafe edit"

        with self.assertRaisesMessage(
            ValidationError,
            "Turn off 'Available to candidates'",
        ):
            self.question.save(update_fields=["text"])

        self.option.option_text = "Unsafe option edit"
        with self.assertRaisesMessage(
            ValidationError,
            "Turn off 'Available to candidates'",
        ):
            self.option.save(update_fields=["option_text"])

    def test_inactive_paper_with_unfinished_session_cannot_be_edited(self):
        self._session()
        self.question.text = "Unsafe edit"

        with self.assertRaisesMessage(ValidationError, "unfinished candidate session"):
            self.question.save(update_fields=["text"])

    def test_admin_form_reports_unfinished_session_as_validation_error(self):
        self._session()
        self.question.question_type = "single_answer"
        form = QuestionAdminForm(
            instance=self.question,
            data={
                "mock_test_section": self.paper_section.pk,
                "question_type": "single_answer",
                "difficulty": "medium",
                "subsection": self.question.subsection_id,
                "name": self.question.name,
                "text": "Corrected prompt",
                "correct_answer": "",
                "answer_explanation": "",
                "answer_explanation_draft": "",
                "reading_time": 0,
                "answering_time": 0,
                "speaking_score_max": "",
                "writing_score_max": "",
                "reading_score_max": 1,
                "listening_score_max": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Close selected unfinished sessions", str(form.errors))

    def test_inactive_paper_with_completed_session_can_be_edited(self):
        session = self._session(completed=True)
        snapshot = session.question_manifest.get(question=self.question)

        self.question.text = "Corrected after testing"
        self.question.save(update_fields=["text"])

        self.question.refresh_from_db()
        snapshot.refresh_from_db()
        self.assertEqual(self.question.text, "Corrected after testing")
        self.assertEqual(snapshot.question_snapshot["text"], "Original prompt")

    def test_closing_unanswered_session_unblocks_direct_editing(self):
        session = self._session()

        complete_session_submission(session.pk)
        session.refresh_from_db()
        self.assertTrue(session.is_completed)

        self.question.text = "Corrected after closing session"
        self.question.save(update_fields=["text"])
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "Corrected after closing session")
