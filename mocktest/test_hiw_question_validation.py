from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from mocktest.models import MockTest, MockTestSection, Question, Section, SubSection
from mocktest.services.question_bank_validation import QuestionBankAuditor


class HighlightIncorrectWordQuestionValidationTests(TestCase):
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
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name="HIW-Q1",
            text="The cat sat on the blue mat.",
            audio=SimpleUploadedFile("source.mp3", b"audio-data"),
            listening_score_max=2,
        )

    def issue_codes(self):
        return {
            issue["code"]
            for issue in QuestionBankAuditor(
                check_storage=False,
                include_response_context=False,
            ).question_issues(self.question)
        }

    def test_missing_source_transcript_blocks_question(self):
        self.assertIn("invalid_answer_key", self.issue_codes())

    def test_reviewed_source_transcript_satisfies_hiw_validation(self):
        self.question.correct_answer = "The dog sat on the red mat."
        self.question.save(update_fields=["correct_answer"])

        self.assertNotIn("invalid_answer_key", self.issue_codes())
