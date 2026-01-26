from pydantic import BaseModel, Field
from typing import List, Literal, Optional

Ruleset = Literal["FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"]

class Issue(BaseModel):
    severity: Literal["High", "Medium", "Low"]
    location_hint: str
    finding: str
    recommendation: str
    reference: Optional[str]
    confidence: Literal["High", "Medium", "Low"]

class PageReview(BaseModel):
    page_index: int
    page_label: str
    sheet_number: str
    sheet_title: str
    summary: str
    issues: List[Issue]

class ReviewResult(BaseModel):
    project_name: str
    ruleset: Ruleset
    scale_note: str
    overall_summary: str
    pages: List[PageReview]
