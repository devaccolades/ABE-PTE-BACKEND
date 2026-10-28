from functools import partial

from .schema import EvaluationCase, KeyAnswer


# Source: lecture on emotional stability. Rubric: form 2, content 4, grammar 2, spelling 2, vocabulary 2.
sst = partial(EvaluationCase, task="summarize_spoken_text", question_id=26, question_name="L-SST - Q1 - ATHIRA")
# Reference: "Chemical reactions occur when substances combine or change." (8 words)
dictation = partial(EvaluationCase, task="write_from_dictation", question_id=27, question_name="WFD - Q1 - ATHIRA")
blanks = partial(EvaluationCase, task="l_fill_in_blanks", question_id=31, question_name="L-FIB-Q1-ATHIRA")
multiple = partial(EvaluationCase, task="l_mc_multiple", question_id=28, question_name="L-MCQ-MA-Q1-ATHIRA")
single = partial(EvaluationCase, task="l_mc_single", question_id=36, question_name="L-MCQ-SA-Q1-ATHIRA")
summary = partial(EvaluationCase, task="highlight_correct_summary", question_id=33, question_name="L-HCS-Q1-ATHIRA")
missing_word = partial(EvaluationCase, task="select_missing_word", question_id=37, question_name="L-SMW-Q1-ATHIRA")
# Two incorrect words in the displayed transcript: "trained" and "Einstein".
highlight = partial(EvaluationCase, task="highlight_incorrect_words", question_id=38, question_name="L-HIW-Q1-ATHIRA")

FULL = (1, 1)
PARTIAL = (0.01, 0.99)

CASES = [
    sst(
        id="sst-good", label="faithful summary, 60 words",
        answer="The lecture explained that emotional stability differs between people. While some people value intense, roller-coaster experiences and the euphoria they bring, the speaker emphasised that a peaceful and stable mood is more important for happiness. The speaker concluded that the secret of happiness is moderation, avoiding too much strain and finding a balance between excitement and contentment in everyday life.",
        expect={"no_override": True, "traits": {"content": (3, 4)}},
        known_issue=(
            "By policy, a fidelity verdict below SOURCE_FIDELITY_MIN_CONFIDENCE fails the "
            "evaluation instead of passing it for review; seen as 'mixed' at 0.87. Decision pending."
        ),
    ),
    sst(
        id="sst-keywords", label="source keywords with little meaning",
        answer="The lecture was about emotion and happiness. The speaker talked about roller coaster and euphoria and strain. The speaker also talked about different people and their mood. There were many important points in the lecture and the speaker explained them clearly with examples, which was very interesting and useful for the listeners to understand the topic.",
        expect={"traits": {"content": (0, 2)}},
    ),
    sst(
        id="sst-off-topic", label="summary of a different lecture",
        answer="The lecture discussed the history of the printing press and how it changed European society. The speaker explained that cheaper books spread literacy, allowed scientific ideas to travel faster and weakened the control of religious authorities over information. Finally, the speaker argued that the internet is having a similar effect today by making knowledge available to everyone at low cost.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    sst(
        id="sst-75-words", label="good content but 75 words", trainer_ref="SST-003",
        answer="The lecture explained that emotional stability differs greatly between different people. While some people value intense, roller-coaster experiences and the strong euphoria they bring, the speaker emphasised that a peaceful and stable mood is actually more important for long-term happiness. The speaker concluded that the real secret of happiness is moderation, which means avoiding too much strain and finding a sensible balance between excitement and contentment in everyday life, work and personal relationships today.",
        expect={"zero": True, "override": "company_strict_form"},
    ),
    dictation(id="wfd-exact", label="exact sentence", answer=KeyAnswer("exact"), expect={"ratio": FULL}),
    dictation(
        id="wfd-lowercase", label="lowercase without punctuation",
        answer=KeyAnswer("lowercase_no_punctuation"), expect={"ratio": FULL},
    ),
    dictation(
        id="wfd-missing-word", label="last word missing (7 of 8)",
        answer=KeyAnswer("missing_last_word"), expect={"ratio": (0.87, 0.88)},
    ),
    dictation(
        id="wfd-typo", label="one misspelled word (7 of 8)",
        answer=KeyAnswer("one_typo"), expect={"ratio": (0.87, 0.88)},
    ),
    dictation(
        id="wfd-three-words", label="only the first three words", trainer_ref="WFD-001",
        answer="Chemical reactions occur", expect={"ratio": (0.375, 0.375)},
    ),
    dictation(id="wfd-unanswered", label="empty submission", answer="", expect={"zero": True}),
    blanks(id="lfib-correct", label="all blanks correct", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    blanks(
        id="lfib-uppercase", label="correct words typed in capitals",
        answer=KeyAnswer("correct_uppercase"), expect={"ratio": FULL},
    ),
    blanks(
        id="lfib-first-only", label="first of four blanks correct",
        answer=KeyAnswer("first_correct"), expect={"ratio": (0.25, 0.25)},
    ),
    blanks(id="lfib-wrong", label="every blank wrong", answer=KeyAnswer("wrong"), expect={"zero": True}),
    multiple(id="lmcm-correct", label="all correct options", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    multiple(
        id="lmcm-one-correct", label="one correct option only",
        answer=KeyAnswer("one_correct"), expect={"ratio": PARTIAL},
    ),
    multiple(
        id="lmcm-plus-wrong", label="all correct plus one wrong (penalised)",
        answer=KeyAnswer("correct_plus_wrong"), expect={"ratio": PARTIAL},
    ),
    multiple(id="lmcm-wrong", label="only wrong options", answer=KeyAnswer("wrong"), expect={"zero": True}),
    single(id="lmcs-correct", label="correct option", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    single(id="lmcs-wrong", label="wrong option", answer=KeyAnswer("wrong"), expect={"zero": True}),
    single(id="lmcs-unanswered", label="nothing selected", answer=None, expect={"zero": True}),
    summary(id="hcs-correct", label="correct summary", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    summary(id="hcs-wrong", label="wrong summary", answer=KeyAnswer("wrong"), expect={"zero": True}),
    missing_word(id="smw-correct", label="correct word", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    missing_word(id="smw-wrong", label="wrong word", answer=KeyAnswer("wrong"), expect={"zero": True}),
    highlight(
        id="hiw-correct", label="both incorrect words highlighted",
        answer=KeyAnswer("correct"), expect={"ratio": FULL},
    ),
    highlight(
        id="hiw-plus-extra", label="both incorrect words plus one correct word (penalised)",
        answer=KeyAnswer("correct_plus_extra"), expect={"ratio": PARTIAL},
    ),
    highlight(
        id="hiw-only-extra", label="only a correct word highlighted",
        answer=KeyAnswer("only_extra"), expect={"zero": True},
    ),
    highlight(
        id="hiw-unanswered", label="nothing highlighted",
        answer={"selections": []}, expect={"zero": True},
    ),
]
