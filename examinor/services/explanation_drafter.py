import json

from django.conf import settings

from .evaluator import get_openai_client


def _correct_answer_context(question):
    subsection = question.subsection.name

    if subsection == "fib_dropdown":
        return {
            "blanks": [
                {
                    "blank": subquestion.blank_number,
                    "correct": [
                        option.option_text
                        for option in subquestion.options.all()
                        if option.is_correct
                    ],
                }
                for subquestion in question.sub_questions.prefetch_related("options")
            ]
        }

    options = list(question.options.all())
    if subsection == "reorder_paragraphs":
        return {
            "correct_order": [
                option.option_text
                for option in sorted(
                    options,
                    key=lambda option: (option.order_position, option.id),
                )
            ]
        }

    if subsection == "fib_drag_drop":
        return {
            "blanks": [
                {
                    "blank": option.order_position,
                    "correct": option.option_text,
                }
                for option in sorted(
                    (
                        option
                        for option in options
                        if option.is_correct and option.order_position is not None
                    ),
                    key=lambda option: option.order_position,
                )
            ]
        }

    return {
        "correct_options": [
            option.option_text
            for option in options
            if option.is_correct
        ]
    }


def draft_question_explanation(question):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    payload = {
        "question_type": question.subsection.name,
        "question": question.text or question.name,
        "correct_answer": _correct_answer_context(question),
    }
    prompt = (
        "Write a concise educational explanation for this PTE Reading question. "
        "Explain why the supplied answer is correct using the passage, grammar, "
        "vocabulary, or logical sequence as appropriate. Do not discuss scoring, "
        "do not invent facts, and do not address a specific student. Return only "
        "the explanation in 2 to 4 sentences.\n\n"
        f"QUESTION DATA:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    completion = client.responses.create(
        model=settings.OPENAI_EVALUATION_MODEL,
        input=prompt,
    )
    explanation = (completion.output_text or "").strip()
    if not explanation:
        raise RuntimeError("OpenAI returned an empty explanation.")
    return explanation
