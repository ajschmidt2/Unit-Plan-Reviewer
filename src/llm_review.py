import base64
import json
from typing import List
from openai import OpenAI
from .schemas import ReviewResult

SYSTEM_INSTRUCTIONS = """
You are an accessibility plan reviewer for UNIT plans.
Flag likely issues when uncertain and assign confidence levels.
Do not invent measurements.
Extract sheet number and sheet title from the drawing title block (usually right side).
If a field is unknown, use an empty string (never omit required fields).
Provide at least 3 issues per page; if few are visible, include low-confidence potential risks.
Use clear, actionable findings and recommendations tied to FHA/ANSI rules.
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

def _coerce_choice(value: str | None, allowed: set[str], fallback: str) -> str:
    if value in allowed:
        return value
    return fallback

def _normalize_payload(payload: dict, project_name, ruleset, scale_note, page_payloads):
    if not isinstance(payload, dict):
        raise ValueError("LLM response was not an object.")
    data = dict(payload)
    data.setdefault("project_name", project_name or "")
    data.setdefault("ruleset", ruleset)
    data.setdefault("scale_note", scale_note or "")
    data.setdefault("overall_summary", "")

    pages = data.get("pages")
    if not isinstance(pages, list):
        pages = []
    normalized_pages = []
    for idx, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        if page.get("page_index") is None:
            page_index = page_payloads[idx].get("page_index", idx) if idx < len(page_payloads) else idx
        else:
            page_index = page.get("page_index")
        if page.get("page_label") is None:
            page_label = page_payloads[idx].get("page_label", "") if idx < len(page_payloads) else ""
        else:
            page_label = page.get("page_label")
        sheet_number = page.get("sheet_number", "")
        sheet_title = page.get("sheet_title", "")
        summary = page.get("summary", "")
        issues = page.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        normalized_issues = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = _coerce_choice(issue.get("severity"), {"High", "Medium", "Low"}, "Low")
            confidence = _coerce_choice(issue.get("confidence"), {"High", "Medium", "Low"}, "Low")
            normalized_issues.append(
                {
                    "severity": severity,
                    "location_hint": issue.get("location_hint", ""),
                    "finding": issue.get("finding", ""),
                    "recommendation": issue.get("recommendation", ""),
                    "reference": issue.get("reference"),
                    "confidence": confidence,
                }
            )
        normalized_pages.append(
            {
                "page_index": page_index,
                "page_label": page_label,
                "sheet_number": sheet_number,
                "sheet_title": sheet_title,
                "summary": summary,
                "issues": normalized_issues,
            }
        )
    data["pages"] = normalized_pages
    data["ruleset"] = _coerce_choice(data.get("ruleset"), {"FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"}, ruleset)
    return data

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
    payload = _normalize_payload(payload, project_name, ruleset, scale_note, page_payloads)

    return ReviewResult.model_validate(payload)
