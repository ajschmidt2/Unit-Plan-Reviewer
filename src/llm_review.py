import base64
import json
import re
from typing import List, Dict
from openai import OpenAI
from .schemas import ReviewResult

# Page-specific analysis guides
PAGE_TYPE_ANALYSIS = {
    "Floor Plan": {
        "focus_areas": [
            "Door clear opening widths at all entries (32\" min for FHA)",
            "Accessible route widths (36\" minimum continuous)",
            "Maneuvering clearances at doors (pull side, push side, latch side)",
            "Bathroom turning spaces (60\" diameter circle or T-turn)",
            "Kitchen work aisle width (40\" minimum)",
            "Hallway widths throughout unit",
            "Bedroom approach and maneuvering space",
        ],
        "critical_measurements": [
            "Door openings", "Route widths", "Bathroom clearances", "Kitchen clearances"
        ]
    },
    "Interior Elevation": {
        "focus_areas": [
            "Grab bar heights and locations (33-36\" AFF typical)",
            "Counter heights (34\" max for accessible counters)",
            "Mirror heights (bottom edge 40\" max AFF)",
            "Electrical outlet and switch heights",
            "Window sill heights (operable windows 44\" max)",
            "Shower controls locations and heights (38-48\" AFF)",
        ],
        "critical_measurements": [
            "Grab bar mounting heights", "Counter heights", "Control heights"
        ]
    },
    "Door Schedule": {
        "focus_areas": [
            "Clear opening widths (should be 32\" minimum for FHA)",
            "Door hardware specifications (lever handles required)",
            "Threshold heights (1/2\" max for exterior, 1/4\" max interior)",
            "Door types and swing directions",
        ],
        "critical_measurements": [
            "Clear opening width", "Threshold height"
        ]
    },
    "Reflected Ceiling Plan": {
        "focus_areas": [
            "Ceiling height changes",
            "Protruding objects below 80\" (light fixtures, soffits)",
            "Light fixture heights and protrusions from wall",
        ],
        "critical_measurements": [
            "Clearance heights", "Protrusion distances"
        ]
    },
    "Other": {
        "focus_areas": [
            "General accessibility compliance",
            "Clear dimensions and measurements",
            "Compliance with specified ruleset"
        ],
        "critical_measurements": []
    }
}

TAG_TO_PAGE_TYPE = {
    "Interior Elevations": "Interior Elevation",
    "RCP / Ceiling": "Reflected Ceiling Plan",
    "Notes / Code": "Other",
    "Details / Sections": "Other",
}

def _normalize_tag(tag: str) -> str:
    if tag in TAG_TO_PAGE_TYPE:
        return TAG_TO_PAGE_TYPE[tag]
    return tag

def build_enhanced_prompt(page_label: str, ruleset: str) -> str:
    """Build a targeted prompt based on page type and ruleset"""
    normalized = _normalize_tag(page_label)
    analysis_guide = PAGE_TYPE_ANALYSIS.get(normalized, PAGE_TYPE_ANALYSIS["Other"])
    
    prompt = f"""
For this {page_label}, focus your accessibility review on these specific areas:

FOCUS AREAS FOR {page_label.upper()}:
"""
    for i, area in enumerate(analysis_guide["focus_areas"], 1):
        prompt += f"\n{i}. {area}"
    
    prompt += f"""

CRITICAL MEASUREMENTS TO VERIFY:
"""
    for measurement in analysis_guide["critical_measurements"]:
        prompt += f"\n- {measurement}"
    
    prompt += f"""

MEASUREMENT EXTRACTION:
- Actively look for dimension lines, text labels, and scale bars on the drawing
- Report actual measurements you can read: "Door A: 32\" clear opening (measured from dimension line)"
- If dimensions aren't clearly labeled, note: "Door width not dimensioned - requires verification"
- Include measurements in your findings when available
- For each issue, try to provide the measured value vs. required value

RULESET REQUIREMENTS ({ruleset}):
"""
    
    if ruleset == "FHA":
        prompt += """
- Doors: 32" clear opening (nominal 2'10" door)
- Routes: 36" minimum width continuous
- Bathrooms: 60" turning circle OR 60" T-turn space
- Kitchen: 40" minimum work aisle between opposing base cabinets
- Maneuvering clearances: 18" pull side, 0" push side minimum (varies by approach)
- Hardware: Lever handles or other operable with one hand, no tight grasping
"""
    elif "TYPE_A" in ruleset:
        prompt += """
- Doors: 32" clear opening minimum
- Routes: 36" minimum width continuous
- Bathrooms: 60" turning circle required (T-turn not acceptable)
- Kitchen: 40" minimum work aisle, accessible sink and cooktop required
- Enhanced clearances per ANSI A117.1 Type A
- Grab bar blocking required at all toilet and bathtub/shower locations
"""
    elif "TYPE_B" in ruleset:
        prompt += """
- Doors: 32" clear opening (31.75" acceptable at bathroom doors)
- Routes: 36" minimum width
- Bathrooms: Reinforced grab bar backing required (actual bars not required initially)
- Kitchen: 40" work aisle if U-shaped layout
- Per ANSI A117.1 Type B (less stringent than Type A)
- Usable doors, accessible routes, and reinforcement only
"""
    
    return prompt

SYSTEM_INSTRUCTIONS = """
You are an expert accessibility plan reviewer for residential unit plans, specializing in FHA and ANSI A117.1 compliance.

Your task is to carefully review architectural floor plans, elevations, and schedules for accessibility compliance issues.

CRITICAL REQUIREMENTS:
1. You MUST list ALL distinct issues you can identify on each page/region. There is NO MAXIMUM.
   - Do NOT summarize into a short list.
   - Do NOT stop at 5–7 items.
   - If you see multiple doors/rooms/conditions, list each as its own issue.
   - If a critical dimension is missing, add a separate "Needs verification" issue for that condition.
   - Typical unit plan sheets should produce 10–25 issues when details are visible; combo sheets may produce more.
2. You MUST extract the sheet number and sheet title from the title block (usually on the right side of the drawing)
3. Every issue MUST include: severity, location_hint, finding, recommendation, confidence
4. Be specific about locations (e.g., "Master Bathroom entrance", "Kitchen approach", "Hallway near bedroom 2")
5. Reference specific FHA or ANSI requirements when applicable
6. EXTRACT AND REPORT ACTUAL MEASUREMENTS whenever visible on the drawings
7. Each issue location_hint MUST include "Page {page_index} / {region tag}" and anchor text if provided

MEASUREMENT REPORTING:
- Look for dimension strings on the drawings (e.g., "3'-0\"", "32\"", "5'6\"")
- Report measurements in your findings: "Measured: 34\", Required: 36\""
- Include measurement field with just the extracted value when found
- If you cannot read a critical dimension, explicitly note this as an issue

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
- High: Clearly visible measurement or condition that violates code, dimension is labeled
- Medium: Likely issue based on typical drawing conventions but needs field verification
- Low: Potential concern or item that should be verified but not clearly shown on drawing

OUTPUT FORMAT:
Return STRICT JSON matching this schema:
{
  "project_name": "string",
  "ruleset": "FHA" | "ANSI_A1171_TYPE_A" | "ANSI_A1171_TYPE_B",
  "scale_note": "string",
  "overall_summary": "Brief overall assessment of all pages reviewed",
  "pages": [
    {
      "page_index": 0,
      "page_label": "Combo Sheet" | "Floor Plan" | "Interior Elevation" | "Door Schedule" | "Reflected Ceiling Plan" | "Other",
      "sheet_id": "A2.1",
      "sheet_title": "Unit Plan",
      "summary": "Brief page summary",
      "issues": [
        {
          "severity": "High" | "Medium" | "Low",
          "location_hint": "Specific location on drawing",
          "finding": "What the issue is, including measurements if visible",
          "recommendation": "How to fix it",
          "reference": "FHA section or ANSI reference (optional)",
          "confidence": "High" | "Medium" | "Low",
          "measurement": "32\" (if you extracted a measurement)"
        }
      ]
    }
  ]
}

IMPORTANT: If a plan looks mostly compliant, keep scanning and add verification issues covering doors, routes, bathrooms, kitchens, thresholds, and hardware. Do NOT stop early.
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
    cleaned = text.strip()

    def _strip_trailing_commas(payload: str) -> str:
        return re.sub(r",\s*([}\]])", r"\1", payload)

    decoder = json.JSONDecoder()

    # Try direct parsing first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try raw decode to ignore trailing non-JSON content
    try:
        parsed, _ = decoder.raw_decode(cleaned)
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON from markdown code blocks
    if "```json" in cleaned:
        start = cleaned.find("```json") + 7
        end = cleaned.find("```", start)
        if end > start:
            try:
                return json.loads(cleaned[start:end].strip())
            except json.JSONDecodeError:
                pass
    
    # Try finding JSON object boundaries
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        extracted = cleaned[start:end + 1].strip()
        for candidate in (extracted, _strip_trailing_commas(extracted)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    parsed, _ = decoder.raw_decode(candidate)
                    return parsed
                except json.JSONDecodeError:
                    continue
    
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
    page_hints = {}
    for payload_item in page_payloads:
        if not isinstance(payload_item, dict):
            continue
        hint_index = payload_item.get("page_index")
        if hint_index is None or hint_index in page_hints:
            continue
        page_hints[hint_index] = {
            "page_label": payload_item.get("page_label", "Combo Sheet"),
            "sheet_id": payload_item.get("sheet_id_hint") or payload_item.get("sheet_number_hint", ""),
            "sheet_title": payload_item.get("sheet_title_hint", ""),
        }
    for idx, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        payload_fallback = page_payloads[idx] if idx < len(page_payloads) else {}
        if page.get("page_index") is None:
            page_index = payload_fallback.get("page_index", idx)
        else:
            page_index = page.get("page_index")
        hint = page_hints.get(page_index, {})
        if page.get("page_label") is None:
            payload_label = payload_fallback.get("page_label", "Combo Sheet")
            page_label = hint.get("page_label") or payload_label
        else:
            page_label = page.get("page_label")
        sheet_id = page.get("sheet_id") or page.get("sheet_number", "")
        sheet_title = page.get("sheet_title", "")
        if not sheet_id:
            sheet_id = (
                hint.get("sheet_id")
                or payload_fallback.get("sheet_id_hint", "")
                or payload_fallback.get("sheet_number_hint", "")
            )
        if not sheet_title:
            sheet_title = hint.get("sheet_title") or payload_fallback.get("sheet_title_hint", "")
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
                    "measurement": issue.get("measurement"),
                }
            )
        normalized_pages.append(
            {
                "page_index": page_index,
                "page_label": page_label,
                "sheet_id": sheet_id,
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
        {"type": "text", "text": f"""Project: {project_name}
Ruleset: {ruleset}
Scale: {scale_note}

COMPREHENSIVE REVIEW REQUIREMENTS:
- List ALL distinct issues you can find. There is NO MAXIMUM.
- Do NOT stop at 5–7 items.
- If there are multiple doors/rooms/conditions, evaluate each separately.
- If a required dimension is not shown, add a separate issue: "Not dimensioned — requires verification."
- If fewer than 10 issues appear on a typical unit plan sheet, re-check for missed items.

Return strict JSON only.
"""}
    ]

    for p in page_payloads:
        page_label = p.get("page_label", "Combo Sheet")
        region_tag = p.get("tag", page_label)
        tag_label = _normalize_tag(region_tag)
        enhanced_prompt = build_enhanced_prompt(tag_label, ruleset)

        content.append({"type": "text", "text": f"\n\n=== PAGE {p['page_index']} — {page_label} ==="})
        content.append({"type": "text", "text": f"REGION TAG: {region_tag}"})
        content.append({"type": "text", "text": f"Scale note for this region: {p.get('scale_note', scale_note)}"})
        if p.get("anchor_text"):
            content.append({"type": "text", "text": f"Anchor: {p['anchor_text']}"})
        content.append({"type": "text", "text": enhanced_prompt})

        if p.get("extra_text"):
            content.append({"type": "text", "text": f"Extracted text from this page:\n{p['extra_text'][:8000]}"})

        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _png_to_data_url(p["png_bytes"])},
            }
        )

    # Use chat completions (standard approach for gpt-4o-mini)
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": content}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,  # Lower temperature for more consistent analysis
        max_tokens=8000,
    )
    
    output_text = _extract_output_text(resp)
    
    if not output_text:
        raise ValueError("No response from OpenAI API")
    
    print("LLM output char length:", len(output_text))
    print("LLM Response (first 1000 chars):", output_text[:1000])
    print("LLM Response (last 400 chars):", output_text[-400:])
    
    payload = _coerce_json(output_text)
    payload = _normalize_payload(payload, project_name, ruleset, scale_note, page_payloads)

    return ReviewResult.model_validate(payload)
