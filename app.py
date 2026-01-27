import subprocess
import streamlit as st
import json
from src.auth import require_login
from src.pdf_utils import (
    pdf_to_page_images,
    extract_page_texts,
    extract_sheet_metadata,
    extract_title_block_texts,
    ImageQualityChecker,
    ScaleVerifier,
)
from src.page_classifier import TAGS, classify_page
from src.region_extractor import extract_regions
from src.llm_review import run_review
from src.report_pdf import build_pdf_report
from src.annotations import apply_annotations, assign_issue_ids
from src.storage import init_db, save_review, get_project_review_history, compare_reviews
from src.schemas import ReviewResult
from src.quality_analysis import ReviewQualityAnalyzer

def _get_app_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True
        ).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"

class IssueManager:
    """Manage user interactions with review issues"""
    
    @staticmethod
    def initialize_session_state():
        """Initialize session state for issue tracking"""
        if 'dismissed_issues' not in st.session_state:
            st.session_state.dismissed_issues = set()
        if 'issue_notes' not in st.session_state:
            st.session_state.issue_notes = {}
        if 'issue_severity_overrides' not in st.session_state:
            st.session_state.issue_severity_overrides = {}
    
    @staticmethod
    def display_interactive_issue(page_index: int, issue_index: int, issue: dict):
        """Display an issue with interactive controls"""
        IssueManager.initialize_session_state()
        
        issue_id = issue.get("issue_id") or f"p{page_index}_i{issue_index - 1}"
        
        # Check if dismissed
        if issue_id in st.session_state.dismissed_issues:
            st.markdown(f"~~{issue_index}. [Dismissed] {issue['location_hint']}~~")
            st.caption("This issue has been dismissed.")
            if st.button("Restore", key=f"restore_{issue_id}"):
                st.session_state.dismissed_issues.remove(issue_id)
                st.rerun()
            st.divider()
            return
        
        # Display issue with controls
        col1, col2 = st.columns([5, 1])
        
        with col1:
            severity_color = {
                "High": "🔴",
                "Medium": "🟡",
                "Low": "🟢"
            }
            
            # Allow severity override
            current_severity = st.session_state.issue_severity_overrides.get(
                issue_id, issue['severity']
            )
            
            st.markdown(
                f"**{issue_index}. {severity_color.get(current_severity, '⚪')} "
                f"[{current_severity}] {issue['location_hint']}**"
            )
        
        with col2:
            # Dismiss button
            if st.button("Dismiss", key=f"dismiss_{issue_id}"):
                st.session_state.dismissed_issues.add(issue_id)
                st.rerun()
        
        st.markdown(f"**Finding:** {issue['finding']}")
        st.markdown(f"**Recommendation:** {issue['recommendation']}")
        
        if issue.get('reference'):
            st.markdown(f"**Reference:** {issue['reference']}")
        
        if issue.get('measurement'):
            st.markdown(f"**Measured:** {issue['measurement']}")
        
        st.caption(f"*Confidence: {issue['confidence']}*")
        
        # Add notes section (NO expander — expanders cannot nest)
        show_controls = st.checkbox(
            "📝 Add notes / override severity",
            key=f"show_controls_{issue_id}",
            value=False,
        )

        if show_controls:
            with st.container():
                st.caption("Overrides & notes")

                new_severity = st.selectbox(
                    "Override Severity",
                    ["Keep Original", "High", "Medium", "Low"],
                    key=f"severity_{issue_id}",
                )

                if new_severity != "Keep Original" and new_severity != issue["severity"]:
                    if st.button("Apply Severity Change", key=f"apply_sev_{issue_id}"):
                        st.session_state.issue_severity_overrides[issue_id] = new_severity
                        st.rerun()

                existing_note = st.session_state.issue_notes.get(issue_id, "")
                note = st.text_area(
                    "Notes",
                    value=existing_note,
                    key=f"note_{issue_id}",
                    placeholder="Add notes about this issue, field verification results, etc.",
                )

                if st.button("Save Note", key=f"save_note_{issue_id}"):
                    st.session_state.issue_notes[issue_id] = note
                    st.success("Note saved!")
        
        st.divider()
    
    @staticmethod
    def export_with_annotations(result):
        """Export review with user annotations"""
        IssueManager.initialize_session_state()
        
        annotated = {
            "review": result.model_dump(),
            "annotations": {
                "dismissed_issues": list(st.session_state.dismissed_issues),
                "notes": st.session_state.issue_notes,
                "severity_overrides": st.session_state.issue_severity_overrides,
            }
        }
        
        return json.dumps(annotated, indent=2)
    
    @staticmethod
    def display_summary_stats():
        """Display summary of user actions"""
        IssueManager.initialize_session_state()
        
        dismissed_count = len(st.session_state.dismissed_issues)
        notes_count = len([n for n in st.session_state.issue_notes.values() if n.strip()])
        overrides_count = len(st.session_state.issue_severity_overrides)
        
        if dismissed_count > 0 or notes_count > 0 or overrides_count > 0:
            st.info(
                f"📊 You have: {dismissed_count} dismissed issues, "
                f"{notes_count} notes, {overrides_count} severity overrides"
            )

def display_quality_metrics(result):
    """Display quality metrics in Streamlit"""
    analyzer = ReviewQualityAnalyzer()
    metrics = analyzer.calculate_metrics(result)
    warnings = analyzer.get_quality_warnings(metrics)
    suggestions = analyzer.suggest_improvements(metrics)
    
    with st.expander("📊 Review Quality Metrics", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Issues", metrics.total_issues)
            st.metric("Avg Issues/Page", f"{metrics.avg_issues_per_page:.1f}")
        
        with col2:
            st.metric("Confidence Score", f"{metrics.confidence_score:.0f}%")
            st.metric("High Confidence", metrics.high_confidence_issues)
        
        with col3:
            st.metric("Completeness", f"{metrics.completeness_score:.0f}%")
            st.metric("With References", metrics.issues_with_references)
        
        if warnings:
            st.warning("**Quality Warnings:**")
            for warning in warnings:
                st.write(warning)
        
        if suggestions:
            st.info("**Suggestions for Improvement:**")
            for suggestion in suggestions:
                st.write(suggestion)


def build_annotations() -> dict:
    IssueManager.initialize_session_state()
    return {
        "dismissed_issues": list(st.session_state.get("dismissed_issues", set())),
        "notes": st.session_state.get("issue_notes", {}),
        "severity_overrides": st.session_state.get("issue_severity_overrides", {}),
    }


def load_review_package(payload: dict):
    if isinstance(payload, dict) and "review" in payload:
        review_payload = payload.get("review", {})
        annotations = payload.get("annotations", {}) or {}
    else:
        review_payload = payload
        annotations = {}
    review = assign_issue_ids(ReviewResult.model_validate(review_payload))
    annotated = apply_annotations(review, annotations)
    return review, annotations, annotated

def display_image_quality_report(page_images, scale_note):
    """Display image quality report in Streamlit"""
    with st.expander("🔍 Image Quality & Scale Analysis"):
        overall_suitable = True
        
        for page_img in page_images:
            quality = ImageQualityChecker.check_image_quality(page_img.png_bytes)
            
            st.write(f"**Page {page_img.page_index}**")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Resolution", f"{quality['width']}x{quality['height']}")
            with col2:
                st.metric("DPI", quality['dpi'])
            with col3:
                st.metric("Sharpness", quality['sharpness'])
            with col4:
                score_color = "🟢" if quality['quality_score'] >= 80 else "🟡" if quality['quality_score'] >= 60 else "🔴"
                st.metric("Quality", f"{score_color} {quality['quality_score']}")
            
            if quality['warnings']:
                for warning in quality['warnings']:
                    st.warning(warning)
                overall_suitable = False
            else:
                st.success("✅ Image quality suitable for detailed review")
            
            st.divider()
        
        # Scale verification
        st.subheader("Scale Verification")
        scale_info = ScaleVerifier.suggest_measurement_extraction(scale_note, 200)
        st.info(scale_info)
        
        return overall_suitable

def display_comparison(comparison: dict):
    """Display comparison results in Streamlit"""
    st.subheader("📊 Comparison with Previous Review")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Previous Issues",
            comparison["old_issue_count"]
        )
    
    with col2:
        st.metric(
            "Current Issues", 
            comparison["new_issue_count"],
            delta=comparison["new_issue_count"] - comparison["old_issue_count"],
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "Resolved",
            comparison["resolved_count"],
            delta=comparison["resolved_count"],
            delta_color="normal"
        )
    
    with col4:
        st.metric(
            "New Issues",
            comparison["new_issues_count"],
            delta=comparison["new_issues_count"],
            delta_color="inverse"
        )
    
    if comparison["improvement_percentage"] > 0:
        st.success(f"✅ Overall improvement: {comparison['improvement_percentage']:.1f}% reduction in issues")
    elif comparison["improvement_percentage"] < 0:
        st.warning(f"⚠️ Issue count increased by {abs(comparison['improvement_percentage']):.1f}%")
    else:
        st.info("Issue count unchanged")

def display_results(result, base_review):
    """Display results with interactive issue management"""
    st.success("✅ Review Complete!")
    
    IssueManager.display_summary_stats()
    
    # Overall Summary
    if result.overall_summary:
        st.subheader("Overall Summary")
        st.write(result.overall_summary)
    
    # Display quality metrics
    display_quality_metrics(result)
    
    # Display each page's results with interactive controls
    for page in result.pages:
        with st.expander(f"📄 Page {page.page_index} — {page.page_label}", expanded=True):
            sheet_id = getattr(page, "sheet_id", None) or getattr(page, "sheet_number", None)
            sheet_title = page.sheet_title or "N/A"
            st.write(f"**Sheet:** {sheet_id or 'N/A'} — {sheet_title}")
            
            if page.summary:
                st.write("**Summary:**")
                st.info(page.summary)
            
            if page.issues:
                st.write(f"**Issues Found:** {len(page.issues)}")
                for idx, issue in enumerate(page.issues, 1):
                    IssueManager.display_interactive_issue(
                        page.page_index, idx, issue.model_dump()
                    )
            else:
                st.warning("No issues reported for this page.")
    
    # Export with annotations
    col1, col2 = st.columns(2)
    with col1:
        annotated_json = IssueManager.export_with_annotations(base_review)
        st.download_button(
            "📥 Download Annotated Review (JSON)",
            annotated_json,
            file_name="annotated_review.json",
            mime="application/json"
        )
    
    with col2:
        if st.button("🔄 Reset All Annotations"):
            st.session_state.dismissed_issues = set()
            st.session_state.issue_notes = {}
            st.session_state.issue_severity_overrides = {}
            st.rerun()

def main():
    require_login()
    init_db()

    st.title("Unit Plan Reviewer")
    st.caption(f"Build: {_get_app_version()}")

    if "page_scale_overrides" not in st.session_state:
        st.session_state.page_scale_overrides = {}

    project_name = st.text_input("Project Name")
    ruleset = st.selectbox("Ruleset", ["FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"])
    scale_note = st.text_input("Scale Note", "1/4\" = 1'-0\"")

    auto_tagging = st.checkbox("Auto-detect content tags", value=True)
    use_region_detection = st.checkbox("Use region detection / crop views", value=True)

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if not uploaded:
        st.stop()

    pdf_bytes = uploaded.getvalue()
    current_context = (
        project_name.strip(),
        ruleset,
        scale_note,
        uploaded.name,
        auto_tagging,
        use_region_detection,
    )
    if st.session_state.get("review_context") != current_context:
        st.session_state.review_context = current_context
        st.session_state.review_result = None
        st.session_state.review_saved = False
        st.session_state.report_pdf = None
    
    with st.spinner("Processing PDF..."):
        pages = pdf_to_page_images(pdf_bytes)
        page_texts = extract_page_texts(pdf_bytes)
        title_blocks = extract_title_block_texts(pdf_bytes, max_pages=len(pages))
    
    st.success(f"✅ Loaded {len(pages)} pages from PDF")
    
    # Display image quality analysis
    quality_ok = display_image_quality_report(pages, scale_note)
    
    if not quality_ok:
        st.warning("⚠️ Some image quality issues detected. Review accuracy may be affected.")
    
    selected = []
    include_all = st.checkbox("Include all pages")

    for p in pages:
        with st.expander(f"Page {p.page_index}"):
            st.image(p.png_bytes, use_container_width=True)
            
            title_block = title_blocks[p.page_index] if p.page_index < len(title_blocks) else ""
            page_text = page_texts.get(p.page_index, "")
            auto_tags = classify_page(page_text) if auto_tagging else {"tags": []}
            auto_tag_list = [entry["tag"] for entry in auto_tags["tags"]] or ["Floor Plan"]
            
            col1, col2 = st.columns(2)
            
            with col1:
                include_page = st.checkbox(
                    "Include",
                    key=f"include_page_{p.page_index}",
                    disabled=include_all,
                    value=include_all
                )
            
            with col2:
                selected_tags = st.multiselect(
                    "Tags",
                    TAGS,
                    default=auto_tag_list,
                    key=f"tags_{p.page_index}",
                    disabled=not (include_all or include_page),
                )

            if auto_tags["tags"]:
                tag_lines = [
                    f"- {entry['tag']} ({entry['confidence']})"
                    for entry in auto_tags["tags"]
                ]
                st.markdown("**Auto tags:**\n" + "\n".join(tag_lines))

            scale_options = [
                scale_note,
                "1/8\" = 1'-0\"",
                "3/16\" = 1'-0\"",
                "1/4\" = 1'-0\"",
                "3/8\" = 1'-0\"",
                "1/2\" = 1'-0\"",
            ]
            scale_options = list(dict.fromkeys(scale_options))
            different_scales = st.checkbox(
                "Different scales on this sheet",
                key=f"diff_scales_{p.page_index}",
                disabled=not (include_all or include_page),
            )

            if different_scales:
                plan_scale = st.selectbox(
                    "Plan scale",
                    scale_options,
                    key=f"plan_scale_{p.page_index}",
                )
                elevation_scale = st.selectbox(
                    "Elevation scale",
                    scale_options,
                    key=f"elev_scale_{p.page_index}",
                )
                rcp_scale = st.selectbox(
                    "RCP scale",
                    scale_options,
                    key=f"rcp_scale_{p.page_index}",
                )
                detail_scale = st.selectbox(
                    "Detail scale",
                    scale_options,
                    key=f"detail_scale_{p.page_index}",
                )
                st.session_state.page_scale_overrides[p.page_index] = {
                    "Floor Plan": plan_scale,
                    "Interior Elevations": elevation_scale,
                    "RCP / Ceiling": rcp_scale,
                    "Details / Sections": detail_scale,
                    "Door Schedule": detail_scale,
                    "Notes / Code": detail_scale,
                }
            else:
                st.session_state.page_scale_overrides.pop(p.page_index, None)
            
            if include_all or include_page:
                sheet_number, sheet_title = extract_sheet_metadata(
                    title_block or page_text
                )
                
                # Show extracted metadata for debugging
                st.caption(f"Detected: Sheet {sheet_number or 'N/A'} - {sheet_title or 'N/A'}")

                tag_fallback = auto_tag_list
                resolved_tags = selected_tags or tag_fallback
                primary_tag = resolved_tags[0] if resolved_tags else "Floor Plan"
                page_label = (
                    f"Combo: {', '.join(resolved_tags[:3])}"
                    if len(resolved_tags) > 1
                    else primary_tag
                )
                scale_overrides = st.session_state.page_scale_overrides.get(p.page_index, {})
                extra_text = (
                    f"Page text:\n{page_text}\n\n"
                    f"Title block text (right side):\n{title_block}"
                )

                if use_region_detection:
                    regions = extract_regions(
                        pdf_bytes,
                        p.page_index,
                        dpi=200,
                        selected_tags=resolved_tags,
                    )
                    st.markdown("**Detected regions:**")
                    for region in regions:
                        st.image(
                            region["png_bytes"],
                            caption=f"{region['tag']} ({region['confidence']})",
                            use_container_width=True,
                        )
                        selected.append(
                            {
                                "page_index": p.page_index,
                                "page_label": page_label,
                                "tag": region["tag"],
                                "region_bbox": region["bbox"],
                                "anchor_text": region["anchor_text"],
                                "scale_note": scale_overrides.get(region["tag"], scale_note),
                                "png_bytes": region["png_bytes"],
                                "sheet_id_hint": sheet_number,
                                "sheet_title_hint": sheet_title,
                                "extra_text": extra_text,
                            }
                        )
                else:
                    selected.append(
                        {
                            "page_index": p.page_index,
                            "page_label": page_label,
                            "tag": ", ".join(resolved_tags),
                            "scale_note": scale_note,
                            "png_bytes": p.png_bytes,
                            "sheet_id_hint": sheet_number,
                            "sheet_title_hint": sheet_title,
                            "extra_text": extra_text,
                        }
                    )

    selected_page_indices = sorted({p["page_index"] for p in selected})
    st.write(f"**Selected pages:** {selected_page_indices}")

    def render_review_output(review_result):
        annotations = build_annotations()
        annotated_result = apply_annotations(review_result, annotations)
        # Display results on screen
        display_results(annotated_result, review_result)

        # Check for previous reviews
        history = get_project_review_history(project_name.strip(), limit=2)
        if len(history) >= 2:
            st.info("📂 Previous review found for this project")

            if st.checkbox("Compare with previous review"):
                old_review, _, old_annotated = load_review_package(history[1]["result"])
                comparison = compare_reviews(
                    old_annotated.model_dump(),
                    annotated_result.model_dump(),
                )
                display_comparison(comparison)

        # Save to database once per run
        if not st.session_state.review_saved:
            package = {"review": review_result.model_dump(), "annotations": annotations}
            save_review(
                project_name.strip(),
                ruleset,
                scale_note,
                json.dumps(package),
            )
            st.session_state.review_saved = True
            st.success("💾 Review saved to database")

        # Generate and offer PDF download
        with st.spinner("Generating PDF report..."):
            pdf_bytes = build_pdf_report(annotated_result)

        st.download_button(
            "📥 Download PDF Report",
            pdf_bytes,
            file_name=f"{project_name.replace(' ', '_')}_review.pdf",
            mime="application/pdf"
        )

    if st.button("Run Review", type="primary"):
        if not project_name.strip():
            st.error("Enter a Project Name first.")
            st.stop()

        if not selected:
            st.warning("Select at least one page (check Include) before running the review.")
            st.stop()

        api_key = st.secrets.get("OPENAI_API_KEY", "")
        if not api_key:
            st.error("Missing OPENAI_API_KEY in Streamlit secrets.")
            st.stop()

        model_name = st.secrets.get("OPENAI_MODEL", "gpt-4o-mini")
        
        st.info(f"🤖 Using model: {model_name}")
        st.info(f"📊 Analyzing {len(selected)} page(s) with ruleset: {ruleset}")

        try:
            with st.spinner("🔍 Running accessibility review... This may take 30-60 seconds per page."):
                result = run_review(
                    api_key=api_key,
                    project_name=project_name.strip(),
                    ruleset=ruleset,
                    scale_note=scale_note,
                    page_payloads=selected,
                    model_name=model_name
                )
            
            # Debug: Show raw result structure
            with st.expander("🔧 Debug: Raw Result Data"):
                st.json(result.model_dump())

            result = assign_issue_ids(result)
            st.session_state.review_result = result
            st.session_state.review_saved = False
            st.session_state.report_pdf = None
            render_review_output(result)
            
        except Exception as e:
            st.error("❌ Error during review:")
            st.exception(e)
            st.stop()
    elif st.session_state.get("review_result") is not None:
        st.session_state.review_result = assign_issue_ids(st.session_state.review_result)
        render_review_output(st.session_state.review_result)

if __name__ == "__main__":
    main()
