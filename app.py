import subprocess
import streamlit as st
from src.auth import require_login
from src.pdf_utils import (
    pdf_to_page_images,
    extract_page_texts,
    extract_sheet_metadata,
    extract_title_block_texts,
)
from src.llm_review import run_review
from src.report_pdf import build_pdf_report
from src.storage import init_db, save_review

def _get_app_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True
        ).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"

def display_results(result):
    """Display review results on screen"""
    st.success("✅ Review Complete!")
    
    # Overall Summary
    if result.overall_summary:
        st.subheader("Overall Summary")
        st.write(result.overall_summary)
    
    # Display each page's results
    for page in result.pages:
        with st.expander(f"📄 Page {page.page_index} — {page.page_label}", expanded=True):
            # Sheet info
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Sheet Number:** {page.sheet_number or 'N/A'}")
            with col2:
                st.write(f"**Sheet Title:** {page.sheet_title or 'N/A'}")
            
            # Page summary
            if page.summary:
                st.write("**Summary:**")
                st.info(page.summary)
            
            # Issues
            if page.issues:
                st.write(f"**Issues Found:** {len(page.issues)}")
                for idx, issue in enumerate(page.issues, 1):
                    severity_color = {
                        "High": "🔴",
                        "Medium": "🟡", 
                        "Low": "🟢"
                    }
                    confidence_badge = f"*Confidence: {issue.confidence}*"
                    
                    st.markdown(f"**{idx}. {severity_color.get(issue.severity, '⚪')} [{issue.severity}] {issue.location_hint}** ({confidence_badge})")
                    st.markdown(f"**Finding:** {issue.finding}")
                    st.markdown(f"**Recommendation:** {issue.recommendation}")
                    if issue.reference:
                        st.markdown(f"**Reference:** {issue.reference}")
                    st.divider()
            else:
                st.warning("No issues reported for this page.")

def main():
    require_login()
    init_db()

    st.title("Unit Plan Reviewer")
    st.caption(f"Build: {_get_app_version()}")

    project_name = st.text_input("Project Name")
    ruleset = st.selectbox("Ruleset", ["FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"])
    scale_note = st.text_input("Scale Note", "1/4\" = 1'-0\"")

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if not uploaded:
        st.stop()

    pdf_bytes = uploaded.getvalue()
    
    with st.spinner("Processing PDF..."):
        pages = pdf_to_page_images(pdf_bytes)
        page_texts = extract_page_texts(pdf_bytes)
        title_blocks = extract_title_block_texts(pdf_bytes, max_pages=len(pages))
    
    st.success(f"✅ Loaded {len(pages)} pages from PDF")
    
    selected = []

    include_all = st.checkbox("Include all pages")

    for p in pages:
        with st.expander(f"Page {p.page_index}"):
            st.image(p.png_bytes, use_container_width=True)
            include_page = st.checkbox(
                "Include",
                key=f"include_page_{p.page_index}",
                disabled=include_all
            )
            if include_all or include_page:
                title_block = title_blocks[p.page_index] if p.page_index < len(title_blocks) else ""
                sheet_number, sheet_title = extract_sheet_metadata(
                    title_block or page_texts.get(p.page_index, "")
                )
                
                # Show extracted metadata for debugging
                with st.container():
                    st.caption(f"Detected: Sheet {sheet_number or 'N/A'} - {sheet_title or 'N/A'}")
                
                selected.append({
                    "page_index": p.page_index,
                    "page_label": "Floor Plan",
                    "png_bytes": p.png_bytes,
                    "sheet_number_hint": sheet_number,
                    "sheet_title_hint": sheet_title,
                    "extra_text": (
                        f"Page text:\n{page_texts.get(p.page_index, '')}\n\n"
                        f"Title block text (right side):\n{title_block}"
                    )
                })

    st.write(f"**Selected pages:** {[p['page_index'] for p in selected]}")

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
            
            # Display results on screen
            display_results(result)
            
            # Save to database
            save_review(project_name, ruleset, scale_note, result.model_dump_json())
            st.success("💾 Review saved to database")
            
            # Generate and offer PDF download
            with st.spinner("Generating PDF report..."):
                pdf = build_pdf_report(result)
            
            st.download_button(
                "📥 Download PDF Report", 
                pdf, 
                file_name=f"{project_name.replace(' ', '_')}_review.pdf",
                mime="application/pdf"
            )
            
        except Exception as e:
            st.error("❌ Error during review:")
            st.exception(e)
            st.stop()

if __name__ == "__main__":
    main()
