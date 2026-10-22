from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from examinor.scoring.response_scores import compile_response_score_evidence
from examinor.services.orchestrator import run_evaluation_for_subsection
from examinor.services.prompt_copy import detect_prompt_copy
from mocktest.tasks import apply_answer_integrity_policy
from mocktest.models import (
    MockTest, MockTestSection, Question, Section, SingleResponse, SubSection,
    UserMockTestSession, UserResponse,
)
from mocktest.tasks import evaluate_single_response, evaluate_user_response


PROMPT = (
    "Some people think television provides relaxation and companionship. "
    "To what extent do you agree or disagree with this statement?"
)


@override_settings(STRICT_FORM_POLICY_ENABLED=False)
class PromptCopyTests(SimpleTestCase):
    def test_exact_and_formatting_only_copies_are_blocked_for_both_tasks(self):
        for task in ("write_essay", "respond_to_a_situation"):
            for answer in (PROMPT, PROMPT.upper(), PROMPT.replace(".", "!")):
                with self.subTest(task=task, answer=answer):
                    self.assertTrue(detect_prompt_copy(answer, PROMPT, task)["is_prompt_copy"])
        self.assertTrue(detect_prompt_copy(
            PROMPT, "<p>" + PROMPT.replace(" ", "&nbsp;") + "</p>", "write_essay",
        )["is_prompt_copy"])

    def test_copied_fragments_repeated_prompt_and_token_additions_are_blocked(self):
        for answer in (PROMPT + " I agree.", PROMPT + " " + PROMPT,
                       "Some people think television provides relaxation and companionship."):
            with self.subTest(answer=answer):
                self.assertTrue(detect_prompt_copy(answer, PROMPT, "write_essay")["is_prompt_copy"])

    def test_topic_vocabulary_and_quotation_with_original_response_are_allowed(self):
        for answer in (
            "I agree that television provides relaxation and companionship because "
            "comedies help me unwind after work and interviews offer isolated viewers human contact.",
            PROMPT + " In my view, documentaries offer valuable knowledge while shared "
            "family viewing creates opportunities to discuss social issues and build relationships.",
            "Television provides companionship.",
        ):
            with self.subTest(answer=answer):
                self.assertFalse(detect_prompt_copy(answer, PROMPT, "write_essay")["is_prompt_copy"])

    def test_missing_prompt_and_tiny_matches_do_not_trigger(self):
        for answer, prompt in ((PROMPT, ""), ("I agree", "I agree"), ("", PROMPT)):
            self.assertFalse(detect_prompt_copy(answer, prompt, "write_essay")["is_prompt_copy"])

    def test_tasks_where_source_reproduction_is_expected_are_excluded(self):
        for task in ("read_aloud", "repeat_sentence", "write_from_dictation",
                     "summarize_written_text", "answer_short_question", "mc_multiple"):
            with self.subTest(task=task):
                self.assertFalse(detect_prompt_copy(PROMPT, PROMPT, task)["applicable"])

    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_gate_runs_before_provider_or_cache_and_zeros_every_trait(self, provider):
        for task in ("write_essay", "respond_to_a_situation"):
            for key, answer in (
                ("answer_data", {"text": PROMPT}),
                ("transcribed_audio_data", {"transcription": {"text": PROMPT}}),
            ):
                with self.subTest(task=task, key=key):
                    subsection = SimpleNamespace(
                        name=task, rubric={"content": {"max": 6}, "grammar": {"max": 2}},
                    )
                    result = run_evaluation_for_subsection(subsection, PROMPT, {key: answer})
                    self.assertTrue(result["ok"])
                    self.assertFalse(result["provider_called"])
                    self.assertEqual(result["evaluation"]["weighted_score"], 0)
                    self.assertEqual(result["evaluation"]["max_score"], 8)
                    self.assertTrue(all(p["score"] == 0 for p in result["evaluation"]["scores"].values()))
                    self.assertEqual(result["score_overrides"][0]["code"], "copied_question_answer")
        provider.assert_not_called()

    @patch("mocktest.tasks.inspect_answer_integrity")
    def test_final_score_policy_also_overrides_previously_positive_results(self, inspect):
        inspect.return_value = {"checks": {
            "repetition": {"enabled": False, "evidence": {"status": "disabled", "is_repetitive": False}},
            "known_template": {"enabled": False, "evidence": {"status": "disabled", "is_template_dominated": False}},
        }}
        for mode in ("legacy", "shadow", "v2"):
            for spoken in (True, False):
                with self.subTest(mode=mode, spoken=spoken):
                    task = "respond_to_a_situation" if spoken else "write_essay"
                    skill = "speaking" if spoken else "writing"
                    subsection = SimpleNamespace(name=task, trait_skill_map={"content": [skill], "form": [skill]})
                    question = SimpleNamespace(
                        text=PROMPT, subsection=subsection, speaking_score_max=6,
                        writing_score_max=6, reading_score_max=0, listening_score_max=0,
                    )
                    response = SimpleNamespace(question=question, answer_data=PROMPT,
                                               transcribed_audio_data=None)
                    result = apply_answer_integrity_policy(response, {
                        "ok": True,
                        "evaluation": {"scores": {
                            "content": {"score": 5, "max": 6},
                            "form": {"score": 2, "max": 2},
                        }, "weighted_score": 7},
                    }, subsection)
                    self.assertEqual(result["score_overrides"][0]["original_weighted_score"], 7)
                    evidence = compile_response_score_evidence(question, result, mode=mode)
                    self.assertTrue(all(p["score"] == 0 for p in evidence["promoted"]["skills"].values()))


@override_settings(STRICT_FORM_POLICY_ENABLED=False)
class PromptCopyTaskTests(TestCase):
    @patch("examinor.services.orchestrator.evaluate_with_openai")
    def test_full_exam_and_single_practice_save_zero_and_reason(self, provider):
        for task_name in ("write_essay", "respond_to_a_situation"):
            skill = "writing" if task_name == "write_essay" else "speaking"
            section = Section.objects.create(name=skill.title())
            subsection = SubSection.objects.create(
                section=section, name=task_name, evaluation_type="ai",
                ai_input_type="text" if skill == "writing" else "audio",
                rubric={"content": {"max": 6}, "form": {"max": 2}},
                trait_skill_map={"content": [skill], "form": [skill]},
            )
            paper = MockTest.objects.create(title=task_name, scoring_mode="v2")
            paper_section = MockTestSection.objects.create(mock_test=paper, section=section, order=1)
            question = Question.objects.create(
                name=task_name, text=PROMPT, subsection=subsection,
                mock_test_section=paper_section, **{f"{skill}_score_max": 8},
            )
            session = UserMockTestSession.objects.create(
                mock_test=paper, name="Prompt copy QA", session_id=task_name, scoring_mode="v2",
            )
            common = {"question": question, "answer_data": PROMPT}
            if skill == "speaking":
                common.update(answer_audio="qa/copied-prompt.webm", transcribed_audio_data={"transcription": {"text": PROMPT}})
            responses = (
                (SingleResponse.objects.create(name="QA", scoring_mode="v2", **common), evaluate_single_response),
                (UserResponse.objects.create(mock_test=paper, user_session=session, **common), evaluate_user_response),
            )
            for response, task in responses:
                with self.subTest(task=task_name, model=type(response).__name__):
                    execution = task.apply(args=(response.pk, question.pk))
                    self.assertTrue(execution.successful(), execution.result)
                    response.refresh_from_db()
                    self.assertTrue(response.evaluated)
                    self.assertEqual(response.evaluation_status, "completed")
                    self.assertEqual(getattr(response, f"{skill}_score_awarded"), 0)
                    self.assertTrue(response.evaluation_result["integrity_checks"]["prompt_copy"]["is_prompt_copy"])
        provider.assert_not_called()
