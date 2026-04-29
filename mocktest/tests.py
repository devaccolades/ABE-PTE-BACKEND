from django.template.loader import render_to_string
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
from mocktest.services.pdf_service import build_session_pdf_context


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
