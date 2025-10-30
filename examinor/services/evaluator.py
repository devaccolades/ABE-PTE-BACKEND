import openai
import json
from django.conf import settings
from .prompt_builder import build_prompt

openai.api_key = settings.OPENAI_API_KEY

def evaluate_with_openai(question, response_text):
    prompt = build_prompt(question, response_text)

    completion = openai.chat.completions.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    try:
        result = json.loads(completion.choices[0].message.content)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
