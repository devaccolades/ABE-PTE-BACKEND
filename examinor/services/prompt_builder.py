def build_prompt(question, response_text):
    rubric = question.rubric.criteria if question.rubric else {}
    rubric_text = ", ".join([f"{k} ({v} marks)" for k, v in rubric.items()])

    return f"""
You are a certified PTE examiner.

Question: {question.prompt}

Candidate's Answer:
{response_text}

Evaluate the response based on:
{rubric_text}.

Output a JSON object with:
- overall_score
- breakdown (each criterion)
- feedback (a short paragraph with strengths and improvements)
"""
