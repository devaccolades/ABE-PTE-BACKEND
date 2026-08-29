from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re


WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
MIN_ALIGNMENT_RATIO = 0.5


class HighlightIncorrectWordsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WordToken:
    word_index: int
    word: str
    normalized: str


@dataclass(frozen=True, slots=True)
class IncorrectWord:
    word_index: int
    word: str
    expected: str


@dataclass(frozen=True, slots=True)
class TranscriptComparison:
    alignment_ratio: float
    displayed_word_count: int
    source_word_count: int
    incorrect_words: tuple[IncorrectWord, ...]
    source_only_words: tuple[str, ...]

    @property
    def unscorable_differences(self):
        differences = []
        empty_expected = tuple(
            item for item in self.incorrect_words if not item.expected
        )
        if empty_expected:
            positions = ", ".join(
                str(item.word_index) for item in empty_expected
            )
            differences.append(
                f"displayed word deletion(s) at position(s): {positions}"
            )
        if self.source_only_words:
            differences.append(
                "source-only word insertion(s): "
                + ", ".join(self.source_only_words)
            )
        return tuple(differences)

    def as_dict(self):
        return {
            "alignment_ratio": self.alignment_ratio,
            "displayed_word_count": self.displayed_word_count,
            "source_word_count": self.source_word_count,
            "incorrect_words": [asdict(item) for item in self.incorrect_words],
            "source_only_words": list(self.source_only_words),
            "scorable": not self.unscorable_differences,
            "review_warnings": list(self.unscorable_differences),
        }


def tokenize_words(value):
    return tuple(
        WordToken(
            word_index=index,
            word=match.group(0),
            normalized=match.group(0).lower().replace("’", "'"),
        )
        for index, match in enumerate(WORD_RE.finditer(str(value or "")))
    )


def compare_displayed_text_to_source(displayed_text, source_transcript):
    displayed = tokenize_words(displayed_text)
    source = tokenize_words(source_transcript)
    if not displayed:
        raise HighlightIncorrectWordsError("The displayed question text has no words.")
    if not source:
        raise HighlightIncorrectWordsError(
            "A source-audio transcript is required in Question.correct_answer."
        )

    displayed_values = [token.normalized for token in displayed]
    source_values = [token.normalized for token in source]
    matcher = SequenceMatcher(
        None,
        displayed_values,
        source_values,
        autojunk=False,
    )
    alignment_ratio = round(matcher.ratio(), 4)
    if alignment_ratio < MIN_ALIGNMENT_RATIO:
        raise HighlightIncorrectWordsError(
            "Displayed text and source transcript are too different to score safely "
            f"(alignment={alignment_ratio:.2f})."
        )

    incorrect = []
    source_only = []
    for tag, displayed_start, displayed_end, source_start, source_end in matcher.get_opcodes():
        if tag == "equal":
            continue

        expected_words = [token.word for token in source[source_start:source_end]]
        if tag in {"replace", "delete"}:
            displayed_segment = displayed[displayed_start:displayed_end]
            for offset, token in enumerate(displayed_segment):
                expected = expected_words[offset] if offset < len(expected_words) else ""
                incorrect.append(
                    IncorrectWord(
                        word_index=token.word_index,
                        word=token.word,
                        expected=expected,
                    )
                )
        if tag == "insert":
            source_only.extend(expected_words)
        elif tag == "replace" and len(expected_words) > displayed_end - displayed_start:
            source_only.extend(expected_words[displayed_end - displayed_start:])

    if not incorrect:
        raise HighlightIncorrectWordsError(
            "The displayed text has no detectable incorrect words compared with the source transcript."
        )

    return TranscriptComparison(
        alignment_ratio=alignment_ratio,
        displayed_word_count=len(displayed),
        source_word_count=len(source),
        incorrect_words=tuple(incorrect),
        source_only_words=tuple(source_only),
    )


def assess_highlighted_words(displayed_text, source_transcript, normalized_answer):
    comparison = compare_displayed_text_to_source(displayed_text, source_transcript)
    ensure_scorable_comparison(comparison)
    expected_by_index = {
        item.word_index: item for item in comparison.incorrect_words
    }

    if normalized_answer.get("mode") == "positions":
        displayed_by_index = {
            token.word_index: token for token in tokenize_words(displayed_text)
        }
        correct_selected = []
        incorrect_selected = []
        selected_indices = set()
        for selection in normalized_answer.get("selections", []):
            index = selection["word_index"]
            submitted_word = selection["word"]
            displayed_token = displayed_by_index.get(index)
            valid_position = bool(
                displayed_token
                and displayed_token.normalized
                == submitted_word.lower().replace("’", "'")
            )
            if valid_position and index in expected_by_index:
                correct_selected.append(expected_by_index[index])
                selected_indices.add(index)
            else:
                incorrect_selected.append(
                    {
                        "word_index": index,
                        "word": submitted_word,
                    }
                )
        missed = [
            item
            for item in comparison.incorrect_words
            if item.word_index not in selected_indices
        ]
    else:
        expected_counts = Counter(
            item.word.lower().replace("’", "'")
            for item in comparison.incorrect_words
        )
        selected_words = [
            str(word).strip()
            for word in normalized_answer.get("words", [])
            if str(word).strip()
        ]
        selected_counts = Counter(
            word.lower().replace("’", "'") for word in selected_words
        )
        matched_counts = selected_counts & expected_counts
        wrong_counts = selected_counts - expected_counts
        missed_counts = expected_counts - selected_counts
        correct_selected = []
        for item in comparison.incorrect_words:
            normalized = item.word.lower().replace("’", "'")
            if matched_counts[normalized] > 0:
                correct_selected.append(item)
                matched_counts[normalized] -= 1
        incorrect_selected = [
            {"word_index": None, "word": word}
            for word, count in wrong_counts.items()
            for _ in range(count)
        ]
        missed = []
        for item in comparison.incorrect_words:
            normalized = item.word.lower().replace("’", "'")
            if missed_counts[normalized] > 0:
                missed.append(item)
                missed_counts[normalized] -= 1

    awarded = max(len(correct_selected) - len(incorrect_selected), 0)
    ratio = awarded / len(comparison.incorrect_words)
    return {
        "ratio": ratio,
        "awarded": awarded,
        "expected_count": len(comparison.incorrect_words),
        "correct_selected": correct_selected,
        "incorrect_selected": incorrect_selected,
        "missed": missed,
        "comparison": comparison,
    }


def ensure_scorable_comparison(comparison):
    if comparison.unscorable_differences:
        raise HighlightIncorrectWordsError(
            "Displayed text and source transcript contain insertion/deletion "
            "differences that cannot be selected by the candidate. Normalize the "
            "reviewed transcript to the displayed text's token boundaries: "
            + "; ".join(comparison.unscorable_differences)
        )
