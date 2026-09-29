import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required, superuser_required
from apps.students.models import Student

from . import services
from .forms import LostItemForm, PaymentForm
from .models import LostItem
from .reports import build_report_pdf


def _can_view_student(user, student):
    """Admins see everyone; a parent only their own child (same rule as the rest of the project)."""
    if user.is_staff or user.is_superuser:
        return True
    parent_account = getattr(user, 'parent_account', None)
    if parent_account is None:
        return False
    return parent_account.students.filter(pk=student.pk).exists()


def _authorized_student(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied("You don't have access to this student's record.")
    return student


# ------------------------------------------------------------------ items
@admin_required
def add(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    form = LostItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.student = student
        item.created_by = request.user
        item.save()
        messages.success(request, f"Lost item '{item.item_name}' recorded.")
        return redirect('students:detail', pk=student.pk)
    return render(request, 'lostitems/form.html', {'form': form, 'student': student, 'title': 'Add lost item'})


@admin_required
def edit(request, pk):
    item = get_object_or_404(LostItem, pk=pk)
    form = LostItemForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()       # status is recalculated from payments automatically
        messages.success(request, "Lost item updated.")
        return redirect('students:detail', pk=item.student_id)
    return render(request, 'lostitems/form.html', {'form': form, 'student': item.student, 'title': 'Edit lost item'})


@superuser_required
def delete(request, pk):
    item = get_object_or_404(LostItem, pk=pk)
    if request.method == 'POST':
        student_pk = item.student_id
        item.delete()
        messages.success(request, "Lost item record deleted.")
        return redirect('students:detail', pk=student_pk)
    return render(request, 'lostitems/confirm_delete.html', {'item': item, 'student': item.student})


# --------------------------------------------------------------- payments
@admin_required
def pay(request, pk):
    """Pay all or part of what is owed on one lost item."""
    item = get_object_or_404(LostItem.objects.prefetch_related('payments'), pk=pk)
    if item.balance <= 0:
        messages.info(request, f"'{item.item_name}' is already fully paid.")
        return redirect('students:detail', pk=item.student_id)

    if request.method == 'POST':
        form = PaymentForm(request.POST, item=item)
        if form.is_valid():
            try:
                services.add_payment(item, form.cleaned_data['amount'], form.cleaned_data['note'], request.user)
            except ValueError as exc:
                form.add_error('amount', str(exc))
            else:
                item.refresh_from_db()
                if item.status == 'paid':
                    messages.success(request, f"'{item.item_name}' is now fully paid.")
                else:
                    messages.success(request, f"Payment recorded. Remaining balance: {services.money(item.balance)}.")
                return redirect('students:detail', pk=item.student_id)
    else:
        form = PaymentForm(initial={'amount': item.balance}, item=item)

    return render(request, 'lostitems/pay.html', {'form': form, 'item': item, 'student': item.student})


# ----------------------------------------------------------------- report
@login_required
def report(request, student_pk):
    student = _authorized_student(request, student_pk)
    return render(request, 'lostitems/report.html', {
        'student': student,
        'r': services.report_data(student),
        'numbers': services.parent_numbers(student),
        'can_manage': request.user.is_staff or request.user.is_superuser,
    })


@login_required
def report_pdf(request, student_pk):
    from apps.accounts.models import SiteSettings

    student = _authorized_student(request, student_pk)
    site = SiteSettings.load()

    logo_path = None
    if site.logo and os.path.exists(site.logo.path):
        logo_path = site.logo.path
    else:
        default_logo = os.path.join(settings.BASE_DIR, 'static', 'img', 'school_logo.png')
        if os.path.exists(default_logo):
            logo_path = default_logo

    parents = ", ".join(
        f"{name} ({rel})" for name, rel in (
            (student.father_name, 'Father'), (student.mother_name, 'Mother'), (student.guardian_name, 'Guardian')
        ) if name
    )
    pdf = build_report_pdf(student, services.report_data(student), site.school_name, logo_path, parents)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="lost_items_{student.student_number}.pdf"'
    return response


@admin_required
@require_POST
def report_send(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)

    if not getattr(settings, 'WAHA_BASE_URL', ''):
        messages.warning(request, "WhatsApp (WAHA) is not connected yet, so nothing was sent. "
                                  "Set WAHA_BASE_URL in your .env file first.")
        return redirect('lostitems:report', student_pk=student.pk)

    ok, found = services.send_report_to_parents(student)
    if found == 0:
        messages.error(request, "This student has no parent or guardian phone number on file.")
    elif ok == found:
        messages.success(request, f"Report sent to {ok} parent number(s) on WhatsApp.")
    else:
        messages.warning(request, f"Sent to {ok} of {found} number(s). Check that WAHA is running.")
    return redirect('lostitems:report', student_pk=student.pk)
