def build_prompt(question, response_text):
    """
    Builds an AI evaluation prompt based on the question's subsection and rubric.
    """
    subsection = getattr(question, "subsection", None)
    rubric = subsection.rubric if subsection and subsection.rubric else {}

    rubric_text = ", ".join(
        [f"{criterion} ({details.get('max_score', '?')} marks)" for criterion, details in rubric.items()]
    ) if isinstance(rubric, dict) else "content, form, grammar, vocabulary"

    return f"""
You are a certified PTE examiner.

### Task Type:
{subsection.name.replace("_", " ").title() if subsection else "General Task"}

### Question:
{question.prompt}

### Candidate's Response:
{response_text}

### Evaluation Rubric:
Evaluate the response based on the following criteria:
{rubric_text}.

### Output:
Return a valid JSON object with:
{{
  "overall_score": <numeric>,
  "breakdown": {{
    "criterion_1": <score>,
    "criterion_2": <score>,
    ...
  }},
  "feedback": "short summary of strengths and areas for improvement"
}}
"""
