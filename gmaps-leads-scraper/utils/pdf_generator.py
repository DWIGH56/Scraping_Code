"""
PDF generation engine using ReportLab.

Features:
- Diagonal transparent background watermark ("CONFIDENTIAL - PROPRIETARY DATA")
- Tabular lead data output
- UTF-8 support for international characters
"""

import logging
import os
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
    Spacer,
)

from config.settings import OUTPUT_DIR, DEFAULT_PDF_NAME, WATERMARK_TEXT, WATERMARK_OPACITY

logger = logging.getLogger(__name__)


def _draw_watermark(canvas_obj: pdf_canvas.Canvas, doc) -> None:
    """
    Draw a diagonal transparent watermark across every page.
    This is called as a page template callback by ReportLab.
    """
    w, h = doc.pagesize if doc else A4

    canvas_obj.saveState()

    # Set watermark colour with low opacity (transparent)
    canvas_obj.setFillColor(HexColor("#888888"), alpha=WATERMARK_OPACITY)

    # Rotate 45 degrees and draw watermark text repeatedly for full coverage
    canvas_obj.translate(w / 2, h / 2)
    canvas_obj.rotate(45)

    # Draw the watermark on a diagonal across the page
    for dx in range(-int(w), int(w), 200):
        for dy in range(-int(h), int(h), 200):
            canvas_obj.setFont("Helvetica-Bold", 36)
            canvas_obj.drawString(dx, dy, WATERMARK_TEXT)

    canvas_obj.restoreState()


def generate_pdf(
    leads: list[dict],
    filename: str = DEFAULT_PDF_NAME,
    title: str = "Google Maps Leads Report",
) -> str:
    """
    Generate a PDF report from scraped leads with a diagonal watermark background.

    Parameters
    ----------
    leads : list[dict]
    filename : str
    title : str

    Returns
    -------
    str – absolute path to the generated PDF file.
    """
    filepath = os.path.join(OUTPUT_DIR, filename)

    # Page setup – landscape for more columns
    doc = SimpleDocTemplate(
        filepath,
        pagesize=landscape(A4),
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal_style = styles["Normal"]

    elements = []

    # Title
    elements.append(Paragraph(title, title_style))
    elements.append(
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style)
    )
    elements.append(Spacer(1, 12))

    if not leads:
        elements.append(Paragraph("No leads were found.", normal_style))
    else:
        # Column headers
        headers = [
            "Name",
            "Phone",
            "Website",
            "Rating",
            "Reviews",
            "Address",
            "Category",
            "Keyword",
            "Location",
            "Google Ads",
            "FB Pixel",
        ]

        # Build table data
        table_data = [headers]
        for lead in leads:
            table_data.append(
                [
                    lead.get("name", ""),
                    lead.get("phone", ""),
                    lead.get("website", ""),
                    str(lead.get("rating", "")) if lead.get("rating") else "",
                    str(lead.get("reviews_count", "")) if lead.get("reviews_count") else "",
                    lead.get("address", ""),
                    lead.get("category", ""),
                    lead.get("keyword", ""),
                    lead.get("location", ""),
                    "✅" if lead.get("has_google_ads") else "❌",
                    "✅" if lead.get("has_facebook_pixel") else "❌",
                ]
            )

        # Create table
        col_widths = [
            1.6 * inch,  # Name
            1.2 * inch,  # Phone
            1.8 * inch,  # Website
            0.6 * inch,  # Rating
            0.6 * inch,  # Reviews
            2.0 * inch,  # Address
            1.2 * inch,  # Category
            1.0 * inch,  # Keyword
            1.2 * inch,  # Location
            0.8 * inch,  # Google Ads
            0.8 * inch,  # FB Pixel
        ]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1a73e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("LEADING", (0, 0), (-1, -1), 10),
                    ("ALIGN", (3, 1), (4, -1), "CENTER"),
                    ("ALIGN", (9, 1), (10, -1), "CENTER"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f8f9fa")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(table)

    # Build the PDF with the watermark callback
    doc.build(
        elements,
        onFirstPage=_draw_watermark,
        onLaterPages=_draw_watermark,
    )

    logger.info(f"PDF generated: {filepath}")
    return filepath