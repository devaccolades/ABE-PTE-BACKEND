from django.test import SimpleTestCase

from examinor.scoring.task_contracts import (
    TASK_CONTRACTS,
    AnswerKind,
    EvaluationEngine,
    PayloadStatus,
    TaskContractError,
    get_task_contract,
    has_usable_transcript,
    inspect_answer_payload,
)
from mocktest.models import SubSection


class TaskRegistryTests(SimpleTestCase):
    def test_registry_covers_every_supported_subsection(self):
        supported = {name for name, _label in SubSection.SUBSECTION_CHOICES}
        self.assertEqual(set(TASK_CONTRACTS), supported)

    def test_gate_policies_are_task_specific(self):
        self.assertEqual(
            get_task_contract("repeat_sentence").gate_traits,
            ("content",),
        )
        self.assertEqual(
            get_task_contract("summarize_written_text").gate_traits,
            ("content", "form"),
        )
        self.assertEqual(
            get_task_contract("mc_single").gate_traits,
            (),
        )

    def test_effective_engine_is_explicit(self):
        self.assertEqual(
            get_task_contract("highlight_incorrect_words").evaluation_engine,
            EvaluationEngine.RULE,
        )
        self.assertEqual(
            get_task_contract("write_from_dictation").evaluation_engine,
            EvaluationEngine.RULE,
        )
        self.assertEqual(
            get_task_contract("read_aloud").answer_kind,
            AnswerKind.AUDIO_UPLOAD,
        )

    def test_unknown_subsection_fails_closed(self):
        with self.assertRaisesRegex(TaskContractError, "No evaluation task contract"):
            get_task_contract("unknown_task")


class AnswerPayloadInspectionTests(SimpleTestCase):
    def assertInspection(self, result, status, normalized):
        self.assertEqual(result.status, status)
        self.assertEqual(result.normalized, normalized)

    def test_every_subsection_has_valid_and_invalid_payload_examples(self):
        valid_by_kind = {
            AnswerKind.AUDIO_UPLOAD: ({}, {"has_audio": True}),
            AnswerKind.BLANK_MAPPING: ({"1": 10}, {}),
            AnswerKind.ORDERED_MAPPING: ({"1": 10, "2": 11}, {}),
            AnswerKind.SINGLE_OPTION_ID: (10, {}),
            AnswerKind.MULTIPLE_OPTION_IDS: ([10, 11], {}),
            AnswerKind.DELIMITED_TEXT: ("alpha|beta", {}),
            AnswerKind.HIGHLIGHTED_WORDS: (
                {"selections": [{"word_index": 0, "word": "alpha"}]},
                {},
            ),
            AnswerKind.FREE_TEXT: ("Candidate answer", {}),
        }
        invalid_by_kind = {
            AnswerKind.AUDIO_UPLOAD: ({}, {}),
            AnswerKind.BLANK_MAPPING: ({"first": 10}, {}),
            AnswerKind.ORDERED_MAPPING: ({"first": 10}, {}),
            AnswerKind.SINGLE_OPTION_ID: ("not-an-id", {}),
            AnswerKind.MULTIPLE_OPTION_IDS: ([0], {}),
            AnswerKind.DELIMITED_TEXT: (123, {}),
            AnswerKind.HIGHLIGHTED_WORDS: (
                {"selections": [{"word_index": -1, "word": "alpha"}]},
                {},
            ),
            AnswerKind.FREE_TEXT: (123, {}),
        }

        for subsection, contract in TASK_CONTRACTS.items():
            valid_answer, valid_context = valid_by_kind[contract.answer_kind]
            invalid_answer, invalid_context = invalid_by_kind[contract.answer_kind]
            with self.subTest(subsection=subsection, case="valid"):
                valid = inspect_answer_payload(
                    subsection,
                    valid_answer,
                    **valid_context,
                )
                self.assertNotEqual(valid.status, PayloadStatus.INVALID)
            with self.subTest(subsection=subsection, case="invalid"):
                invalid = inspect_answer_payload(
                    subsection,
                    invalid_answer,
                    **invalid_context,
                )
                self.assertEqual(invalid.status, PayloadStatus.INVALID)

    def test_non_audio_empty_payloads_are_unanswered(self):
        cases = (
            ("fib_dropdown", {}, {}),
            ("reorder_paragraphs", None, {}),
            ("mc_single", "", None),
            ("mc_multiple", [], []),
            ("l_fill_in_blanks", "||", []),
            ("write_essay", {"text": "  "}, ""),
        )

        for subsection, answer, normalized in cases:
            with self.subTest(subsection=subsection, answer=answer):
                result = inspect_answer_payload(subsection, answer)
                self.assertInspection(
                    result,
                    PayloadStatus.UNANSWERED,
                    normalized,
                )
                self.assertFalse(result.usable)
                self.assertEqual(result.issues[-1].code, "answer_not_provided")

    def test_audio_requires_audio_or_recoverable_transcript(self):
        canonical = inspect_answer_payload(
            "read_aloud",
            "legacy answer text is ignored",
            has_audio=True,
            has_transcript=False,
        )
        recoverable = inspect_answer_payload(
            "repeat_sentence",
            {},
            has_audio=False,
            has_transcript=True,
        )
        invalid = inspect_answer_payload(
            "describe_image",
            "text cannot replace response audio",
        )

        self.assertInspection(
            canonical,
            PayloadStatus.CANONICAL,
            {"response_source": "audio"},
        )
        self.assertInspection(
            recoverable,
            PayloadStatus.LEGACY_COMPATIBLE,
            {"response_source": "stored_transcript"},
        )
        self.assertEqual(invalid.status, PayloadStatus.INVALID)
        self.assertEqual(invalid.issues[0].code, "response_audio_missing")

    def test_usable_transcript_requires_non_empty_text(self):
        valid_cases = [
            "spoken answer",
            {"text": "legacy transcript"},
            {"transcription": "spoken answer"},
            {"transcription": {"text": "spoken answer"}},
        ]
        invalid_cases = [
            None,
            {},
            {"text": "  "},
            {"transcription": {}},
            {"transcription": {"text": ""}, "analysis": {"duration": 3}},
        ]

        for payload in valid_cases:
            with self.subTest(payload=payload):
                self.assertTrue(has_usable_transcript(payload))
        for payload in invalid_cases:
            with self.subTest(payload=payload):
                self.assertFalse(has_usable_transcript(payload))

    def test_mapping_normalizes_json_identifiers(self):
        result = inspect_answer_payload(
            "fib_dropdown",
            {"2": "103", "1": 101},
        )

        self.assertInspection(
            result,
            PayloadStatus.CANONICAL,
            {"1": 101, "2": 103},
        )

    def test_mapping_rejects_invalid_and_duplicate_selections(self):
        cases = [
            ({"first": 1}, "invalid_mapping_identifier"),
            ({"1": 10, "2": "10"}, "duplicate_option_selection"),
        ]

        for answer, issue_code in cases:
            with self.subTest(answer=answer):
                result = inspect_answer_payload("fib_drag_drop", answer)
                self.assertEqual(result.status, PayloadStatus.INVALID)
                self.assertEqual(result.issues[0].code, issue_code)

    def test_json_encoded_mapping_is_recoverable_legacy(self):
        result = inspect_answer_payload(
            "reorder_paragraphs",
            '{"1": 12, "2": 10}',
        )

        self.assertInspection(
            result,
            PayloadStatus.LEGACY_COMPATIBLE,
            {"1": 12, "2": 10},
        )
        self.assertEqual(result.issues[0].code, "json_encoded_answer")

    def test_single_choice_accepts_numeric_wire_values(self):
        number = inspect_answer_payload("mc_single", 42)
        numeric_string = inspect_answer_payload("l_mc_single", "42")
        wrapped = inspect_answer_payload(
            "highlight_correct_summary",
            {"selected_option_id": "42"},
        )

        self.assertInspection(number, PayloadStatus.CANONICAL, 42)
        self.assertInspection(numeric_string, PayloadStatus.CANONICAL, 42)
        self.assertInspection(wrapped, PayloadStatus.LEGACY_COMPATIBLE, 42)

    def test_multiple_choice_distinguishes_canonical_legacy_and_invalid(self):
        canonical = inspect_answer_payload("mc_multiple", [10, "11"])
        scalar = inspect_answer_payload("l_mc_multiple", "10")
        duplicate = inspect_answer_payload("mc_multiple", [10, "10"])
        empty = inspect_answer_payload("mc_multiple", [])

        self.assertInspection(canonical, PayloadStatus.CANONICAL, [10, 11])
        self.assertInspection(scalar, PayloadStatus.LEGACY_COMPATIBLE, [10])
        self.assertEqual(
            scalar.issues[0].code,
            "scalar_multiple_choice_answer",
        )
        self.assertEqual(duplicate.status, PayloadStatus.INVALID)
        self.assertEqual(duplicate.issues[0].code, "duplicate_option_selection")
        self.assertInspection(empty, PayloadStatus.UNANSWERED, [])

    def test_delimited_text_supports_current_and_legacy_shapes(self):
        canonical = inspect_answer_payload(
            "l_fill_in_blanks",
            "alpha|beta|gamma",
        )
        mapped = inspect_answer_payload(
            "l_fill_in_blanks",
            {"2": "beta", "1": "alpha"},
        )

        self.assertInspection(
            canonical,
            PayloadStatus.CANONICAL,
            ["alpha", "beta", "gamma"],
        )
        self.assertInspection(
            mapped,
            PayloadStatus.LEGACY_COMPATIBLE,
            ["alpha", "beta"],
        )

    def test_free_text_supports_wrapper_and_classifies_empty_answer(self):
        canonical = inspect_answer_payload("write_essay", "  Candidate answer  ")
        wrapped = inspect_answer_payload(
            "summarize_written_text",
            {"text": "Candidate summary"},
        )
        empty = inspect_answer_payload("write_from_dictation", {})

        self.assertInspection(
            canonical,
            PayloadStatus.CANONICAL,
            "Candidate answer",
        )
        self.assertInspection(
            wrapped,
            PayloadStatus.LEGACY_COMPATIBLE,
            "Candidate summary",
        )
        self.assertInspection(empty, PayloadStatus.UNANSWERED, "")

    def test_ambiguous_legacy_wrapper_is_invalid(self):
        result = inspect_answer_payload(
            "select_missing_word",
            {"answer": 10, "selected_id": 11},
        )

        self.assertEqual(result.status, PayloadStatus.INVALID)
        self.assertEqual(result.issues[0].code, "ambiguous_answer_wrapper")
