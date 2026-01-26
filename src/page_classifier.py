import re
from typing import Dict, List

TAGS = [
    "Floor Plan",
    "Interior Elevations",
    "RCP / Ceiling",
    "Door Schedule",
    "Notes / Code",
    "Details / Sections",
]

KEYWORDS = {
    "Floor Plan": ["FLOOR PLAN", "UNIT PLAN", "PLAN", "DIMENSION", "ROOM", "DWG SCALE"],
    "Interior Elevations": [
        "INTERIOR ELEVATION",
        "ELEVATION",
        "CABINET ELEV",
        "TILE ELEV",
        "A",
        "B",
        "C",
        "D",
    ],
    "RCP / Ceiling": [
        "RCP",
        "REFLECTED CEILING",
        "CEILING PLAN",
        "LIGHTING",
        "SMOKE",
        "SPRINKLER",
        "DIFFUSER",
    ],
    "Door Schedule": ["DOOR SCHEDULE", "DOOR", "MARK", "WIDTH", "HEIGHT", "FRAME", "HARDWARE", "HINGE", "SET"],
    "Notes / Code": ["GENERAL NOTES", "ACCESSIBILITY", "ADA", "ANSI", "FHA", "CODE", "SPEC"],
    "Details / Sections": ["DETAIL", "SECTION", "CALLOUT", "TYP.", "ENLARGED"],
}

CONFIDENCE_THRESHOLDS = [
    (8, "High"),
    (4, "Medium"),
    (1, "Low"),
]


def _score_for_keyword(text: str, keyword: str) -> int:
    if " " in keyword:
        return 3 if keyword in text else 0
    if len(keyword) == 1:
        return 1 if re.search(rf"\\b{re.escape(keyword)}\\b", text) else 0
    return 1 if keyword in text else 0


def _table_bonus(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0
    spaced_lines = sum(1 for line in lines if re.search(r"\S+\s{2,}\S+", line))
    header_hits = sum(1 for token in ["WIDTH", "HEIGHT", "TYPE", "MARK"] if token in text)
    if spaced_lines >= max(3, len(lines) // 10) or header_hits >= 2:
        return 5
    return 0


def _confidence_for_score(score: int) -> str:
    for threshold, label in CONFIDENCE_THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


def classify_page(text: str) -> Dict:
    combined = (text or "").upper()
    scores: Dict[str, int] = {tag: 0 for tag in TAGS}

    for tag, keywords in KEYWORDS.items():
        for keyword in keywords:
            scores[tag] += _score_for_keyword(combined, keyword)

    scores["Door Schedule"] += _table_bonus(combined)

    tagged = [
        {
            "tag": tag,
            "score": score,
            "confidence": _confidence_for_score(score),
        }
        for tag, score in scores.items()
        if score >= 3
    ]

    if not tagged:
        top_tag = max(scores.items(), key=lambda item: item[1])[0]
        tagged = [
            {
                "tag": top_tag,
                "score": scores[top_tag],
                "confidence": _confidence_for_score(scores[top_tag]),
            }
        ]

    tagged.sort(key=lambda item: item["score"], reverse=True)
    return {"tags": tagged, "raw_scores": scores}
