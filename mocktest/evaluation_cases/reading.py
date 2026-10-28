from functools import partial

from .schema import EvaluationCase, KeyAnswer


single = partial(EvaluationCase, task="mc_single", question_id=32, question_name="MCSAR6452-1")
multiple = partial(EvaluationCase, task="mc_multiple", question_id=13, question_name="MCMAR6452-1")
dropdown = partial(EvaluationCase, task="fib_dropdown", question_id=90, question_name="RFIB Drop Down 1 SALINI")
# Four blanks, four distractors.
drag_drop = partial(EvaluationCase, task="fib_drag_drop", question_id=100, question_name="R-FIB-Q1-DRAG-ATHIRA")
reorder = partial(EvaluationCase, task="reorder_paragraphs", question_id=30, question_name="ROP6452-1")

FULL = (1, 1)
PARTIAL = (0.01, 0.99)

CASES = [
    single(id="mcs-correct", label="correct option", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    single(id="mcs-wrong", label="wrong option", answer=KeyAnswer("wrong"), expect={"zero": True}),
    single(id="mcs-unanswered", label="nothing selected", answer=None, expect={"zero": True}),
    multiple(id="mcm-correct", label="all correct options", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    multiple(
        id="mcm-one-correct", label="one correct option only",
        answer=KeyAnswer("one_correct"), expect={"ratio": PARTIAL},
    ),
    multiple(
        id="mcm-plus-wrong", label="all correct plus one wrong (penalised)",
        answer=KeyAnswer("correct_plus_wrong"), expect={"ratio": PARTIAL},
    ),
    multiple(id="mcm-wrong", label="only wrong options", answer=KeyAnswer("wrong"), expect={"zero": True}),
    multiple(id="mcm-unanswered", label="nothing selected", answer=[], expect={"zero": True}),
    dropdown(id="fibd-correct", label="every blank correct", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    dropdown(
        id="fibd-first-only", label="first blank correct, rest wrong",
        answer=KeyAnswer("first_correct"), expect={"ratio": PARTIAL},
    ),
    dropdown(id="fibd-wrong", label="every blank wrong", answer=KeyAnswer("wrong"), expect={"zero": True}),
    drag_drop(id="fibdd-correct", label="every word placed correctly", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    drag_drop(
        id="fibdd-first-only", label="only the first blank filled (1 of 4)",
        answer=KeyAnswer("first_correct"), expect={"ratio": (0.25, 0.25)},
    ),
    drag_drop(id="fibdd-wrong", label="correct words in the wrong blanks", answer=KeyAnswer("wrong"), expect={"zero": True}),
    drag_drop(id="fibdd-unanswered", label="nothing placed", answer={}, expect={"zero": True}),
    reorder(id="rop-correct", label="correct order", answer=KeyAnswer("correct"), expect={"ratio": FULL}),
    reorder(
        id="rop-swap-first-two", label="first two paragraphs swapped",
        answer=KeyAnswer("swap_first_two"), expect={"ratio": (0, 0.99)},
    ),
    reorder(id="rop-reversed", label="order reversed", answer=KeyAnswer("reversed"), expect={"zero": True}),
]
