from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SubSection,
    UserMockTestSession,
    UserResponse,
)


class HighlightIncorrectWordResponseReevaluationTests(TestCase):
    def setUp(self):
        mock_test = MockTest.objects.create(title="HIW Test")
        section = Section.objects.create(name="Listening")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        subsection = SubSection.objects.create(
            section=section,
            name="highlight_incorrect_words",
            rubric={"content": {"max": 2}},
            trait_skill_map={"content": ["listening"]},
        )
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            text="The cat sat on the blue mat.",
            correct_answer="The dog sat on the red mat.",
            listening_score_max=2,
        )
        session = UserMockTestSession.objects.create(
            name="Student",
            session_id="hiw-session",
            mock_test=mock_test,
        )
        self.response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data="cat,blue",
            evaluation_status="completed",
            evaluated=True,
        )

    def test_dry_run_does_not_change_response(self):
        stdout = StringIO()
        call_command(
            "reevaluate_highlight_incorrect_word_responses",
            stdout=stdout,
        )

        self.response.refresh_from_db()
        self.assertEqual(self.response.listening_score_awarded, 0)
        self.assertIn("Dry run only", stdout.getvalue())

    def test_confirm_recalculates_response_and_session(self):
        call_command(
            "reevaluate_highlight_incorrect_word_responses",
            "--confirm",
            "--expected-user-count",
            "1",
            "--expected-single-count",
            "0",
            stdout=StringIO(),
        )

        self.response.refresh_from_db()
        self.response.user_session.refresh_from_db()
        self.assertEqual(self.response.listening_score_awarded, 2)
        self.assertEqual(self.response.evaluation_status, "completed")
        self.assertEqual(self.response.user_session.listening_score_awarded, 2)
