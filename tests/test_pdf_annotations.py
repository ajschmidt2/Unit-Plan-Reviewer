import unittest

import fitz

from src.annotations import apply_annotations, assign_issue_ids
from src.report_pdf import build_pdf_report
from src.schemas import Issue, PageReview, ReviewResult


class TestPdfAnnotations(unittest.TestCase):
    def test_severity_override_in_pdf(self):
        review = ReviewResult(
            project_name="Test Project",
            ruleset="FHA",
            scale_note="1/4\" = 1'-0\"",
            overall_summary="",
            pages=[
                PageReview(
                    page_index=0,
                    page_label="Floor Plan",
                    summary="",
                    issues=[
                        Issue(
                            severity="Low",
                            location_hint="Entry",
                            finding="Issue finding",
                            recommendation="Issue recommendation",
                            confidence="High",
                        )
                    ],
                )
            ],
        )
        review = assign_issue_ids(review)
        issue_id = review.pages[0].issues[0].issue_id
        annotations = {
            "dismissed_issues": [],
            "notes": {},
            "severity_overrides": {issue_id: "High"},
        }

        annotated = apply_annotations(review, annotations)
        pdf_bytes = build_pdf_report(annotated)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        self.assertIn("[High]", text)


if __name__ == "__main__":
    unittest.main()
