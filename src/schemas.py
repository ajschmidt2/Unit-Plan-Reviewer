from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict

Ruleset = Literal["FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"]
PageType = Literal["Floor Plan", "Interior Elevation", "Door Schedule", "Reflected Ceiling Plan", "Other"]

class Issue(BaseModel):
    severity: Literal["High", "Medium", "Low"]
    location_hint: str
    finding: str
    recommendation: str
    reference: Optional[str] = None
    confidence: Literal["High", "Medium", "Low"]
    measurement: Optional[str] = None  # Extracted measurement if available

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

class ImageQualityMetrics(BaseModel):
    width: int
    height: int
    dpi: str
    sharpness: float
    file_size_kb: float
    quality_score: int
    warnings: List[str]
    suitable_for_review: bool

class ReviewQualityMetrics(BaseModel):
    total_issues: int
    high_confidence_issues: int
    issues_with_measurements: int
    issues_with_references: int
    pages_reviewed: int
    avg_issues_per_page: float
    confidence_score: float
    completeness_score: float
