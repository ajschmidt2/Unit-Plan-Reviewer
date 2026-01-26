import streamlit as st
from src.auth import require_login
from src.pdf_utils import pdf_to_page_images, extract_pdf_text
from src.llm_review import run_review
from src.report_pdf import build_pdf_report
from src.storage import init_db, save_review

def main():
    require_login()
    init_db()

    st.title("Unit Plan Reviewer")

    project_name = st.text_input("Project Name")
    ruleset = st.selectbox("Ruleset", ["FHA", "ANSI_A1171_TYPE_A", "ANSI_A1171_TYPE_B"])
    scale_note = st.text_input("Scale Note", "1/8\" = 1'-0\"")

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if not uploaded:
        st.stop()

    pages = pdf_to_page_images(uploaded.getvalue())
    selected = []

    for p in pages:
        with st.expander(f"Page {p.page_index}"):
            st.image(p.png_bytes, use_container_width=True)
            if st.checkbox("Include", key=p.page_index):
                selected.append({
                    "page_index": p.page_index,
                    "page_label": "Floor Plan",
                    "png_bytes": p.png_bytes
                })

    if st.button("Run Review"):
        result = run_review(
            api_key=st.secrets["OPENAI_API_KEY"],
            project_name=project_name,
            ruleset=ruleset,
            scale_note=scale_note,
            page_payloads=selected
        )

        save_review(project_name, ruleset, scale_note, result.model_dump_json())
        pdf = build_pdf_report(result)

        st.download_button("Download PDF Report", pdf, file_name="review.pdf")

if __name__ == "__main__":
    main()
