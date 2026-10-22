"""Detect answers that reproduce the task prompt instead of responding to it."""

from html.parser import HTMLParser
import re
import unicodedata

from examinor.services.repetitive_answer import apply_answer_integrity_override


PROMPT_COPY_TASKS = frozenset({"write_essay", "respond_to_a_situation"})


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _tokens(text):
    parser = _VisibleText()
    parser.feed(str(text or ""))
    visible = unicodedata.normalize("NFKC", " ".join(parser.parts)).casefold()
    visible = visible.replace("'", "").replace("\u2019", "")
    return re.findall(r"[^\W_]+", visible)


def detect_prompt_copy(answer, question_text, answer_type):
    applicable = answer_type in PROMPT_COPY_TASKS
    candidate = _tokens(answer) if applicable else []
    prompt = _tokens(question_text) if applicable else []
    covered = set()
    if candidate and prompt:
        # Four-word fragments tolerate punctuation, small edits and repeated copies
        # without treating shared topic vocabulary as evidence of copying.
        fragments = {tuple(prompt[i:i + 4]) for i in range(len(prompt) - 3)}
        for i in range(len(candidate) - 3):
            if tuple(candidate[i:i + 4]) in fragments:
                covered.update(range(i, i + 4))
    ratio = len(covered) / len(candidate) if candidate else 0.0
    exact = len(candidate) >= 4 and candidate == prompt
    dominated = len(candidate) >= 8 and ratio >= 0.90
    blocked = applicable and (exact or dominated)
    return {
        "detector_version": "prompt-copy-v1",
        "applicable": applicable,
        "is_prompt_copy": blocked,
        "answer_word_count": len(candidate),
        "matched_word_count": len(covered),
        "prompt_copy_ratio": ratio,
        "reason": (
            "The answer repeats the question instead of providing an original response."
            if blocked else "No prompt-copy override applied."
        ),
    }


def apply_prompt_copy_override(result, detection):
    if not detection["is_prompt_copy"]:
        return result
    return apply_answer_integrity_override(
        result,
        detection,
        check_name="prompt_copy",
        trigger_field="is_prompt_copy",
        override_code="copied_question_answer",
    )
