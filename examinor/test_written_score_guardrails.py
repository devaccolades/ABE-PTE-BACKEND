from django.test import SimpleTestCase

from examinor.services.prompt_builder import TASK_CALIBRATION_RULES, build_prompt
from examinor.services.written_score_guardrails import apply_written_score_guardrails


def essay_scores(structure=6.0):
    return {
        "scores": {
            "content": {"score": 6.0, "max": 6.0},
            "development_structure_coherence": {"score": structure, "max": 6.0},
        },
        "weighted_score": 6.0 + structure,
    }


PARAGRAPH = "Modern life moves quickly, and many people feel constant pressure at work."


class EssayStructureCapTests(SimpleTestCase):
    def cap(self, answer, structure=6.0, task="write_essay"):
        return apply_written_score_guardrails(essay_scores(structure), task_type=task, answer=answer)

    def test_essay_without_paragraph_breaks_is_capped_at_band_three(self):
        result = self.cap(" ".join([PARAGRAPH] * 6))
        self.assertEqual(result["scores"]["development_structure_coherence"]["score"], 3.0)
        self.assertEqual(result["weighted_score"], 9.0)
        self.assertEqual(result["score_guardrails"][0]["reason"], "no_paragraph_breaks")
        self.assertEqual(result["score_guardrails"][0]["original_score"], 6.0)

    def test_paragraphed_essays_lower_scores_and_other_tasks_are_unchanged(self):
        paragraphed = "\n\n".join([PARAGRAPH] * 4)
        for answer, structure, task in (
            (paragraphed, 6.0, "write_essay"),
            ("\n".join([PARAGRAPH] * 3), 6.0, "write_essay"),
            (PARAGRAPH, 2.0, "write_essay"),
            (PARAGRAPH, 6.0, "summarize_written_text"),
        ):
            with self.subTest(task=task, structure=structure):
                self.assertEqual(self.cap(answer, structure, task), essay_scores(structure))


class TaskCalibrationPromptTests(SimpleTestCase):
    def test_pearson_band_rules_are_only_added_to_their_task(self):
        rubric = {"content": {"max": 6}}
        for task, phrase in (
            ("respond_to_a_situation", "no elaboration or support"),
            ("write_essay", "is not presented at all"),
            ("describe_image", "contradict the image"),
        ):
            with self.subTest(task=task):
                self.assertIn(phrase, build_prompt(task, "Q", {"answer_data": "An answer."}, rubric)[0])
        retell = build_prompt("retell_lecture", "Q", {"answer_data": "An answer."}, rubric)[0]
        for rules in TASK_CALIBRATION_RULES.values():
            self.assertNotIn(rules, retell)


class SpellingCountCapTests(SimpleTestCase):
    def cap(self, spelling, errors, task="write_essay"):
        evaluation = {
            "scores": {"spelling": {"score": spelling, "max": 2.0}},
            "weighted_score": spelling,
            "feedback": {"summary": "s", "errors": [{"type": t, "text": "x"} for t in errors]},
        }
        return apply_written_score_guardrails(evaluation, task_type=task, answer="One paragraph.\n\nTwo.")

    def test_spelling_follows_the_number_of_annotated_spelling_errors(self):
        for spelling, errors, expected in (
            (2.0, ["spelling", "spelling", "spelling"], 0.0),
            (1.0, ["spelling", "spelling"], 0.0),
            (2.0, ["spelling", "grammar"], 1.0),
            (2.0, ["grammar"], 2.0),
            (0.0, ["spelling"], 0.0),
        ):
            with self.subTest(errors=errors, spelling=spelling):
                self.assertEqual(self.cap(spelling, errors)["scores"]["spelling"]["score"], expected)

    def test_applies_to_summarize_spoken_text_too(self):
        self.assertEqual(
            self.cap(2.0, ["spelling", "spelling"], task="summarize_spoken_text")["scores"]["spelling"]["score"], 0.0,
        )
