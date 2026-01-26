"""
Quality analysis and metrics for reviews
Place this in src/quality_analysis.py
"""

from typing import List, Dict
from .schemas import ReviewResult, ReviewQualityMetrics

class ReviewQualityAnalyzer:
    """Analyze the quality and completeness of a review"""
    
    EXPECTED_ISSUES_PER_PAGE = {
        "Floor Plan": 5,
        "Interior Elevation": 3,
        "Door Schedule": 3,
        "Reflected Ceiling Plan": 2,
        "Other": 3,
    }
    
    @staticmethod
    def calculate_metrics(result: ReviewResult) -> ReviewQualityMetrics:
        """Calculate quality metrics for a review"""
        total_issues = 0
        high_confidence = 0
        with_measurements = 0
        with_references = 0
        
        for page in result.pages:
            total_issues += len(page.issues)
            for issue in page.issues:
                if issue.confidence == "High":
                    high_confidence += 1
                if issue.measurement or any(char.isdigit() for char in issue.finding):
                    with_measurements += 1
                if issue.reference:
                    with_references += 1
        
        pages_reviewed = len(result.pages)
        avg_issues = total_issues / pages_reviewed if pages_reviewed > 0 else 0
        
        # Confidence score: based on ratio of high-confidence issues
        confidence_score = (high_confidence / total_issues * 100) if total_issues > 0 else 0
        
        # Completeness score: based on expected vs actual issues and references
        expected_total = sum(
            ReviewQualityAnalyzer.EXPECTED_ISSUES_PER_PAGE.get(page.page_label, 3)
            for page in result.pages
        )
        completeness_score = min(100, (total_issues / expected_total * 100)) if expected_total > 0 else 0
        
        return ReviewQualityMetrics(
            total_issues=total_issues,
            high_confidence_issues=high_confidence,
            issues_with_measurements=with_measurements,
            issues_with_references=with_references,
            pages_reviewed=pages_reviewed,
            avg_issues_per_page=avg_issues,
            confidence_score=confidence_score,
            completeness_score=completeness_score,
        )
    
    @staticmethod
    def get_quality_warnings(metrics: ReviewQualityMetrics) -> List[str]:
        """Generate warnings about potential review quality issues"""
        warnings = []
        
        if metrics.avg_issues_per_page < 3:
            warnings.append(
                f"⚠️ Low issue count: Only {metrics.avg_issues_per_page:.1f} issues per page. "
                "Review may be incomplete."
            )
        
        if metrics.confidence_score < 30:
            warnings.append(
                f"⚠️ Low confidence: Only {metrics.confidence_score:.0f}% of issues are high confidence. "
                "Consider manual verification."
            )
        
        if metrics.issues_with_references < metrics.total_issues * 0.5:
            warnings.append(
                f"⚠️ Missing references: Only {metrics.issues_with_references} of {metrics.total_issues} "
                "issues have code references."
            )
        
        if metrics.completeness_score < 60:
            warnings.append(
                f"⚠️ Review may be incomplete: Completeness score is {metrics.completeness_score:.0f}%. "
                "Consider re-running or manual review."
            )
        
        return warnings
    
    @staticmethod
    def suggest_improvements(metrics: ReviewQualityMetrics) -> List[str]:
        """Suggest ways to improve the review"""
        suggestions = []
        
        if metrics.issues_with_measurements < metrics.total_issues * 0.3:
            suggestions.append(
                "💡 Request specific measurements: Ask the LLM to extract and report actual dimensions "
                "from the drawings for more concrete findings."
            )
        
        if metrics.confidence_score < 50:
            suggestions.append(
                "💡 Consider higher quality images: Higher DPI rendering may help the LLM identify "
                "details with more confidence."
            )
        
        if metrics.issues_with_references < metrics.total_issues * 0.5:
            suggestions.append(
                "💡 Add code references: Consider requesting specific code section references "
                "for each finding to strengthen the review."
            )
        
        suggestions.append(
            "💡 Follow-up review: Consider a second-pass review focusing specifically on "
            "issues flagged as Medium or Low confidence."
        )
        
        return suggestions
