import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required
from apps.students.models import Student
from apps.students.services import sort_students
from .services import (
    generate_id_card_pdf, get_or_create_card, save_card_qr, regenerate_cards,
)


def _can_view_student(user, student):
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


# ---------------- NEW: all QR codes, sorted FI.1 -> FVI.n ----------------
@admin_required
def qr_list(request):
    students = sort_students(Student.objects.select_related('id_card'))
    for s in students:
        s.card = getattr(s, 'id_card', None)     # None if no card yet
    return render(request, 'qrcodes/qr_list.html', {
        'students': students,
        'total': len(students),
    })


# ---------------- NEW: rebuild every QR (needs admin password) ----------------
@admin_required
@require_POST
def qr_regenerate_all(request):
    password = request.POST.get('password', '')
    if not password or not request.user.check_password(password):
        messages.error(request, "Incorrect or missing password. No QR codes were changed.")
        return redirect('qrcodes:list')

    students = sort_students(Student.objects.all())
    # Runs in the background so the page doesn't freeze for hundreds of students.
    threading.Thread(target=regenerate_cards, args=(students,), daemon=True).start()
    messages.success(
        request,
        f"Rebuilding {len(students)} QR codes in the background. "
        "Refresh this page in a minute or two to see the new codes."
    )
    return redirect('qrcodes:list')


@login_required
def qr_preview(request, pk):
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)
    return render(request, 'qrcodes/qr_preview.html', {'student': student, 'card': card})


@admin_required   # was: any logged-in user. A parent could otherwise "revive" an expired card.
def qr_regenerate(request, pk):
    """Force-regenerate ONE student's QR."""
    student = get_object_or_404(Student, pk=pk)
    save_card_qr(student)
    return redirect('qrcodes:preview', pk=student.pk)


@login_required
def qr_print(request, pk):
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)

    if request.method == 'POST':
        card.mark_printed()
        return redirect('qrcodes:print', pk=student.pk)

    return render(request, 'qrcodes/id_card_print.html', {'student': student, 'card': card})


@login_required
def qr_download_pdf(request, pk):
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)
    pdf_bytes = generate_id_card_pdf(student, card)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="id_card_{student.student_number}.pdf"'
    return response
