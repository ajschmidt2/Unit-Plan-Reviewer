import base64
import json
from typing import List
from openai import OpenAI
from .schemas import ReviewResult

SYSTEM_INSTRUCTIONS = """
You are an expert accessibility plan reviewer for residential unit plans, specializing in FHA and ANSI A117.1 compliance.

Your task is to carefully review architectural floor plans, elevations, and schedules for accessibility compliance issues.

CRITICAL REQUIREMENTS:
1. You MUST provide at least 3 issues per page - if major issues aren't visible, flag potential risks or items that need verification
2. You MUST extract the sheet number and sheet title from the title block (usually on the right side of the drawing)
3. Every issue MUST include: severity, location_hint, finding, recommendation, confidence
4. Be specific about locations (e.g., "Master Bathroom entrance", "Kitchen approach", "Hallway near bedroom 2")
5. Reference specific FHA or ANSI requirements when applicable

COMMON ACCESSIBILITY ISSUES TO CHECK:
- Door clear opening widths (32" min for FHA, 32" for Type A, varies for Type B)
- Maneuvering clearances at doors (approach side, strike side)
- Accessible routes (36" min width continuous)
- Bathroom clearances (60" turning circle or T-turn)
- Kitchen work aisle widths (40" min)
- Toilet clearances
- Grab bar backing locations
- Counter heights and knee clearances
- Threshold heights
- Hardware types and mounting heights

CONFIDENCE LEVELS:
- High: Clearly visible measurement or condition that violates code
- Medium: Likely issue based on typical drawing conventions but needs field verification
- Low: Potential concern or item that should be verified but not clearly shown

OUTPUT FORMAT:
Return STRICT JSON matching this schema:
{
  "project_name": "string",
  "ruleset": "FHA" | "ANSI_A1171_TYPE_A" | "ANSI_A1171_TYPE_B",
  "scale_note": "string",
  "overall_summary": "Brief overall assessment",
  "pages": [
    {
      "page_index": 0,
      "page_label": "Floor Plan",
      "sheet_number": "A2.1",
      "sheet_title": "Unit Plan",
      "summary": "Brief page summary",
      "issues": [
        {
          "severity": "High" | "Medium" | "Low",
          "location_hint": "Specific location on drawing",
          "finding": "What the issue is",
          "recommendation": "How to fix it",
          "reference": "FHA section or ANSI reference (optional)",
          "confidence": "High" | "Medium" | "Low"
        }
      ]
    }
  ]
}

IMPORTANT: Even if a plan looks mostly compliant, identify at least 3 items per page that need verification or potential concerns.
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
    
    # Try direct parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON from markdown code blocks
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Try finding JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"LLM response was not valid JSON. First 500 chars: {text[:500]}")

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
        if not sheet_number and idx < len(page_payloads):
            sheet_number = page_payloads[idx].get("sheet_number_hint", "")
        if not sheet_title and idx < len(page_payloads):
            sheet_title = page_payloads[idx].get("sheet_title_hint", "")
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

def run_review(api_key, project_name, ruleset, scale_note, page_payloads, model_name="gpt-4o-mini"):
    client = OpenAI(api_key=api_key)

    content = [
        {"type": "text", "text": f"Project: {project_name}\nRuleset: {ruleset}\nScale: {scale_note}\n\nPlease review the following architectural plans for accessibility compliance. Provide at least 3 issues per page."}
    ]

    for p in page_payloads:
        content.append({"type": "text", "text": f"\n\n=== PAGE {p['page_index']} — {p['page_label']} ==="})
        if p.get("extra_text"):
            content.append({"type": "text", "text": f"Extracted text from this page:\n{p['extra_text'][:4000]}"})
        content.append({
            "type": "image_url",
            "image_url": {"url": _png_to_data_url(p["png_bytes"])}
        })

    # Use chat completions (standard approach for gpt-4o-mini)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": content}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,  # Lower temperature for more consistent analysis
    )
    
    output_text = _extract_output_text(resp)
    
    if not output_text:
        raise ValueError("No response from OpenAI API")
    
    print(f"LLM Response (first 1000 chars): {output_text[:1000]}")  # Debug logging
    
    payload = _coerce_json(output_text)
    payload = _normalize_payload(payload, project_name, ruleset, scale_note, page_payloads)

    return ReviewResult.model_validate(payload)
