from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from apps.students.models import Student
from .services import generate_id_card_qr, generate_id_card_pdf, get_or_create_card


def _can_view_student(user, student):
    """
    Same rule as the students app: admins see everyone, a parent login
    only their own linked child. Kept local to avoid a circular import
    with apps.students.views (which already imports from this module).
    """
    if user.is_staff or user.is_superuser:
        return True
    parent_account = getattr(user, 'parent_account', None)
    if parent_account is None:
        return False
    return parent_account.students.filter(pk=student.pk).exists()


def _get_authorized_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied("You don't have access to this student's QR code.")
    return student


@login_required
def qr_preview(request, pk):
    """Preview a specific student's QR code before printing."""
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)
    return render(request, 'qrcodes/qr_preview.html', {
        'student': student,
        'card': card,
    })


@login_required
def qr_regenerate(request, pk):
    """Force-regenerate the QR (e.g. after editing student details)."""
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)
    card.qr_image.save(
        f"qr_{student.student_number}.png",
        generate_id_card_qr(student),
        save=True,
    )
    return redirect('qrcodes:preview', pk=student.pk)


@login_required
def qr_print(request, pk):
    """
    Printable ID card view for one specific student. Uses the
    dedicated print.css so it lays out cleanly on paper/card stock.
    """
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)

    if request.method == 'POST':
        # The print template's "Confirm Printed" button hits this
        # with POST to log that a physical copy was produced.
        card.mark_printed()
        return redirect('qrcodes:print', pk=student.pk)

    return render(request, 'qrcodes/id_card_print.html', {
        'student': student,
        'card': card,
    })


@login_required
def qr_download_pdf(request, pk):
    """
    Generate a downloadable PDF of one student's ID card, so staff can
    save or email it instead of only being able to browser-print it.
    Built with reportlab (pure Python, no native library dependencies).
    """
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)

    pdf_bytes = generate_id_card_pdf(student, card)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="id_card_{student.student_number}.pdf"'
    )
    return response
