import base64
import json
import re
import importlib.util
from typing import List, Dict, Optional

from openai import OpenAI
from .schemas import ReviewResult

# --- Gemini imports ---
genai = None
gemini_types = None
if importlib.util.find_spec("google.genai") is not None:
    from google import genai
    from google.genai import types as gemini_types


# IMPROVED Page-specific analysis guides with code references
PAGE_TYPE_ANALYSIS = {
    "Floor Plan": {
        "focus_areas": [
            "Door clear opening widths at ALL entries (32\" min for FHA) [FHA 24 CFR 100.205(c)(3)(i)]",
            "Accessible route widths throughout (36\" continuous min) [FHA 24 CFR 100.205(c)(3)(ii)]",
            "Maneuvering clearances at EVERY door (18\" pull side min) [FHA 24 CFR 100.205(c)(3)(i)]",
            "Bathroom turning spaces (60\" circle or T-turn) [FHA 24 CFR 100.205(c)(3)(iii)]",
            "Kitchen work aisle width (40\" min between cabinets) [FHA Guidelines]",
            "Hallway widths throughout unit",
            "Bedroom approach and maneuvering space",
            "Threshold conditions at all transitions",
        ],
        "critical_measurements": [
            "Door openings (every single door)",
            "Route widths (all corridors)",
            "Bathroom clearances",
            "Kitchen clearances",
            "Maneuvering spaces at doors",
        ]
    },
    "Interior Elevation": {
        "focus_areas": [
            "Grab bar heights and locations (33-36\" AFF) [ANSI A117.1 Section 609.4]",
            "Counter heights (34\" max for accessible) [ANSI A117.1 Section 606.3]",
            "Mirror heights (bottom edge 40\" max AFF) [ANSI A117.1 Section 603.3]",
            "Electrical outlet heights (15\"-48\" AFF) [ANSI A117.1 Section 308]",
            "Window sill heights (operable 44\" max) [ANSI A117.1 Section 309.4]",
            "Shower control locations and heights (38-48\" AFF) [ANSI A117.1 Section 607.6]",
            "Lavatory knee clearance (27\" min height) [ANSI A117.1 Section 606.2]",
        ],
        "critical_measurements": [
            "Grab bar mounting heights",
            "Counter heights",
            "Control heights",
            "Mirror bottom edge height",
            "Knee clearance dimensions",
        ]
    },
    "Door Schedule": {
        "focus_areas": [
            "Clear opening widths for ALL doors (32\" min FHA) [FHA 24 CFR 100.205(c)(3)(i)]",
            "Door hardware specifications (lever required) [FHA 24 CFR 100.205(c)(3)(iv)]",
            "Threshold heights (1/2\" max exterior, 1/4\" interior) [ANSI A117.1 Section 404.2.5]",
            "Door types and swing directions (verify clearances)",
        ],
        "critical_measurements": [
            "Clear opening width (EVERY door)",
            "Threshold height",
        ]
    },
    "Reflected Ceiling Plan": {
        "focus_areas": [
            "Ceiling height changes (min 80\" clearance) [ANSI A117.1 Section 307.2]",
            "Protruding objects below 80\" (lights, soffits) [ANSI A117.1 Section 307.3]",
            "Light fixture heights and wall protrusions (4\" max) [ANSI A117.1 Section 307.3]",
        ],
        "critical_measurements": [
            "Clearance heights",
            "Protrusion distances",
        ]
    },
    "Other": {
        "focus_areas": [
            "General accessibility compliance with code citations",
            "Clear dimensions and measurements extraction",
            "Specific code section references for all findings",
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
    """Build a targeted prompt with emphasis on code citations and confidence"""
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

MEASUREMENT EXTRACTION INSTRUCTIONS (CRITICAL FOR HIGH CONFIDENCE):
1. Look carefully for dimension text on the drawing (e.g., "3'-0\"", "32\"", "5'6\"", "2-10")
2. If you see a dimension CLEARLY labeled:
   - Extract the EXACT text as printed
   - Set confidence = "High"
   - Include in "measurement" field
3. If you can estimate from scale bar or visual measurement:
   - Note "estimated from scale"
   - Set confidence = "Medium"
4. If dimension is NOT visible or unclear:
   - State "Not dimensioned on plan"
   - Set confidence = "Low"
   - Add recommendation to verify in field
5. ALWAYS include the "measurement" field (even if "Not dimensioned")

CODE REFERENCE REQUIREMENTS (100% MANDATORY):
EVERY single issue MUST cite a specific code section with number.
Do NOT use generic references like "FHA" or "ANSI" alone.

Examples of CORRECT references:
✓ "FHA 24 CFR 100.205(c)(3)(i)"
✓ "ANSI A117.1 Section 404.2.3"
✓ "ICC/ANSI A117.1-2017 Section 604.3"

Examples of WRONG references:
✗ "FHA requirements"
✗ "ANSI standards"
✗ "Code compliance"

"""

    if ruleset == "FHA":
        prompt += """
FHA CODE REFERENCES (Fair Housing Act - 24 CFR 100.205):
- Doors (32" clear): FHA 24 CFR 100.205(c)(3)(i)
- Routes (36" wide): FHA 24 CFR 100.205(c)(3)(ii)
- Bathroom turning (60" circle/T): FHA 24 CFR 100.205(c)(3)(iii)
- Kitchen aisle (40" min): FHA Fair Housing Design Manual Section 4.4
- Maneuvering (18" pull): FHA 24 CFR 100.205(c)(3)(i)
- Hardware (operable one-hand): FHA 24 CFR 100.205(c)(3)(iv)
- Thresholds (1/2" max): FHA Fair Housing Design Manual Section 3.7

CONFIDENCE STANDARDS FOR FHA:
- HIGH: Dimension is labeled and clearly visible on plan (e.g., you see "2'-10\"" marked on door)
- MEDIUM: You can measure using scale bar but no direct dimension label shown
- LOW: Critical dimension is missing, unclear, or requires field verification
"""
    elif "TYPE_A" in ruleset:
        prompt += """
ANSI A117.1 TYPE A CODE REFERENCES (ICC/ANSI A117.1-2017):
- Doors (32" clear): ANSI A117.1 Section 1003.5
- Routes (36" continuous): ANSI A117.1 Section 1003.3
- Bathroom turning (60" circle only): ANSI A117.1 Section 1003.12.2
- Kitchen (40" aisle, accessible fixtures): ANSI A117.1 Section 1003.12.3
- Toilet centerline (18" to wall): ANSI A117.1 Section 1004.11.3.1.1
- Toilet clearance (56" depth): ANSI A117.1 Section 1004.11.3.1.1
- Grab bar blocking: ANSI A117.1 Section 1003.12.5
- Counter heights (34" max): ANSI A117.1 Section 1003.12.4.1

CONFIDENCE STANDARDS FOR TYPE A:
- HIGH: Dimension clearly visible and readable on plan drawings
- MEDIUM: Can infer from context or typical dimensions but not explicitly labeled
- LOW: Requires field verification or dimension not shown on drawings
"""
    elif "TYPE_B" in ruleset:
        prompt += """
ANSI A117.1 TYPE B CODE REFERENCES (ICC/ANSI A117.1-2017):
- Doors (32" clear, 31.75" bath OK): ANSI A117.1 Section 1004.5
- Routes (36" min width): ANSI A117.1 Section 1004.3
- Bathroom reinforcement: ANSI A117.1 Section 1004.11.3
- Kitchen aisle (40" if U-shaped): ANSI A117.1 Section 1004.12.2
- Thresholds (1/2" exterior, 1/4" interior): ANSI A117.1 Section 1004.5.1

Note: Type B is less stringent than Type A - focuses on adaptability and reinforcement

CONFIDENCE STANDARDS FOR TYPE B:
- HIGH: Reinforcement locations clearly marked, dimensions visible
- MEDIUM: Can infer compliance from typical construction details
- LOW: Cannot verify without field inspection or construction documents
"""

    prompt += """

QUALITY CHECKLIST BEFORE SUBMITTING (CRITICAL):
1. ✅ EVERY issue includes: severity, location_hint, finding, recommendation, reference, confidence, measurement
2. ✅ Code references include SPECIFIC section numbers (not just "FHA" or "ANSI")
3. ✅ Measurements extracted when visible OR noted as "Not dimensioned"
4. ✅ Confidence is HIGH when dimensions are clearly visible on drawings
5. ✅ At least 50% of issues should be HIGH confidence if drawings have dimension labels
6. ✅ Found ALL issues - typical floor plan should have 10-20 issues minimum

BEFORE YOU RETURN YOUR RESPONSE, VERIFY:
- % of HIGH confidence issues (target: 50%+)
- % of issues with code references (target: 100%)
- % of issues with measurements (target: 100% - either extracted or "Not dimensioned")
- Total issue count (floor plan should be 10-20, not 5-7)

If you have < 50% HIGH confidence, re-examine drawings for visible dimensions.
If any issue lacks a code reference, add the specific code section.
"""

    return prompt


# IMPROVED System instructions with emphasis on quality
SYSTEM_INSTRUCTIONS = """
You are an expert accessibility plan reviewer specializing in FHA and ANSI A117.1 compliance.

CRITICAL OUTPUT QUALITY REQUIREMENTS:

1. CODE REFERENCES (100% MANDATORY):
   EVERY issue MUST include a specific code reference with section number.

   Correct format examples:
   ✓ "FHA 24 CFR 100.205(c)(3)(i)"
   ✓ "ANSI A117.1 Section 404.2.3"
   ✓ "ICC/ANSI A117.1-2017 Section 604.3"

   WRONG (do not do this):
   ✗ "FHA requirements"
   ✗ "ANSI standards"
   ✗ Just "FHA" or "ANSI"

2. CONFIDENCE LEVELS (Must be accurately assigned):
   - HIGH: Dimension is labeled and clearly visible on the drawing
     Example: You can see "2'-10\"" marked on door, "36\"" on corridor
   - MEDIUM: Can estimate from scale or context but not explicitly labeled
     Example: Can measure with scale bar, typical construction detail
   - LOW: Cannot verify from drawing, needs field measurement
     Example: Dimension not shown, detail unclear, "verify in field" needed

   TARGET: 50%+ of issues should be HIGH confidence if drawings have dimensions

3. MEASUREMENTS (Always extract when visible):
   - Look for dimension strings on drawings: "3'-0\"", "32\"", "5'6\"", "2-10"
   - If visible: Extract EXACT text, put in "measurement" field, confidence=HIGH
   - If not visible: State "Not dimensioned on plan", confidence=LOW
   - ALWAYS populate the "measurement" field (even if "Not dimensioned")

4. LOCATION SPECIFICITY (Be extremely precise):
   WRONG: "Bathroom door"
   CORRECT: "Master Bathroom entrance door (north wall, adjacent to bedroom)"
   BETTER: "Unit 2A Master Bath entry door on north wall"

5. COMPLETENESS (Find ALL issues):
   - Floor plans: Expect 10-20 issues minimum
   - Interior elevations: Expect 5-10 issues
   - Door schedules: Expect 3-8 issues
   - Do NOT stop at 5-7 issues - keep scanning for all conditions

6. SHEET METADATA (Must extract):
   - Sheet number from title block (e.g., "A2.1", "A-201")
   - Sheet title from title block (e.g., "Unit Plan", "Floor Plan")
   - Look in the right side of drawing for title block

COMMON ACCESSIBILITY ISSUES TO CHECK:
✓ Door clear openings (EVERY door - check schedule + plans)
✓ Maneuvering clearances (at EVERY door - check both sides)
✓ Accessible route widths (continuous 36\" - check hallways, passages)
✓ Bathroom turning circles (60\" diameter - check free of obstructions)
✓ Kitchen work aisles (40\" - between opposing cabinets)
✓ Toilet clearances (side, front, centerline to wall)
✓ Grab bar backing locations (Type A: required at all fixtures)
✓ Counter heights (accessible counters 34\" max)
✓ Threshold heights (1/2\" max exterior, 1/4\" interior)
✓ Hardware types (lever handles, operable one-handed)
✓ Fixture control heights (38\"-48\" AFF for shower controls)

OUTPUT FORMAT (STRICT JSON):
{
  "project_name": "string",
  "ruleset": "FHA" | "ANSI_A1171_TYPE_A" | "ANSI_A1171_TYPE_B",
  "scale_note": "string",
  "overall_summary": "Brief assessment including confidence statement",
  "pages": [
    {
      "page_index": 0,
      "page_label": "Floor Plan" | "Interior Elevation" | "Door Schedule" | "Reflected Ceiling Plan" | "Other",
      "sheet_id": "A2.1",
      "sheet_title": "Unit Plan",
      "summary": "Page summary with confidence assessment",
      "issues": [
        {
          "severity": "High" | "Medium" | "Low",
          "location_hint": "Extremely specific location (unit + room + wall + feature)",
          "finding": "Issue description with measurement if visible",
          "recommendation": "Fix with specific dimensions and code requirement",
          "reference": "MANDATORY: Specific code section (e.g., 'FHA 24 CFR 100.205(c)(3)(i)')",
          "confidence": "High" | "Medium" | "Low",
          "measurement": "MANDATORY: Extracted dimension (e.g., '2-10') OR 'Not dimensioned'"
        }
      ]
    }
  ]
}

FINAL QUALITY CHECK BEFORE RETURNING:
Before you return your response, verify:
✓ Every issue has a code reference with section number (target: 100%)
✓ At least 50% of issues are HIGH confidence (if drawings have dimensions)
✓ Every issue has a measurement value (extracted or "Not dimensioned")
✓ Location hints are specific (room + wall + feature)
✓ Issue count is appropriate (10-20 for floor plans, not 5-7)
✓ Summary mentions overall confidence level

If you don't meet these targets, re-examine the drawings before submitting.
"""

# Agentic vision addendum for Gemini
AGENTIC_VISION_ADDENDUM = """
AGENTIC VISION REQUIREMENTS (Gemini Code Execution):
- If ANY dimension/label/note is too small or unclear, use code execution to crop/zoom/rotate
- Use Python PIL/OpenCV to enhance image regions
- If still unreadable after inspection, mark confidence=Low and note "requires field verification"
- Prefer reporting exact dimension string as printed
- Use code execution to measure pixel distances if scale is provided
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

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    try:
        parsed, _ = decoder.raw_decode(cleaned)
        return parsed
    except json.JSONDecodeError:
        pass

    if "```json" in cleaned:
        start = cleaned.find("```json") + 7
        end = cleaned.find("```", start)
        if end > start:
            try:
                return json.loads(cleaned[start:end].strip())
            except json.JSONDecodeError:
                pass

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
            reference = issue.get("reference")
            if require_references and not reference:
                reference = "Reference needed"
            normalized_issues.append(
                {
                    "severity": severity,
                    "location_hint": issue.get("location_hint", ""),
                    "finding": issue.get("finding", ""),
                    "recommendation": issue.get("recommendation", ""),
                    "reference": reference,
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
    data["ruleset"] = _coerce_choice(
        data.get("ruleset"),
        {"FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"},
        ruleset
    )
    return data


def _build_openai_content(project_name, ruleset, scale_note, page_payloads):
    content = [
        {"type": "text", "text": f"""Project: {project_name}
Ruleset: {ruleset}
Scale: {scale_note}

CRITICAL QUALITY REQUIREMENTS:
1. EVERY issue MUST have a code reference with section number (100% required)
2. At least 50% of issues should be HIGH confidence (if dimensions visible)
3. EVERY issue MUST have a measurement (extracted or "Not dimensioned")
4. Typical floor plan = 10-20 issues minimum (not 5-7)

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
    return content


def _openai_run_review(
    openai_api_key: str,
    project_name: str,
    ruleset: str,
    scale_note: str,
    page_payloads: list[dict],
    model_name: str = "gpt-4o",
) -> ReviewResult:
    client = OpenAI(api_key=openai_api_key)
    content = _build_openai_content(project_name, ruleset, scale_note, page_payloads)

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _system_instructions(require_references)},
            {"role": "user", "content": content}
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=8000,
    )

    output_text = _extract_output_text(resp)
    if not output_text:
        raise ValueError("No response from OpenAI API")

    payload = _coerce_json(output_text)
    payload = _normalize_payload(payload, project_name, ruleset, scale_note, page_payloads)
    return ReviewResult.model_validate(payload)


def _gemini_run_review_per_page(
    gemini_api_key: str,
    project_name: str,
    ruleset: str,
    scale_note: str,
    page_payloads: list[dict],
    model_name: str = "gemini-2.0-flash-exp",
) -> ReviewResult:
    """
    Gemini Agentic Vision approach with improved prompts
    """
    if genai is None or gemini_types is None:
        raise RuntimeError("google-genai is not installed. Add google-genai to requirements.txt.")

    client = genai.Client(api_key=gemini_api_key)

    merged_pages: list[dict] = []
    page_summaries: list[str] = []

    for p in page_payloads:
        page_index = p.get("page_index", 0)
        page_label = p.get("page_label", "Combo Sheet")
        region_tag = p.get("tag", page_label)
        tag_label = _normalize_tag(region_tag)
        enhanced_prompt = build_enhanced_prompt(tag_label, ruleset)

        user_prompt = f"""Project: {project_name}
Ruleset: {ruleset}
Scale: {p.get('scale_note', scale_note)}

=== PAGE {page_index} — {page_label} ===
REGION TAG: {region_tag}
{f"Anchor: {p.get('anchor_text')}" if p.get("anchor_text") else ""}

{enhanced_prompt}

{("Extracted text from this page:\n" + p["extra_text"][:8000]) if p.get("extra_text") else ""}

CRITICAL QUALITY TARGETS:
- Code references: 100% (every issue must have specific section number)
- High confidence: 50%+ (if dimensions are visible on drawings)
- Measurements: 100% (extracted or "Not dimensioned")
- Issue count: 10-20 for floor plans (not 5-7)

Return STRICT JSON matching the schema.
"""

        system_text = SYSTEM_INSTRUCTIONS.strip() + "\n\n" + AGENTIC_VISION_ADDENDUM.strip()

        resp = client.models.generate_content(
            model=model_name,
            contents=[
                gemini_types.Content(
                    role="user",
                    parts=[
                        gemini_types.Part.from_text(system_text),
                        gemini_types.Part.from_text(user_prompt),
                        gemini_types.Part.from_bytes(data=p["png_bytes"], mime_type="image/png"),
                    ],
                )
            ],
            config=gemini_types.GenerateContentConfig(
                tools=[gemini_types.Tool(code_execution=gemini_types.ToolCodeExecution)],
                temperature=0.2,
            ),
        )

        out_text = getattr(resp, "text", None)
        if not out_text:
            raise ValueError(f"Gemini returned empty text for page {page_index}.")

        page_payload = _coerce_json(out_text)
        normalized = _normalize_payload(page_payload, project_name, ruleset, scale_note, [p])

        if normalized.get("pages"):
            merged_pages.extend(normalized["pages"])
        if normalized.get("overall_summary"):
            page_summaries.append(normalized["overall_summary"])

    merged = {
        "project_name": project_name or "",
        "ruleset": ruleset,
        "scale_note": scale_note or "",
        "overall_summary": " ".join(s for s in page_summaries if s).strip(),
        "pages": merged_pages,
    }

    merged = _normalize_payload(merged, project_name, ruleset, scale_note, page_payloads)
    return ReviewResult.model_validate(merged)


def run_review(
    api_key: str,
    project_name: str,
    ruleset: str,
    scale_note: str,
    page_payloads: list[dict],
    model_name: str = "gpt-4o",
    provider: str = "openai",
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.0-flash-exp",
) -> ReviewResult:
    """
    Run accessibility review with improved quality prompts

    Args:
        api_key: OpenAI API key
        project_name: Name of project
        ruleset: FHA, ANSI_A1171_TYPE_A, or ANSI_A1171_TYPE_B
        scale_note: Drawing scale
        page_payloads: List of page data with images
        model_name: OpenAI model (default: gpt-4o for better quality)
        provider: 'openai' or 'gemini'
        gemini_api_key: Gemini API key if using Gemini
        gemini_model: Gemini model (default: gemini-2.0-flash-exp)

    Returns:
        ReviewResult with improved quality metrics
    """
    provider = (provider or "openai").strip().lower()

    if provider == "gemini":
        if not gemini_api_key:
            raise ValueError("Missing GEMINI_API_KEY for provider='gemini'.")
        return _gemini_run_review_per_page(
            gemini_api_key=gemini_api_key,
            project_name=project_name,
            ruleset=ruleset,
            scale_note=scale_note,
            page_payloads=page_payloads,
            model_name=gemini_model,
        )

    return _openai_run_review(
        openai_api_key=api_key,
        project_name=project_name,
        ruleset=ruleset,
        scale_note=scale_note,
        page_payloads=page_payloads,
        model_name=model_name,
    )
