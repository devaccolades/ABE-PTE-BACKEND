from django.core.exceptions import ValidationError
from django.test import TestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubQuestion,
    SubSection,
    UserMockTestSession,
)
from mocktest.services.mock_test_copy import create_editable_mock_test_copy
from mocktest.services.session_finalization import create_session_manifest


class EditableMockTestCopyTests(TestCase):
    def setUp(self):
        section = Section.objects.create(name="Reading")
        subsection = SubSection.objects.create(
            section=section,
            name="fib_dropdown",
            evaluation_type="rule",
        )
        self.source = MockTest.objects.create(
            title="Reviewed paper",
            description="Original description",
            total_score=90,
            total_duration=7200,
            scoring_mode="v2",
        )
        source_section = MockTestSection.objects.create(
            mock_test=self.source,
            section=section,
            order=1,
            total_duration=1200,
        )
        self.source_question = Question.objects.create(
            mock_test_section=source_section,
            subsection=subsection,
            name="R-FIB-1",
            text="Choose ----.",
            correct_answer="answer",
            reading_score_max=1,
            image="questions/images/reference.png",
        )
        QuestionOption.objects.create(
            question=self.source_question,
            option_text="Direct option",
            order_position=1,
        )
        blank = SubQuestion.objects.create(
            question=self.source_question,
            blank_number=1,
            correct_answer="answer",
        )
        QuestionOption.objects.create(
            sub_question=blank,
            option_text="answer",
            is_correct=True,
        )
        session = UserMockTestSession.objects.create(
            name="Historical candidate",
            session_id="historical-copy-test",
            mock_test=self.source,
            scoring_mode="v2",
        )
        create_session_manifest(session.pk)

    def test_copy_is_editable_and_preserves_complete_question_setup(self):
        with self.assertRaises(ValidationError):
            self.source_question.text = "Unsafe live edit"
            self.source_question.save(update_fields=["text"])

        draft = create_editable_mock_test_copy(self.source)

        self.assertFalse(draft.is_active)
        self.assertEqual(draft.scoring_mode, "v2")
        self.assertEqual(draft.sections.count(), 1)
        copied = Question.objects.get(mock_test_section__mock_test=draft)
        self.assertNotEqual(copied.pk, self.source_question.pk)
        self.assertEqual(copied.text, self.source_question.text)
        self.assertEqual(copied.image.name, self.source_question.image.name)
        self.assertEqual(copied.options.count(), 1)
        self.assertEqual(copied.sub_questions.count(), 1)
        self.assertEqual(copied.sub_questions.get().options.count(), 1)

        copied.text = "Safe draft edit"
        copied.save(update_fields=["text"])
        self.source_question.refresh_from_db()
        self.assertEqual(self.source_question.text, "Choose ----.")

    def test_repeated_copies_receive_distinct_titles(self):
        first = create_editable_mock_test_copy(self.source)
        second = create_editable_mock_test_copy(self.source)

        self.assertNotEqual(first.title, second.title)
