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

    The QR encodes the student's details as plain TEXT (not a link), so
    it can be read by any phone's camera with NO internet connection,
    no LAN access to this server, and no server needing to be running
    at all. A QR code can only ever carry text -- it cannot carry the
    student's photo or a logo image, which is why those two stay on the
    printed ID card / PDF and the in-app profile page instead, where an
    actual image can be shown.
    """
    from apps.accounts.models import SiteSettings

    site_settings = SiteSettings.load()
    expiry = expiry_date_for(student)

    lines = [
        "STUDENT ID VERIFICATION",
        f"School: {site_settings.school_name}",
        f"Name: {student.full_name}",
        f"Student Number: {student.student_number}",
        f"Class: {student.get_grade_class_display()}",
        f"Status: {student.get_status_display()}",
        f"Date of Birth: {student.date_of_birth:%d %b %Y}",
        f"Parish: {student.parish or '-'}",
        f"Address: {student.full_address or '-'}",
    ]

    if student.father_name:
        father = student.father_name
        if student.father_phone:
            father += f" ({student.father_phone})"
        lines.append(f"Father: {father}")

    if student.mother_name:
        mother = student.mother_name
        if student.mother_phone:
            mother += f" ({student.mother_phone})"
        lines.append(f"Mother: {mother}")

    if not student.father_name and not student.mother_name and student.guardian_name:
        guardian = student.guardian_name
        if student.guardian_phone:
            guardian += f" ({student.guardian_phone})"
        lines.append(f"Guardian: {guardian}")

    lines.append(f"Valid Until: {format_expiry(expiry)}")

    contact_bits = []
    if site_settings.contact_phone:
        contact_bits.append(site_settings.contact_phone)
    if site_settings.contact_email:
        contact_bits.append(site_settings.contact_email)
    website = getattr(site_settings, 'website', '') or ''
    if website:
        contact_bits.append(website)
    if contact_bits:
        lines.append("School contact: " + " | ".join(contact_bits))

    data = "\n".join(lines)
    image = generate_qr_code_image(data, student.student_number)

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"qr_{student.student_number}.png")


# --------------------------------------------------------------------
# Saving / regenerating cards
# --------------------------------------------------------------------
def save_card_qr(student, card=None):
    from .models import IDCard

    if card is None:
        card, _ = IDCard.objects.get_or_create(student=student)
    if card.qr_image:
        card.qr_image.delete(save=False)
    card.valid_until = expiry_date_for(student)
    card.qr_image.save(
        f"qr_{student.student_number}.png",
        generate_id_card_qr(student),
        save=True,
    )
    return card


def regenerate_cards(students, max_workers=8):
    """
    Rebuild QR codes for a list of students -- IN PARALLEL (several
    students' images are built and saved at once, not one after
    another), so a full-school rebuild finishes much faster. Runs
    happily in a background thread; each worker closes its own
    database connection when it's done with its share of the work.

    This keeps running to completion on the SERVER regardless of
    whether the person who clicked "Regenerate" stays on the page --
    a web request finishing (or the browser tab closing) has no effect
    on a background thread already running on the server. It is only
    at risk if the Django process itself restarts (e.g. the dev
    server's auto-reloader) while a regenerate is still in progress.
    """
    import concurrent.futures
    from django import db

    def _one(student):
        try:
            save_card_qr(student)
        except Exception as exc:
            print(f"QR regenerate failed for {student.student_number}:", exc)
        finally:
            db.connections.close_all()   # this worker thread's own connection

    workers = max(1, min(max_workers, len(students) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_one, students))


def get_or_create_card(student):
    from .models import IDCard

    card, created = IDCard.objects.get_or_create(student=student)
    if created or not card.qr_image:
        save_card_qr(student, card)
    return card


# --------------------------------------------------------------------
# Batch print / download (sorted by class)
# --------------------------------------------------------------------
def students_for_batch(class_key=None):
    from apps.students.models import Student
    from apps.students.services import sort_students

    qs = Student.objects.exclude(status='graduated')
    if class_key:
        qs = qs.filter(grade_class=class_key)
    return sort_students(qs)


def build_qr_batch_pdf(students, title):
    """A4 PDF: QR codes only, in a grid, grouped by class."""
    import os
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas

    from apps.students.services import CLASS_INDEX

    buffer = io.BytesIO()
    c = pdf_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    cols, rows = 4, 5
    margin = 12 * mm
    cell_w = (width - 2 * margin) / cols
    cell_h = (height - 2 * margin - 14 * mm) / rows

    def new_page(class_label):
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, height - margin, title)
        c.setFont("Helvetica", 9)
        c.drawRightString(width - margin, height - margin, class_label)
        c.line(margin, height - margin - 4, width - margin, height - margin - 4)

    students = sorted(students, key=lambda s: CLASS_INDEX.get(s.grade_class, 99))
    current_class = None
    col = row = 0
    for student in students:
        card = getattr(student, 'id_card', None)
        if card is None or not card.qr_image or not os.path.exists(card.qr_image.path):
            continue

        if student.grade_class != current_class:
            if current_class is not None:
                c.showPage()
            current_class = student.grade_class
            new_page(student.get_grade_class_display())
            col = row = 0

        x = margin + col * cell_w
        y = height - margin - 14 * mm - (row + 1) * cell_h

        qr_size = min(cell_w, cell_h) - 12 * mm
        qr_x = x + (cell_w - qr_size) / 2
        c.drawImage(card.qr_image.path, qr_x, y + 10 * mm, width=qr_size, height=qr_size,
                   preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + cell_w / 2, y + 6 * mm, student.student_number)
        c.setFont("Helvetica", 7)
        name = student.full_name
        if len(name) > 22:
            name = name[:20] + "…"
        c.drawCentredString(x + cell_w / 2, y + 2 * mm, name)

        col += 1
        if col >= cols:
            col = 0
            row += 1
            if row >= rows:
                row = 0
                c.showPage()
                new_page(student.get_grade_class_display())

    if current_class is not None:
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def _faded_logo(logo_path, target_width_px=800, opacity=0.07):
    import os
    if not logo_path or not os.path.exists(logo_path):
        return None
    try:
        img = Image.open(logo_path).convert("RGBA")
        ratio = target_width_px / img.width
        img = img.resize((target_width_px, max(1, int(img.height * ratio))))
        alpha = img.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        img.putalpha(alpha)
        return img
    except Exception:
        return None


def _draw_id_card_page(c, student, card, site_settings, width, height):
    """Draws ONE full ID card (border, watermark, photo, text, QR) onto
    the CURRENT page of an already-open reportlab canvas `c` sized
    (width, height). Shared by the single-card PDF and the batch
    (all-cards-in-one-PDF) download, so both look identical."""
    import os
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from django.conf import settings as django_settings

    logo_path = None
    if site_settings.logo and os.path.exists(site_settings.logo.path):
        logo_path = site_settings.logo.path
    else:
        default_logo = os.path.join(django_settings.BASE_DIR, 'static', 'img', 'school_logo.png')
        if os.path.exists(default_logo):
            logo_path = default_logo

    watermark = _faded_logo(logo_path) if logo_path else None
    if watermark:
        wm_w = 46 * mm
        wm_h = wm_w * watermark.height / watermark.width
        c.drawImage(ImageReader(watermark), (width - wm_w) / 2, (height - wm_h) / 2,
                   width=wm_w, height=wm_h, mask='auto')

    c.setStrokeColorRGB(0.12, 0.23, 0.37)
    c.setLineWidth(1)
    c.roundRect(2 * mm, 2 * mm, width - 4 * mm, height - 4 * mm, 3 * mm, stroke=1, fill=0)

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


def generate_id_card_pdf(student, card) -> bytes:
    """Single student's ID card as a 90mm x 55mm PDF."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from apps.accounts.models import SiteSettings

    site_settings = SiteSettings.load()
    width, height = 90 * mm, 55 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    _draw_id_card_page(c, student, card, site_settings, width, height)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def build_id_cards_batch_pdf(students, title):
    """ALL students' full ID cards in one PDF, one card per page
    (90mm x 55mm each), sorted by class. Unlike build_qr_batch_pdf
    (which only draws the QR), this draws the WHOLE card -- photo,
    watermark, text and QR -- exactly as it looks on screen."""
    import os
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from apps.accounts.models import SiteSettings
    from apps.students.services import CLASS_INDEX

    site_settings = SiteSettings.load()
    width, height = 90 * mm, 55 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    students = sorted(students, key=lambda s: CLASS_INDEX.get(s.grade_class, 99))
    drawn_any = False
    for student in students:
        card = getattr(student, 'id_card', None)
        if card is None or not card.qr_image or not os.path.exists(card.qr_image.path):
            continue
        _draw_id_card_page(c, student, card, site_settings, width, height)
        c.showPage()
        drawn_any = True

    if not drawn_any:
        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2, height / 2, "No cards with a QR code yet.")
        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer.read()
