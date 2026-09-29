"""PDF version of the lost items report (reportlab, no native libraries)."""
import io
import os
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor('#1f3b5e')
GREY = colors.HexColor('#667085')
LINE = colors.HexColor('#d5dbe3')


def _m(value):
    return f"{Decimal(value):,.0f}"


def build_report_pdf(student, r, school_name, logo_path=None, parents=None):
    """r = services.report_data(student). Returns PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm, title="Lost Items Report",
    )
    base = getSampleStyleSheet()['Normal']
    small = ParagraphStyle('small', parent=base, fontSize=8.5, textColor=GREY, leading=11)
    body = ParagraphStyle('body', parent=base, fontSize=9.5, leading=12)
    h_school = ParagraphStyle('hs', parent=base, fontName='Helvetica-Bold', fontSize=16, textColor=NAVY, leading=19)
    h_title = ParagraphStyle('ht', parent=base, fontName='Helvetica-Bold', fontSize=11, textColor=GREY, leading=14)
    h_sec = ParagraphStyle('hsec', parent=base, fontName='Helvetica-Bold', fontSize=11, textColor=NAVY, spaceBefore=10, spaceAfter=4)

    story = []

    # ---- header ----
    head_text = [Paragraph(school_name, h_school), Paragraph("LOST ITEMS REPORT", h_title)]
    if logo_path and os.path.exists(logo_path):
        header = Table([[Image(logo_path, 18 * mm, 18 * mm, kind='proportional'), head_text,
                         Paragraph(f"Date: {r['generated_at']:%d %B %Y}", small)]],
                       colWidths=[22 * mm, 100 * mm, 52 * mm])
    else:
        header = Table([[head_text, Paragraph(f"Date: {r['generated_at']:%d %B %Y}", small)]],
                       colWidths=[122 * mm, 52 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
                                ('LINEBELOW', (0, 0), (-1, 0), 1.2, NAVY),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story += [header, Spacer(1, 6)]

    # ---- student ----
    info = [
        [Paragraph('<b>Student</b>', body), Paragraph(student.full_name, body),
         Paragraph('<b>Number</b>', body), Paragraph(student.student_number, body)],
        [Paragraph('<b>Class</b>', body), Paragraph(student.get_grade_class_display(), body),
         Paragraph('<b>Parish</b>', body), Paragraph(student.parish or '-', body)],
    ]
    if parents:
        info.append([Paragraph('<b>Parent(s)</b>', body), Paragraph(parents, body), '', ''])
    t = Table(info, colWidths=[24 * mm, 63 * mm, 24 * mm, 63 * mm])
    style = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
             ('BOX', (0, 0), (-1, -1), 0.6, LINE), ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7f9fc'))]
    if parents:
        style.append(('SPAN', (1, 2), (3, 2)))
    t.setStyle(TableStyle(style))
    story.append(t)

    # ---- items ----
    story.append(Paragraph("Items lost", h_sec))
    if not r['items']:
        story.append(Paragraph("No lost items recorded for this student.", body))
    else:
        rows = [['#', 'Item', 'Date lost', 'Price (TSh)', 'Paid (TSh)', 'Balance (TSh)', 'Status']]
        for n, item in enumerate(r['items'], start=1):
            rows.append([str(n), Paragraph(item.item_name + (f"<br/><font size=7 color='#667085'>{item.note}</font>" if item.note else ''), body),
                         f"{item.date_lost:%d %b %Y}", _m(item.price), _m(item.amount_paid),
                         _m(item.balance), item.get_status_display()])
        rows.append(['', Paragraph('<b>TOTAL</b>', body), '', _m(r['total']), _m(r['paid']), _m(r['balance']), ''])
        tbl = Table(rows, colWidths=[8 * mm, 52 * mm, 24 * mm, 24 * mm, 22 * mm, 24 * mm, 20 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (3, 0), (5, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f7f9fc')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eef6')),
            ('FONTNAME', (3, -1), (5, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, LINE),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)

    # ---- payment history ----
    if r['payments']:
        story.append(Paragraph("Payments received", h_sec))
        prow = [['Date', 'Item', 'Amount (TSh)', 'Note']]
        for p in r['payments']:
            prow.append([f"{p.created_at:%d %b %Y}", Paragraph(p.item.item_name, body), _m(p.amount), Paragraph(p.note or '-', body)])
        pt = Table(prow, colWidths=[26 * mm, 62 * mm, 30 * mm, 56 * mm], repeatRows=1)
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef6')), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), 0.4, LINE),
        ]))
        story.append(pt)

    # ---- summary ----
    story.append(Spacer(1, 12))
    summary = Table([[f"Total value: TSh {_m(r['total'])}", f"Paid: TSh {_m(r['paid'])}",
                      f"Balance due: TSh {_m(r['balance'])}"]], colWidths=[58 * mm] * 3)
    summary.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 0.8, NAVY), ('INNERGRID', (0, 0), (-1, -1), 0.4, LINE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('TEXTCOLOR', (2, 0), (2, 0), colors.HexColor('#b45309') if r['balance'] > 0 else colors.HexColor('#15803d')),
    ]))
    story.append(summary)
    if r['balance'] > 0:
        story += [Spacer(1, 8), Paragraph("Please contact the school office to clear the outstanding balance.", small)]

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
