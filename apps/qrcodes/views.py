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
    students_for_batch, build_qr_batch_pdf, build_id_cards_batch_pdf,
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


# ---------------- all QR codes, sorted by class ----------------
@admin_required
def qr_list(request):
    students = sort_students(Student.objects.select_related('id_card'))
    for s in students:
        s.card = getattr(s, 'id_card', None)
    return render(request, 'qrcodes/qr_list.html', {
        'students': students,
        'total': len(students),
    })


# ---------------- all ID CARDS (full card, not just QR), sorted by class ----------------
@admin_required
def id_cards_list(request):
    students = sort_students(Student.objects.select_related('id_card'))
    for s in students:
        s.card = getattr(s, 'id_card', None)
    return render(request, 'qrcodes/id_cards_list.html', {
        'students': students,
        'total': len(students),
    })


# ---------------- rebuild every card (QR + ID card data are the same
# underlying record, so one action regenerates both -- "Regenerate QR
# codes" and "Regenerate ID Cards" are the same operation, just
# labelled for whichever page the person is on) ----------------
@admin_required
@require_POST
def qr_regenerate_all(request):
    password = request.POST.get('password', '')
    if not password or not request.user.check_password(password):
        messages.error(request, "Incorrect or missing password. No QR codes were changed.")
        return redirect(request.POST.get('from') or 'qrcodes:list')

    students = sort_students(Student.objects.all())
    threading.Thread(target=regenerate_cards, args=(students,), daemon=True).start()
    messages.success(
        request,
        f"Rebuilding {len(students)} QR/ID cards in the background (running in parallel -- "
        "this finishes on the server even if you leave this page). Refresh in a minute to see them."
    )
    return redirect(request.POST.get('from') or 'qrcodes:list')


# ---------------- print / download a batch (choose class or all) ----------------
@admin_required
def qr_print_choose(request):
    """One small 'choose a class' page, shared by both QR codes and ID
    cards -- ?mode=qr (default) or ?mode=cards decides which batch
    print/download endpoints the two buttons point to."""
    mode = request.GET.get('mode', 'qr')
    if mode not in ('qr', 'cards'):
        mode = 'qr'
    return render(request, 'qrcodes/print_choose.html', {
        'class_choices': Student.CLASS_CHOICES,
        'mode': mode,
    })


@admin_required
def qr_print_batch(request):
    class_key = request.GET.get('class', '').strip()
    students = students_for_batch(class_key or None)
    for s in students:
        s.card = getattr(s, 'id_card', None)
    label = dict(Student.CLASS_CHOICES).get(class_key, 'All Students')
    return render(request, 'qrcodes/print_batch.html', {
        'students': students, 'label': label,
    })


@admin_required
def qr_download_batch_pdf(request):
    class_key = request.GET.get('class', '').strip()
    students = students_for_batch(class_key or None)
    label = dict(Student.CLASS_CHOICES).get(class_key, 'All Students')
    pdf = build_qr_batch_pdf(students, title=f"QR Codes - {label}")
    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"qr_codes_{class_key or 'all'}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------- ID CARDS batch print / download ----------------
@admin_required
def id_cards_print_batch(request):
    class_key = request.GET.get('class', '').strip()
    students = students_for_batch(class_key or None)
    for s in students:
        s.card = getattr(s, 'id_card', None)
    label = dict(Student.CLASS_CHOICES).get(class_key, 'All Students')
    return render(request, 'qrcodes/id_cards_print_batch.html', {
        'students': students, 'label': label,
    })


@admin_required
def id_cards_download_batch_pdf(request):
    class_key = request.GET.get('class', '').strip()
    students = students_for_batch(class_key or None)
    label = dict(Student.CLASS_CHOICES).get(class_key, 'All Students')
    pdf = build_id_cards_batch_pdf(students, title=f"ID Cards - {label}")
    response = HttpResponse(pdf, content_type='application/pdf')
    filename = f"id_cards_{class_key or 'all'}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ---------------- single student ----------------
@login_required
def qr_preview(request, pk):
    student = _get_authorized_student(request, pk)
    card = get_or_create_card(student)
    return render(request, 'qrcodes/qr_preview.html', {'student': student, 'card': card})


@admin_required
def qr_regenerate(request, pk):
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
