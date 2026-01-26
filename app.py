import subprocess
import streamlit as st
from src.auth import require_login
from src.pdf_utils import pdf_to_page_images, extract_page_texts, extract_title_block_texts
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
    pages = pdf_to_page_images(pdf_bytes)
    page_texts = extract_page_texts(pdf_bytes)
    title_blocks = extract_title_block_texts(pdf_bytes, max_pages=len(pages))
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
                selected.append({
                    "page_index": p.page_index,
                    "page_label": "Floor Plan",
                    "png_bytes": p.png_bytes,
                    "extra_text": (
                        f"Page text:\n{page_texts.get(p.page_index, '')}\n\n"
                        f"Title block text (right side):\n{title_block}"
                    )
                })

    st.write("Selected pages:", [p["page_index"] for p in selected])

    if st.button("Run Review"):
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

        try:
            result = run_review(
                api_key=api_key,
                project_name=project_name.strip(),
                ruleset=ruleset,
                scale_note=scale_note,
                page_payloads=selected,
                model_name=model_name
            )
        except Exception as e:
            st.exception(e)
            st.stop()

        save_review(project_name, ruleset, scale_note, result.model_dump_json())
        pdf = build_pdf_report(result)

        st.download_button("Download PDF Report", pdf, file_name="review.pdf")

if __name__ == "__main__":
    main()
