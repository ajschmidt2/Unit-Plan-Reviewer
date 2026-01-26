import base64
import json
from typing import List
from openai import OpenAI
from .schemas import ReviewResult

SYSTEM_INSTRUCTIONS = """
You are an accessibility plan reviewer for UNIT plans.
Flag likely issues when uncertain and assign confidence levels.
Do not invent measurements.
Return STRICT JSON matching the schema.
"""

def _png_to_data_url(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"

def _extract_output_text(response) -> str | None:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text
    if hasattr(response, "choices") and response.choices:
        return response.choices[0].message.content
    if hasattr(response, "output"):
        for item in response.output:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) in {"output_text", "text"}:
                    return content.text
    return None

def _coerce_json(text: str) -> dict:
    if not text or not isinstance(text, str):
        raise ValueError("LLM response was empty.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise ValueError(f"LLM response was not valid JSON: {text[:2000]}")

def run_review(api_key, project_name, ruleset, scale_note, page_payloads):
    client = OpenAI(api_key=api_key)

    content = [
        {"type": "text", "text": f"Project: {project_name}\nRuleset: {ruleset}\nScale: {scale_note}"}
    ]

    for p in page_payloads:
        content.append({"type": "text", "text": f"PAGE {p['page_index']} — {p['page_label']}"})
        if p.get("extra_text"):
            content.append({"type": "text", "text": p["extra_text"][:4000]})
        content.append({
            "type": "image_url",
            "image_url": {"url": _png_to_data_url(p["png_bytes"])}
        })

    if hasattr(client, "responses"):
        resp = client.responses.create(
            model="gpt-4.1-mini",
            instructions=SYSTEM_INSTRUCTIONS,
            input=[{"role": "user", "content": content}],
            response_format={"type": "json_object"}
        )
    else:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"}
        )
    output_text = _extract_output_text(resp)
    payload = _coerce_json(output_text)

    return ReviewResult.model_validate(payload)
