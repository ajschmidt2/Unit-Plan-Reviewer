from copy import deepcopy
from typing import Any, Dict, Union

from src.schemas import ReviewResult


def assign_issue_ids(result: ReviewResult) -> ReviewResult:
    updated = result.model_copy(deep=True)
    for page in updated.pages:
        for idx, issue in enumerate(page.issues):
            if not issue.issue_id:
                issue.issue_id = f"p{page.page_index}_i{idx}"
    return updated


def apply_annotations(review: Union[ReviewResult, Dict[str, Any]], annotations: Dict[str, Any]) -> ReviewResult:
    if isinstance(review, ReviewResult):
        base_review = review
    else:
        base_review = ReviewResult.model_validate(review)

    result = base_review.model_copy(deep=True) if isinstance(base_review, ReviewResult) else deepcopy(base_review)
    dismissed = set(annotations.get("dismissed_issues", []))
    notes = annotations.get("notes", {}) or {}
    overrides = annotations.get("severity_overrides", {}) or {}

    for page in result.pages:
        new_issues = []
        for idx, issue in enumerate(page.issues):
            iid = issue.issue_id or f"p{page.page_index}_i{idx}"
            issue.issue_id = iid
            if iid in dismissed:
                continue
            override = overrides.get(iid)
            if override in {"High", "Medium", "Low"}:
                issue.severity = override
            note = notes.get(iid)
            if note:
                issue.reviewer_note = note
            new_issues.append(issue)
        page.issues = new_issues

    return result
