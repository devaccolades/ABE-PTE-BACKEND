from django.test import TestCase, override_settings

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
from mocktest.tasks import validate_evaluation_or_fail


class RepetitiveAnswerPolicyTests(TestCase):
    def _question(self, subsection_name, *, input_type="text"):
        skill = "speaking" if input_type == "audio" else "writing"
        mock_test = MockTest.objects.create(title=f"{subsection_name} test")
        section = Section.objects.create(name=skill.title())
        mock_test_section = MockTestSection.objects.create(
            mock_test=mock_test,
            section=section,
            order=1,
        )
        subsection = SubSection.objects.create(
            section=section,
            name=subsection_name,
            evaluation_type="ai",
            ai_input_type=input_type,
            rubric={"content": {"max": 6}},
            trait_skill_map={"content": [skill]},
        )
        maxima = {f"{skill}_score_max": 6}
        question = Question.objects.create(
            mock_test_section=mock_test_section,
            subsection=subsection,
            name=f"{subsection_name}-1",
            text="Respond to the prompt.",
            **maxima,
        )
        return mock_test, question, subsection

    @staticmethod
    def _evaluation(score=5):
        return {
            "ok": True,
            "evaluation": {
                "scores": {"content": {"score": score, "max": 6}},
                "weighted_score": score,
                "max_score": 6,
            },
        }

    def test_writing_response_is_zeroed_and_reason_is_stored(self):
        mock_test, question, subsection = self._question("write_essay")
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="repetition-writing-session",
            mock_test=mock_test,
            scoring_mode="v2",
        )
        repeated = (
            "This important issue clearly shows that people should work together "
            "to create a better future for everyone."
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data=" ".join([repeated] * 8),
        )

        result = validate_evaluation_or_fail(
            response,
            self._evaluation(),
            subsection,
        )

        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertEqual(result["evaluation"]["scores"]["content"]["score"], 0)
        self.assertTrue(
            result["integrity_checks"]["repetition"]["is_repetitive"]
        )
        self.assertEqual(
            result["score_overrides"][0]["code"],
            "repetitive_template_answer",
        )
        self.assertEqual(
            result["score_overrides"][0]["original_weighted_score"],
            5,
        )

        response.evaluation_result = result
        response.save(update_fields=["evaluation_result"])
        response.apply_skill_scores()
        response.refresh_from_db()

        self.assertTrue(response.evaluated)
        self.assertEqual(response.writing_score_awarded, 0)
        self.assertEqual(
            response.evaluation_result["scoring_evidence"]["promoted"]["skills"][
                "writing"
            ]["score"],
            0,
        )

    def test_speaking_transcript_uses_the_same_policy(self):
        mock_test, question, subsection = self._question(
            "describe_image",
            input_type="audio",
        )
        repeated = "The picture clearly presents the same prepared description."
        response = SingleResponse.objects.create(
            name="Candidate",
            question=question,
            answer_data={},
            transcribed_audio_data={
                "transcription": {"text": " ".join([repeated] * 5)},
            },
        )

        result = validate_evaluation_or_fail(
            response,
            self._evaluation(),
            subsection,
        )

        self.assertEqual(result["evaluation"]["weighted_score"], 0)
        self.assertTrue(
            result["integrity_checks"]["repetition"]["is_repetitive"]
        )

        response.evaluation_result = result
        response.save(update_fields=["evaluation_result"])
        response.apply_skill_scores()
        response.refresh_from_db()

        self.assertTrue(response.evaluated)
        self.assertEqual(response.speaking_score_awarded, 0)

    def test_non_descriptive_task_does_not_run_detector(self):
        mock_test, question, subsection = self._question("write_from_dictation")
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="repetition-excluded-session",
            mock_test=mock_test,
        )
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data="same fixed answer same fixed answer same fixed answer",
        )

        result = validate_evaluation_or_fail(
            response,
            self._evaluation(),
            subsection,
        )

        self.assertEqual(result["evaluation"]["weighted_score"], 5)
        self.assertNotIn("integrity_checks", result)

    @override_settings(REPETITIVE_ANSWER_CONFIG={"enabled": False})
    def test_policy_can_be_disabled(self):
        mock_test, question, subsection = self._question("write_essay")
        session = UserMockTestSession.objects.create(
            name="Candidate",
            session_id="repetition-disabled-session",
            mock_test=mock_test,
        )
        repeated = "This answer repeats exactly the same prepared sentence many times."
        response = UserResponse.objects.create(
            user_session=session,
            mock_test=mock_test,
            question=question,
            answer_data=" ".join([repeated] * 10),
        )

        result = validate_evaluation_or_fail(
            response,
            self._evaluation(),
            subsection,
        )

        self.assertEqual(result["evaluation"]["weighted_score"], 5)
        self.assertNotIn("integrity_checks", result)
