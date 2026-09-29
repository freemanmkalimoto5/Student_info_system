"""
QR generation logic, kept separate from views so it can be reused
(e.g. from management commands, background threads or an API endpoint).
"""
import datetime
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
from django.utils import timezone

O_LEVEL_CLASSES = {'form one', 'form two', 'form three', 'form four'}
A_LEVEL_CLASSES = {'form five', 'form six'}


# --------------------------------------------------------------------
# Expiry rules
# --------------------------------------------------------------------
def expiry_date_for(student, today=None):
    """
    O-level (form 1-4): valid until 31 December (this year).
    A-level (form 5-6): valid until the next 31 May.
    Graduated: None = never expires.
    """
    if student.status == 'graduated':
        return None
    today = today or timezone.localdate()
    if student.grade_class in A_LEVEL_CLASSES:
        may_31 = datetime.date(today.year, 5, 31)
        return may_31 if today <= may_31 else datetime.date(today.year + 1, 5, 31)
    return datetime.date(today.year, 12, 31)


def format_expiry(expiry):
    return expiry.strftime('%d %B %Y') if expiry else 'No expiry'


# --------------------------------------------------------------------
# Image drawing
# --------------------------------------------------------------------
def _get_font(size):
    candidates = ["arialbd.ttf", "DejaVuSans-Bold.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_qr_code_image(data: str, center_text: str) -> Image.Image:
    """QR encoding `data`, with `center_text` drawn in a white box at the center."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img_w, img_h = qr_img.size

    box_w = int(img_w * 0.30)
    box_h = int(img_h * 0.16)
    box_x = (img_w - box_w) // 2
    box_y = (img_h - box_h) // 2

    draw = ImageDraw.Draw(qr_img)
    draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h],
                   fill="white", outline="black", width=2)

    font_size = max(box_h - 10, 10)
    font = _get_font(font_size)
    text_bbox = draw.textbbox((0, 0), center_text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    while text_w > box_w - 10 and font_size > 8:
        font_size -= 2
        font = _get_font(font_size)
        text_bbox = draw.textbbox((0, 0), center_text, font=font)
        text_w = text_bbox[2] - text_bbox[0]

    text_h = text_bbox[3] - text_bbox[1]
    text_x = box_x + (box_w - text_w) // 2
    text_y = box_y + (box_h - text_h) // 2 - text_bbox[1]
    draw.text((text_x, text_y), center_text, fill="black", font=font)
    return qr_img


def generate_id_card_qr(student) -> ContentFile:
    """
    Build the QR for a Student and return it as a ContentFile.
    The QR encodes the student's details as plain TEXT (not a link),
    so it can be read offline. It now also carries a "Valid Until" line.
    """
    from apps.accounts.models import SiteSettings

    site_settings = SiteSettings.load()
    expiry = expiry_date_for(student)

    data = (
        "STUDENT ID VERIFICATION\n"
        f"School: {site_settings.school_name}\n"
        f"Name: {student.full_name}\n"
        f"Student Number: {student.student_number}\n"
        f"Class: {student.get_grade_class_display()}\n"
        f"Status: {student.get_status_display()}\n"
        f"Parish: {student.parish or '-'}\n"
        f"Valid Until: {format_expiry(expiry)}"
    )
    image = generate_qr_code_image(data, student.student_number)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"qr_{student.student_number}.png")


# --------------------------------------------------------------------
# Saving / regenerating cards
# --------------------------------------------------------------------
def save_card_qr(student, card=None):
    """
    (Re)build ONE student's QR for real: delete the old image file,
    recompute valid_until, write a brand-new image. Every place that
    regenerates a QR should go through this function.
    """
    from .models import IDCard

    if card is None:
        card, _ = IDCard.objects.get_or_create(student=student)
    if card.qr_image:
        card.qr_image.delete(save=False)      # don't leave orphan files on disk
    card.valid_until = expiry_date_for(student)
    card.qr_image.save(
        f"qr_{student.student_number}.png",
        generate_id_card_qr(student),
        save=True,
    )
    return card


def regenerate_cards(students):
    """Rebuild QR codes for a list of students. Safe to run in a background thread."""
    from django import db
    try:
        for student in students:
            save_card_qr(student)
    finally:
        db.connections.close_all()


def get_or_create_card(student):
    """Fetch this student's IDCard, generating the QR the first time it's needed."""
    from .models import IDCard

    card, created = IDCard.objects.get_or_create(student=student)
    if created or not card.qr_image:
        save_card_qr(student, card)
    return card


# --------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------
def generate_id_card_pdf(student, card) -> bytes:
    """Render one student's ID card as a 90mm x 55mm PDF (reportlab)."""
    import os
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from django.conf import settings
    from apps.accounts.models import SiteSettings

    site_settings = SiteSettings.load()

    width, height = 90 * mm, 55 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    c.setStrokeColorRGB(0.12, 0.23, 0.37)
    c.setLineWidth(1)
    c.roundRect(2 * mm, 2 * mm, width - 4 * mm, height - 4 * mm, 3 * mm, stroke=1, fill=0)

    logo_path = None
    if site_settings.logo and os.path.exists(site_settings.logo.path):
        logo_path = site_settings.logo.path
    else:
        default_logo = os.path.join(settings.BASE_DIR, 'static', 'img', 'school_logo.png')
        if os.path.exists(default_logo):
            logo_path = default_logo
    if logo_path:
        c.drawImage(logo_path, 4 * mm, height - 13 * mm, width=8 * mm, height=8 * mm,
                    preserveAspectRatio=True, mask='auto')

    c.setFont("Helvetica-Bold", 8)
    school_name = site_settings.school_name
    if len(school_name) > 28:
        school_name = school_name[:26] + "…"
    c.drawCentredString(width / 2, height - 8 * mm, school_name)

    if student.photo and os.path.exists(student.photo.path):
        photo_size = 16 * mm
        photo_x, photo_y = 4 * mm, height - 32 * mm
        cx, cy = photo_x + photo_size / 2, photo_y + photo_size / 2
        c.saveState()
        clip_path = c.beginPath()
        clip_path.circle(cx, cy, photo_size / 2)
        c.clipPath(clip_path, stroke=0, fill=0)
        c.drawImage(student.photo.path, photo_x, photo_y, width=photo_size, height=photo_size,
                    preserveAspectRatio=True, anchor='c', mask='auto')
        c.restoreState()

    text_x = 22 * mm
    text_y = height - 18 * mm
    c.setFont("Helvetica-Bold", 7)
    c.drawString(text_x, text_y, student.full_name)
    c.setFont("Helvetica", 6)
    c.drawString(text_x, text_y - 4 * mm, f"No: {student.student_number}")
    c.drawString(text_x, text_y - 8 * mm, f"Class: {student.get_grade_class_display()}")
    c.drawString(text_x, text_y - 12 * mm, f"Parish: {student.parish or '-'}")
    c.drawString(text_x, text_y - 16 * mm, f"Valid until: {format_expiry(card.valid_until)}")

    if card.is_expired:
        c.setFillColorRGB(0.75, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(width - 15 * mm, 12 * mm, "EXPIRED")
    elif card.qr_image and os.path.exists(card.qr_image.path):
        qr_size = 22 * mm
        c.drawImage(card.qr_image.path, width - qr_size - 4 * mm, 4 * mm,
                    width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto')

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()
