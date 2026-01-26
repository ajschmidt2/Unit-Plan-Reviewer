from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from io import BytesIO

def build_pdf_report(result):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    y = h - inch
    c.setFont("Helvetica-Bold", 14)
    c.drawString(inch, y, f"Unit Plan Review Report — {result.project_name}")
    y -= 0.4 * inch

    c.setFont("Helvetica", 10)
    c.drawString(inch, y, f"Ruleset: {result.ruleset} | Scale: {result.scale_note}")
    y -= 0.4 * inch

    c.setFont("Helvetica", 10)
    c.drawString(inch, y, result.overall_summary)
    y -= 0.4 * inch

    issue_num = 1
    for page in result.pages:
        if y < inch:
            c.showPage()
            y = h - inch

        c.setFont("Helvetica-Bold", 11)
        c.drawString(inch, y, f"Page {page.page_index} — {page.page_label}")
        y -= 0.25 * inch
        c.setFont("Helvetica", 9)
        c.drawString(
            inch,
            y,
            f"Sheet: {page.sheet_number or 'N/A'} — {page.sheet_title or 'N/A'}"
        )
        y -= 0.25 * inch

        for issue in page.issues:
            c.setFont("Helvetica", 9)
            c.drawString(inch, y, f"{issue_num}. [{issue.severity}] {issue.location_hint}")
            y -= 0.2 * inch
            c.drawString(inch + 0.2*inch, y, issue.finding)
            y -= 0.2 * inch
            issue_num += 1

    c.save()
    return buf.getvalue()
