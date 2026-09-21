"""
QR generation logic, kept separate from views so it can be reused
(e.g. later from a bulk-generation command or an API endpoint).
"""
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile


def _get_font(size):
    """
    Try to load a real TrueType font for crisper text; fall back to
    PIL's built-in bitmap font if none is found on this system (keeps
    this working cross-platform without bundling a font file).
    """
    candidates = [
        "arialbd.ttf",   # common on Windows
        "DejaVuSans-Bold.ttf",  # common on Linux
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_qr_code_image(data: str, center_text: str) -> Image.Image:
    """
    Build a QR code encoding `data`, with `center_text` (the student
    number) drawn in a white box at the center of the code.

    High error correction (ERROR_CORRECT_H, ~30% redundancy) is used
    specifically so the code stays scannable even with a chunk of its
    middle covered by text.
    """
    qr = qrcode.QRCode(
        version=None,  # auto-size based on data length
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    img_w, img_h = qr_img.size

    # White box sized to roughly 28% of the QR's width, centered.
    box_w = int(img_w * 0.30)
    box_h = int(img_h * 0.16)
    box_x = (img_w - box_w) // 2
    box_y = (img_h - box_h) // 2

    draw = ImageDraw.Draw(qr_img)
    draw.rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        fill="white",
        outline="black",
        width=2,
    )

    # Shrink font until the student number fits inside the box.
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
    Build the QR for a given Student instance and return it as a
    Django ContentFile, ready to be saved onto an ImageField.

    The QR encodes a full URL to that student's public verification
    page, so scanning it with a phone camera opens the page directly.
    The student number is still shown as visible text at the center.
    """
    from django.conf import settings

    verify_path = f"/verify/{student.student_number}/"
    data = f"{settings.SITE_URL}{verify_path}"
    center_text = student.student_number

    image = generate_qr_code_image(data, center_text)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)

    filename = f"qr_{student.student_number}.png"
    return ContentFile(buffer.read(), name=filename)


def get_or_create_card(student):
    """
    Fetch this student's IDCard, generating the QR image the first
    time it's needed. Shared by qrcodes views (preview/print/download)
    and the student detail page, which now embeds the card + QR
    directly instead of requiring a separate "preview" step.
    """
    from .models import IDCard

    card, created = IDCard.objects.get_or_create(student=student)
    if created or not card.qr_image:
        card.qr_image.save(
            f"qr_{student.student_number}.png",
            generate_id_card_qr(student),
            save=True,
        )
    return card


def generate_id_card_pdf(student, card) -> bytes:
    """
    Render one student's ID card as a small (90mm x 55mm) PDF using
    reportlab. Pure Python, no native/GTK dependencies — this is
    deliberately used instead of weasyprint, which needs system
    libraries (Pango/Cairo) that are painful to install on Windows.

    Reads the student's photo and the QR image straight from disk
    (their .path), so this works even if the dev server isn't running
    to serve them over HTTP.
    """
    import os
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from django.conf import settings

    width, height = 90 * mm, 55 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    # Card border
    c.setStrokeColorRGB(0.12, 0.23, 0.37)
    c.setLineWidth(1)
    c.roundRect(2 * mm, 2 * mm, width - 4 * mm, height - 4 * mm, 3 * mm, stroke=1, fill=0)

    # School logo, top-left
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'school_logo.png')
    if os.path.exists(logo_path):
        c.drawImage(
            logo_path, 4 * mm, height - 13 * mm, width=8 * mm, height=8 * mm,
            preserveAspectRatio=True, mask='auto'
        )

    # Title
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(width / 2, height - 8 * mm, "Student ID Card")

    # Student photo, left side — clipped to a circle for a modern look
    if student.photo and os.path.exists(student.photo.path):
        photo_size = 16 * mm
        photo_x, photo_y = 4 * mm, height - 32 * mm
        cx, cy = photo_x + photo_size / 2, photo_y + photo_size / 2
        c.saveState()
        clip_path = c.beginPath()
        clip_path.circle(cx, cy, photo_size / 2)
        c.clipPath(clip_path, stroke=0, fill=0)
        c.drawImage(
            student.photo.path, photo_x, photo_y, width=photo_size, height=photo_size,
            preserveAspectRatio=True, anchor='c', mask='auto'
        )
        c.restoreState()

    # Details text
    text_x = 22 * mm
    text_y = height - 18 * mm
    c.setFont("Helvetica-Bold", 7)
    c.drawString(text_x, text_y, student.full_name)
    c.setFont("Helvetica", 6)
    c.drawString(text_x, text_y - 4 * mm, f"No: {student.student_number}")
    c.drawString(text_x, text_y - 8 * mm, f"Class: {student.grade_class}")
    c.drawString(text_x, text_y - 12 * mm, f"Parish: {student.parish or '-'}")

    # QR code, bottom-right
    if card.qr_image and os.path.exists(card.qr_image.path):
        qr_size = 22 * mm
        c.drawImage(
            card.qr_image.path, width - qr_size - 4 * mm, 4 * mm,
            width=qr_size, height=qr_size, preserveAspectRatio=True, mask='auto'
        )

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()
