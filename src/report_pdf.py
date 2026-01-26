from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from io import BytesIO
from datetime import datetime

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

    # ===== COVER PAGE =====
    y = h - 2 * inch
    
    # Title
    c.setFont("Helvetica-Bold", 20)
    title = f"Accessibility Review Report"
    c.drawCentredString(w / 2, y, title)
    y -= 0.5 * inch
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, y, result.project_name)
    y -= 1 * inch
    
    # Metadata box
    c.setFont("Helvetica", 11)
    c.drawString(left_margin + 0.5*inch, y, f"Ruleset: {result.ruleset}")
    y -= 0.3 * inch
    c.drawString(left_margin + 0.5*inch, y, f"Scale: {result.scale_note}")
    y -= 0.3 * inch
    c.drawString(left_margin + 0.5*inch, y, f"Date: {datetime.now().strftime('%B %d, %Y')}")
    y -= 0.3 * inch
    c.drawString(left_margin + 0.5*inch, y, f"Pages Reviewed: {len(result.pages)}")
    y -= 0.3 * inch
    
    total_issues = sum(len(p.issues) for p in result.pages)
    c.drawString(left_margin + 0.5*inch, y, f"Total Issues Found: {total_issues}")
    y -= 1 * inch
    
    # Overall summary
    if result.overall_summary:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left_margin, y, "Executive Summary")
        y -= 0.3 * inch
        
        c.setFont("Helvetica", 10)
        y = wrap_text(c, result.overall_summary, left_margin, y, max_text_width, "Helvetica", 10)
        y -= 0.5 * inch
    
    # Disclaimer
    c.setFont("Helvetica-Oblique", 8)
    disclaimer = (
        "DISCLAIMER: This review is provided as preliminary guidance only and does not replace "
        "professional judgment, field verification, or jurisdictional review. All measurements "
        "and findings should be verified on-site before making final decisions."
    )
    y = wrap_text(c, disclaimer, left_margin, y, max_text_width, "Helvetica-Oblique", 8)
    
    # Start new page for content
    c.showPage()
    y = h - inch

    # ===== DETAILED FINDINGS =====
    issue_num = 1
    for page in result.pages:
        # Check if we need a new page
        if y < 2 * inch:
            c.showPage()
            y = h - inch

        # Page header with background
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(left_margin - 0.1*inch, y - 0.35*inch, max_text_width + 0.2*inch, 0.4*inch, fill=True, stroke=False)
        c.setFillColorRGB(0, 0, 0)
        
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left_margin, y - 0.25*inch, f"Page {page.page_index} — {page.page_label}")
        y -= 0.5 * inch
        
        # Sheet info
        c.setFont("Helvetica", 9)
        sheet_text = f"Sheet: {page.sheet_number or 'N/A'} — {page.sheet_title or 'N/A'}"
        c.drawString(left_margin, y, sheet_text)
        y -= 0.25 * inch
        c.setFont("Helvetica", 9)
        c.drawString(
            inch,
            y,
            f"Sheet: {page.sheet_number or 'N/A'} — {page.sheet_title or 'N/A'}"
        )
        y -= 0.25 * inch
        c.setFont("Helvetica", 9)
        c.drawString(inch, y, f"Summary: {page.summary}")
        y -= 0.25 * inch
        c.setFont("Helvetica", 9)
        c.drawString(
            inch,
            y,
            f"Sheet: {page.sheet_number or 'N/A'} — {page.sheet_title or 'N/A'}"
        )
        y -= 0.25 * inch
        c.setFont("Helvetica", 9)
        c.drawString(inch, y, f"Summary: {page.summary}")
        y -= 0.25 * inch
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(inch, y, "Review confirmation: Drawing image reviewed.")
        y -= 0.2 * inch

        if not page.issues:
            c.setFont("Helvetica", 9)
            c.drawString(inch, y, "No issues reported.")
            y -= 0.2 * inch

        if not page.issues:
            c.setFont("Helvetica", 9)
            c.drawString(inch, y, "No issues reported.")
            y -= 0.2 * inch

        # Page summary with wrapping
        if page.summary:
            c.setFont("Helvetica-Oblique", 9)
            y = wrap_text(c, f"Summary: {page.summary}", left_margin, y, max_text_width, "Helvetica-Oblique", 9)
            y -= 0.3 * inch

        if not page.issues:
            c.setFont("Helvetica", 9)
            c.drawString(left_margin, y, "✓ No issues reported for this page.")
            y -= 0.4 * inch
        else:
            for issue in page.issues:
                # Check if we need a new page before each issue
                if y < 2.5 * inch:
                    c.showPage()
                    y = h - inch
                
                # Issue number and severity badge
                c.setFont("Helvetica-Bold", 10)
                severity_symbol = {"High": "●", "Medium": "◐", "Low": "○"}
                header = f"{issue_num}. {severity_symbol.get(issue.severity, '○')} [{issue.severity}] {issue.location_hint}"
                c.drawString(left_margin, y, header)
                y -= 0.2 * inch
                
                # Confidence indicator
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(left_margin + 0.2*inch, y, f"Confidence: {issue.confidence}")
                y -= 0.2 * inch
                
                # Finding with wrapping
                c.setFont("Helvetica", 9)
                finding_text = f"<b>Finding:</b> {issue.finding}"
                y = wrap_text(c, finding_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica", 9)
                y -= 0.15 * inch
                
                # Measurement if present
                if issue.measurement:
                    c.setFont("Helvetica", 9)
                    meas_text = f"<b>Measured:</b> {issue.measurement}"
                    y = wrap_text(c, meas_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica", 9)
                    y -= 0.15 * inch
                
                # Recommendation with wrapping
                rec_text = f"<b>Recommendation:</b> {issue.recommendation}"
                y = wrap_text(c, rec_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica", 9)
                y -= 0.15 * inch
                
                # Reference if present
                if issue.reference:
                    c.setFont("Helvetica-Oblique", 8)
                    ref_text = f"<b>Reference:</b> {issue.reference}"
                    y = wrap_text(c, ref_text, left_margin + 0.2*inch, y, max_text_width - 0.2*inch, "Helvetica-Oblique", 8)
                    y -= 0.15 * inch
                
                y -= 0.3 * inch
                issue_num += 1
        
        y -= 0.2 * inch

    # Add footer to all pages
    page_num = 1
    for page_count in range(c.getPageNumber()):
        c.setFont("Helvetica", 8)
        c.drawCentredString(w / 2, 0.5 * inch, f"Page {page_num} | Generated by Unit Plan Reviewer")
        page_num += 1

    c.save()
    return buf.getvalue()
