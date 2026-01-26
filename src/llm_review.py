import base64
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

    resp = client.responses.create(
        model="gpt-4.1-mini",
        instructions=SYSTEM_INSTRUCTIONS,
        input=[{"role": "user", "content": content}],
        response_format={"type": "json_object"}
    )

    return ReviewResult.model_validate_json(resp.output_text)
