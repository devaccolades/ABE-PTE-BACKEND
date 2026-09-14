from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from mocktest.models import (
    MockTest,
    MockTestSection,
    Question,
    Section,
    SingleResponse,
    SubSection,
    UserMockTestSession,
    UserResponse,
)
from mocktest.services.session_finalization import create_session_manifest


class CorrectReadAloudSkillPolicyTests(TestCase):
    def setUp(self):
        mock_test = MockTest.objects.create(title="Current PTE")
        section = Section.objects.create(name="Speaking")
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
        )
        self.subsection = SubSection.objects.create(
            section=section,
            name="read_aloud",
            rubric={"content": {"max": 6}},
            trait_skill_map={
                "content": ["reading", "speaking"],
                "oral_fluency": ["speaking"],
                "pronunciation": ["speaking"],
            },
        )
        self.question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=self.subsection,
            name="RA-1",
            speaking_score_max=1.5,
            reading_score_max=6,
        )
        self.session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="read-aloud-policy",
            mock_test=mock_test,
            scoring_mode="v2",
        )
        create_session_manifest(self.session.pk)
        self.session.question_manifest.update(
            trait_skill_map_snapshot={
                "content": ["reading", "speaking"],
                "oral_fluency": ["speaking"],
                "pronunciation": ["speaking"],
            },
            skill_maxima_snapshot={
                "speaking": 1.5,
                "writing": 0,
                "reading": 6,
                "listening": 0,
            },
        )
        result = {
            "ok": True,
            "evaluation": {
                "scores": {
                    "content": {"score": 6, "max": 6},
                    "oral_fluency": {"score": 5, "max": 5},
                    "pronunciation": {"score": 5, "max": 5},
                },
            },
        }
        self.response = UserResponse.objects.create(
            user_session=self.session,
            mock_test=mock_test,
            question=self.question,
            evaluated=True,
            evaluation_status="completed",
            evaluation_result=result,
            speaking_score_awarded=1.5,
            reading_score_awarded=6,
        )
        self.single = SingleResponse.objects.create(
            question=self.question,
            scoring_mode="v2",
            evaluated=True,
            evaluation_status="completed",
            evaluation_result=result,
            speaking_score_awarded=1.5,
            reading_score_awarded=6,
        )

    def test_confirm_updates_config_snapshots_and_stored_scores(self):
        call_command(
            "correct_read_aloud_skill_policy",
            "--reason",
            "Current Pearson Read Aloud policy",
            "--expected-subsection-count",
            "1",
            "--expected-question-count",
            "1",
            "--expected-user-count",
            "1",
            "--expected-single-count",
            "1",
            "--expected-manifest-count",
            "1",
            "--confirm",
            stdout=StringIO(),
        )

        self.subsection.refresh_from_db()
        self.question.refresh_from_db()
        self.response.refresh_from_db()
        self.single.refresh_from_db()
        manifest = self.session.question_manifest.get()

        self.assertEqual(self.subsection.trait_skill_map["content"], ["speaking"])
        self.assertIsNone(self.question.reading_score_max)
        self.assertEqual(manifest.skill_maxima_snapshot["reading"], 0)
        self.assertEqual(manifest.trait_skill_map_snapshot["content"], ["speaking"])
        self.assertEqual(self.response.reading_score_awarded, 0)
        self.assertEqual(self.single.reading_score_awarded, 0)
        self.assertEqual(
            self.response.evaluation_result["score_corrections"][-1]["policy_after"],
            "speaking_only",
        )

        rerun = StringIO()
        call_command("correct_read_aloud_skill_policy", stdout=rerun)
        self.assertIn("Questions with Reading maxima to clear: 0", rerun.getvalue())
        self.assertIn("Evaluated UserResponses to rescore: 0", rerun.getvalue())
