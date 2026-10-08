from django.test import SimpleTestCase

from mocktest.services.audio_analysis import analyse_speech


def timestamps(words, *, word_seconds=0.35, gaps=None):
    gaps = gaps or {}
    current = 0.0
    result = []
    for index, word in enumerate(words.split()):
        current += gaps.get(index, 0.0)
        result.append({"word": word, "start": current, "end": current + word_seconds})
        current += word_seconds
    return result


class SpeechAnalysisTests(SimpleTestCase):
    def test_fluent_delivery_uses_measured_timing_and_recognition_evidence(self):
        text = "clear continuous speech should receive strong measurable evidence today"
        result = analyse_speech(
            text,
            timestamps(text),
            4.0,
            [{"start": 0, "end": 4, "avg_logprob": -0.08, "no_speech_prob": 0.01}],
        )

        self.assertEqual(result["analysis_version"], "speech-evidence-v2")
        self.assertEqual(result["fluency_analysis"]["overall_score_0_to_5"], 5)
        self.assertEqual(result["pronunciation_analysis"]["overall_score_0_to_5"], 5)

    def test_fillers_repetition_and_pauses_reduce_fluency(self):
        text = "um we we need to to discuss this issue carefully"
        result = analyse_speech(
            text,
            timestamps(text, gaps={3: 1.4, 7: 1.0}),
            8.0,
            [{"start": 0, "end": 8, "avg_logprob": -0.45, "no_speech_prob": 0.02}],
        )
        fluency = result["fluency_analysis"]

        self.assertEqual(fluency["num_hesitations"], 1)
        self.assertEqual(fluency["num_repetitions"], 2)
        self.assertGreaterEqual(fluency["num_false_starts"], 2)
        self.assertLessEqual(fluency["overall_score_0_to_5"], 2)

    def test_very_slow_short_response_cannot_receive_high_fluency(self):
        text = "among heating systems to be superior"
        result = analyse_speech(text, timestamps(text), 10.0)

        self.assertEqual(result["fluency_analysis"]["overall_score_0_to_5"], 1)
        self.assertIsNone(result["pronunciation_analysis"]["overall_score_0_to_5"])

