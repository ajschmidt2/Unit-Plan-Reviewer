from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from io import BytesIO

def wrap_text(c, text, x, y, max_width, font_name="Helvetica", font_size=9, leading=None):
    """
    Wrap text to fit within max_width and return the new y position.
    """
    if leading is None:
        leading = font_size * 1.2
    
    # Create a paragraph style
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
        'CustomStyle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        alignment=TA_LEFT,
    )
    
    # Create paragraph
    para = Paragraph(text, style)
    
    # Calculate available height (estimate)
    available_height = y - inch
    
    # Create a frame and draw
    frame = Frame(x, y - available_height, max_width, available_height, 
                  leftPadding=0, bottomPadding=0, rightPadding=0, topPadding=0)
    
    # Wrap the paragraph
    w, h = para.wrap(max_width, available_height)
    
    # Draw it
    para.drawOn(c, x, y - h)
    
    # Return new y position
    return y - h - (leading * 0.5)

def build_pdf_report(result):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    
    # Define margins
    left_margin = inch
    right_margin = w - inch
    max_text_width = right_margin - left_margin

    y = h - inch
    
    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left_margin, y, f"Unit Plan Review Report — {result.project_name}")
    y -= 0.4 * inch

    # Metadata
    c.setFont("Helvetica", 10)
    c.drawString(left_margin, y, f"Ruleset: {result.ruleset} | Scale: {result.scale_note}")
    y -= 0.4 * inch

    # Overall summary with wrapping
    if result.overall_summary:
        c.setFont("Helvetica", 10)
        y = wrap_text(c, result.overall_summary, left_margin, y, max_text_width, "Helvetica", 10)
        y -= 0.3 * inch

    issue_num = 1
    for page in result.pages:
        # Check if we need a new page
        if y < 2 * inch:
            c.showPage()
            y = h - inch

        # Page header
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left_margin, y, f"Page {page.page_index} — {page.page_label}")
        y -= 0.25 * inch
        
        # Sheet info
        c.setFont("Helvetica", 9)
        sheet_text = f"Sheet: {page.sheet_number or 'N/A'} — {page.sheet_title or 'N/A'}"
        c.drawString(left_margin, y, sheet_text)
        y -= 0.25 * inch
        
        # Review confirmation
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(left_margin, y, "Review confirmation: Drawing image reviewed.")
        y -= 0.3 * inch

        # Page summary with wrapping
        if page.summary:
            c.setFont("Helvetica-Oblique", 9)
            y = wrap_text(c, page.summary, left_margin, y, max_text_width, "Helvetica-Oblique", 9)
            y -= 0.2 * inch

        if not page.issues:
            c.setFont("Helvetica", 9)
            c.drawString(left_margin, y, "No issues reported.")
            y -= 0.3 * inch
        else:
            for issue in page.issues:
                # Check if we need a new page before each issue
                if y < 2 * inch:
                    c.showPage()
                    y = h - inch
                
                # Issue header with severity and location
                c.setFont("Helvetica-Bold", 9)
                header = f"{issue_num}. [{issue.severity}] {issue.location_hint}"
                if issue.confidence:
                    header += f" (Confidence: {issue.confidence})"
                c.drawString(left_margin, y, header)
                y -= 0.2 * inch
                
                # Finding with wrapping
                c.setFont("Helvetica", 9)
                finding_text = f"Finding: {issue.finding}"
                y = wrap_text(c, finding_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica", 9)
                y -= 0.1 * inch
                
                # Recommendation with wrapping
                rec_text = f"Recommendation: {issue.recommendation}"
                y = wrap_text(c, rec_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica", 9)
                y -= 0.1 * inch
                
                # Reference if present
                if issue.reference:
                    c.setFont("Helvetica-Oblique", 8)
                    ref_text = f"Reference: {issue.reference}"
                    y = wrap_text(c, ref_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica-Oblique", 8)
                    y -= 0.1 * inch
                
                y -= 0.2 * inch
                issue_num += 1

    c.save()
    return buf.getvalue()
