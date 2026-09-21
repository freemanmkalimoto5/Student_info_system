from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.decorators import admin_required
from apps.accounts.services import sync_all_parent_accounts, log_action
from apps.qrcodes.services import get_or_create_card
from apps.pocketmoney.forms import InitialDepositForm, BalanceAdjustmentForm
from apps.pocketmoney.services import add_transaction, get_balance

from .forms import StudentForm, CSVImportForm
from .models import Student
from .services import import_students_from_csv, renumber_students, CLASS_ORDER


def _is_admin(user):
    return user.is_staff or user.is_superuser


def _visible_students_qs(user):
    """
    Admins/staff see every student. A parent login only sees the
    student(s) linked to their ParentAccount — never anyone else's.
    """
    if _is_admin(user):
        return Student.objects.all()

    parent_account = getattr(user, 'parent_account', None)
    if parent_account is None:
        return Student.objects.none()
    return parent_account.students.all()


def _can_view_student(user, student):
    return _is_admin(user) or _visible_students_qs(user).filter(pk=student.pk).exists()


@admin_required
def student_create(request):
    """Form to fill in all the necessary details about a student. Admins only."""
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES)
        deposit_form = InitialDepositForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            student.student_number = _placeholder_number()
            student.added_by = request.user
            student.save()

            sync_all_parent_accounts(student)
            log_action(student, 'created', request.user)
            renumber_students()  # assigns the real, ordered student number

            # Optional starting pocket money — no admin password needed
            # here since registering a student is already admin-only.
            if deposit_form.is_valid():
                initial_amount = deposit_form.cleaned_data.get('initial_amount')
                if initial_amount:
                    add_transaction(
                        student, 'deposit', initial_amount,
                        note='Initial pocket money at registration', user=request.user
                    )

            messages.success(request, f"Student {student.full_name} registered successfully.")
            return redirect('students:detail', pk=student.pk)
    else:
        form = StudentForm()
        deposit_form = InitialDepositForm()

    return render(request, 'students/student_form.html', {
        'form': form,
        'deposit_form': deposit_form,
    })


@admin_required
def student_update(request, pk):
    """Admins only — parents can view their child but not edit records."""
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, instance=student)
        adjustment_form = BalanceAdjustmentForm(request.POST)
        if form.is_valid():
            form.save()
            sync_all_parent_accounts(student)
            log_action(student, 'updated', request.user)
            renumber_students()  # class/name may have changed the correct order

            # Pocket money balance adjustment — requires the admin to
            # re-enter their own password. Wrong/blank password means
            # NO change is made, but the student edit above still saves.
            if adjustment_form.is_valid():
                amount = adjustment_form.cleaned_data.get('amount')
                if amount:
                    password = adjustment_form.cleaned_data.get('admin_password')
                    if not password or not request.user.check_password(password):
                        messages.error(
                            request,
                            "Pocket money balance was NOT changed — incorrect or missing password."
                        )
                    else:
                        try:
                            add_transaction(
                                student,
                                adjustment_form.cleaned_data['adjustment_type'],
                                amount,
                                adjustment_form.cleaned_data.get('note', ''),
                                user=request.user,
                            )
                            messages.success(request, "Pocket money balance updated.")
                        except ValueError as exc:
                            messages.error(request, str(exc))

            messages.success(request, f"Student {student.full_name} updated successfully.")
            return redirect('students:detail', pk=student.pk)
    else:
        form = StudentForm(instance=student)
        adjustment_form = BalanceAdjustmentForm()

    return render(request, 'students/student_form.html', {
        'form': form,
        'student': student,
        'adjustment_form': adjustment_form,
        'pocket_balance': get_balance(student),
    })


@admin_required
def student_delete(request, pk):
    """Delete a student, with confirmation. Admins only."""
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        log_action(student, 'deleted', request.user)
        name = student.full_name
        student.delete()
        renumber_students()
        messages.success(request, f"Student {name} was deleted.")
        return redirect('students:list')

    return render(request, 'students/student_confirm_delete.html', {'student': student})


@login_required
def student_list(request):
    """
    Admins see every student. A parent login sees only their own
    child(ren) — the search box and pagination still work, just
    scoped to whatever they're allowed to see.
    """
    query = request.GET.get('q', '').strip()
    students = _visible_students_qs(request.user)
    if query:
        students = students.filter(
            models_q_search(query)
        )

    paginator = Paginator(students, 20)  # 20 students per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'students': page_obj,   # iterable in the template, same as before
        'page_obj': page_obj,
        'query': query,
    }

    # Live search hits this same view via fetch(), asking for just the
    # table + pagination fragment instead of the whole page.
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'students/_student_table.html', context)

    if _is_admin(request.user):
        context['summary'] = _build_summary()
    return render(request, 'students/student_list.html', context)


def _build_summary():
    """Total students, per-class counts (in class order), and status counts."""
    total = Student.objects.count()

    raw_class_counts = dict(
        Student.objects.values_list('grade_class').annotate(count=Count('id'))
    )
    class_summary = [
        (label, raw_class_counts.get(key, 0))
        for key, label in Student.CLASS_CHOICES
    ]

    status_counts = dict(
        Student.objects.values_list('status').annotate(count=Count('id'))
    )

    return {
        'total': total,
        'class_summary': class_summary,
        'active': status_counts.get('active', 0),
        'suspended': status_counts.get('suspended', 0),
        'transferred': status_counts.get('transferred', 0),
        'graduated': status_counts.get('graduated', 0),
    }


def models_q_search(query):
    """Small helper so student_list can search across a few fields at once."""
    from django.db.models import Q
    return (
        Q(student_number__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(grade_class__icontains=query)
    )


@login_required
def student_detail(request, pk):
    """
    Shows the student's info plus their ID card + QR code inline.
    A parent may only open their own child's page — anyone else's
    student_id gets a 403, not just a hidden link.
    """
    student = get_object_or_404(Student, pk=pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied("You don't have access to this student's record.")

    card = get_or_create_card(student)
    return render(request, 'students/student_detail.html', {
        'student': student,
        'card': card,
    })


@admin_required
def student_import(request):
    """Bulk-register students by uploading a CSV file. Admins only."""
    if request.GET.get('sample') == '1':
        return _sample_csv_response()

    result = None
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            result = import_students_from_csv(form.cleaned_data['csv_file'])
            if result['created']:
                renumber_students()  # assign real numbers once, after the whole batch
                messages.success(
                    request,
                    f"Imported {len(result['created'])} student(s) successfully."
                )
            if result['skipped']:
                messages.warning(
                    request,
                    f"{len(result['skipped'])} row(s) were skipped — see details below."
                )
            form = CSVImportForm()  # reset the form for another upload
    else:
        form = CSVImportForm()

    return render(request, 'students/student_import.html', {
        'form': form,
        'result': result,
        'class_order': CLASS_ORDER,
    })


def _placeholder_number():
    """Temporary unique value assigned before renumber_students() runs."""
    import uuid
    return f"TMP-{uuid.uuid4().hex[:10]}"


def _sample_csv_response():
    """A downloadable CSV template showing the expected columns."""
    header = (
        "first_name,middle_name,last_name,date_of_birth,grade_class,status,"
        "father_name,father_phone,father_whatsapp,"
        "mother_name,mother_phone,mother_whatsapp,"
        "guardian_name,guardian_phone,guardian_relationship,"
        "parish,full_address,region,district,ward\n"
    )
    sample_row = (
        "Jane,John,Doe,2008-05-14,form four,active,"
        "John Doe,0700000000,0700000000,"
        "Mary Doe,0700000001,0700000001,"
        "Aunt Jane,0700000002,Aunt,"
        "Usokami,Kibengu Street,Iringa,Mufindi,Usokami\n"
    )
    response = HttpResponse(header + sample_row, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="student_import_sample.csv"'
    return response
