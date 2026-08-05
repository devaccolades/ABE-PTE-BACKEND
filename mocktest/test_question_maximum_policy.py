import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from mocktest.forms import QuestionAdminForm
from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    QuestionOption,
    Section,
    SubQuestion,
    SubSection,
)
from mocktest.services.question_bank_validation import QuestionBankAuditor
from mocktest.services.question_maximum_policy import (
    maximum_policy_rows,
    question_skill_maximum_expectations,
)


class QuestionMaximumPolicyTests(TestCase):
    def setUp(self):
        self.mock_test = MockTest.objects.create(title="Maximum Policy Test")
        self.reading = Section.objects.create(name="Reading")
        self.reading_test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=self.reading,
        )

    def _subsection(self, name, *, section=None, mapping=None, rubric=None):
        return SubSection.objects.create(
            section=section or self.reading,
            name=name,
            evaluation_type="rule",
            trait_skill_map=mapping or {"reading": ["reading"]},
            rubric=rubric or {"reading": {"0": "Minimum", "1": "Correct"}},
        )

    def test_dropdown_maximum_is_derived_from_blank_count(self):
        subsection = self._subsection("fib_dropdown")
        question = Question.objects.create(
            mock_test_section=self.reading_test_section,
            subsection=subsection,
            reading_score_max=2,
        )
        for blank_number in (1, 2):
            subquestion = SubQuestion.objects.create(
                question=question,
                blank_number=blank_number,
            )
            QuestionOption.objects.create(
                sub_question=subquestion,
                option_text="correct",
                is_correct=True,
            )

        expectations = question_skill_maximum_expectations(question)

        self.assertEqual(
            [(item.skill, item.maximum) for item in expectations],
            [("reading", 2.0)],
        )
        self.assertEqual(maximum_policy_rows(question)[0]["status"], "match")

    def test_repeat_sentence_uses_approved_fixed_maxima(self):
        speaking = Section.objects.create(name="Speaking")
        test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=speaking,
        )
        subsection = self._subsection(
            "repeat_sentence",
            section=speaking,
            mapping={
                "content": ["listening"],
                "oral_fluency": ["speaking"],
                "pronunciation": ["speaking"],
            },
            rubric={"content": {"0": "None", "3": "Complete"}},
        )
        question = Question.objects.create(
            mock_test_section=test_section,
            subsection=subsection,
            speaking_score_max=1.4,
            listening_score_max=15,
        )

        rows = maximum_policy_rows(question)

        self.assertEqual(rows[0]["status"], "match")
        self.assertEqual(rows[1]["status"], "mismatch")
        self.assertEqual(rows[1]["expected_maximum"], 1.5)

    def test_write_from_dictation_uses_reference_word_count(self):
        listening = Section.objects.create(name="Listening")
        test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=listening,
        )
        subsection = self._subsection(
            "write_from_dictation",
            section=listening,
            mapping={"listening_and_writing": ["listening", "writing"]},
            rubric={"listening_and_writing": {"0": "Wrong", "1": "Correct"}},
        )
        question = Question.objects.create(
            mock_test_section=test_section,
            subsection=subsection,
            correct_answer="Seven words are counted in this sentence",
            writing_score_max=7,
            listening_score_max=1,
        )

        rows = maximum_policy_rows(question)

        self.assertEqual([row["status"] for row in rows], ["match", "match"])

    def test_unapproved_task_is_reported_for_review_without_guessing(self):
        subsection = self._subsection(
            "write_essay",
            mapping={"content": ["writing"]},
            rubric={"content": {"0": "None", "3": "Complete"}},
        )
        question = Question.objects.create(
            mock_test_section=self.reading_test_section,
            subsection=subsection,
            writing_score_max=12.5,
        )

        row = maximum_policy_rows(question)[0]

        self.assertEqual(row["status"], "review_required")
        self.assertEqual(row["severity"], "warning")
        self.assertEqual(row["expected_maximum"], "")

    def test_publication_auditor_rejects_authoritative_mismatch(self):
        subsection = self._subsection("mc_single")
        question = Question.objects.create(
            mock_test_section=self.reading_test_section,
            subsection=subsection,
            reading_score_max=2,
        )
        QuestionOption.objects.create(
            question=question,
            option_text="Correct",
            is_correct=True,
        )

        issues = QuestionBankAuditor(check_storage=False).question_issues(question)

        self.assertIn(
            "question_skill_maximum_mismatch",
            {issue["code"] for issue in issues},
        )

    def test_admin_only_autofills_fixed_approved_maxima(self):
        speaking = Section.objects.create(name="Speaking")
        test_section = MockTestSection.objects.create(
            mock_test=self.mock_test,
            section=speaking,
        )
        subsection = self._subsection(
            "repeat_sentence",
            section=speaking,
            mapping={"content": ["listening"]},
            rubric={"content": {"0": "None", "3": "Complete"}},
        )
        form = QuestionAdminForm(data={
            "mock_test_section": test_section.pk,
            "question_type": "single_answer",
            "difficulty": "medium",
            "subsection": subsection.pk,
            "name": "Repeat",
            "text": "Repeat this sentence.",
            "reading_time": 0,
            "answering_time": 15,
            "speaking_score_max": "",
            "writing_score_max": "",
            "reading_score_max": "",
            "listening_score_max": "",
        })

        self.assertTrue(form.is_valid(), form.errors)
        question = form.save()
        self.assertEqual(question.speaking_score_max, 1.4)
        self.assertEqual(question.listening_score_max, 1.5)

    def test_audit_command_writes_read_only_csv(self):
        subsection = self._subsection("mc_single")
        question = Question.objects.create(
            mock_test_section=self.reading_test_section,
            subsection=subsection,
            reading_score_max=2,
        )
        QuestionOption.objects.create(
            question=question,
            option_text="Correct",
            is_correct=True,
        )
        stdout = StringIO()

        with TemporaryDirectory() as directory:
            output = Path(directory) / "maxima.csv"
            call_command(
                "audit_question_skill_maxima",
                "--mock-test",
                str(self.mock_test.pk),
                "--output",
                str(output),
                stdout=stdout,
            )
            with output.open(newline="", encoding="utf-8") as report:
                rows = list(csv.DictReader(report))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "mismatch")
        self.assertEqual(Question.objects.get(pk=question.pk).reading_score_max, 2)
        self.assertIn("Read-only audit", stdout.getvalue())
