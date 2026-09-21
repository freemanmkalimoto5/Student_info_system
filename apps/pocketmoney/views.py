from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.decorators import admin_required, superuser_required
from apps.students.models import Student

from .forms import TransactionForm
from .models import Transaction
from .services import get_balance, add_transaction, get_recent_transactions, delete_transaction


def _can_view_student(user, student):
    """Same ownership rule as the students app — admins see everyone, a parent only their own child."""
    if user.is_staff or user.is_superuser:
        return True
    parent_account = getattr(user, 'parent_account', None)
    if parent_account is None:
        return False
    return parent_account.students.filter(pk=student.pk).exists()


@login_required
def detail(request, student_pk):
    """Balance + transaction history. Viewable by admins and the student's own parent(s)."""
    student = get_object_or_404(Student, pk=student_pk)
    if not _can_view_student(request.user, student):
        raise PermissionDenied("You don't have access to this student's pocket money record.")

    transactions = Transaction.objects.filter(student=student)
    balance = get_balance(student)
    recent = get_recent_transactions(student, limit=3)

    return render(request, 'pocketmoney/detail.html', {
        'student': student,
        'balance': balance,
        'transactions': transactions,
        'recent_transactions': recent,
    })


@admin_required
def add(request, student_pk):
    """Record a deposit or withdrawal. Admins only."""
    student = get_object_or_404(Student, pk=student_pk)

    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            try:
                add_transaction(
                    student=student,
                    transaction_type=form.cleaned_data['transaction_type'],
                    amount=form.cleaned_data['amount'],
                    note=form.cleaned_data['note'],
                    user=request.user,
                )
                messages.success(request, "Transaction recorded successfully.")
                return redirect('pocketmoney:detail', student_pk=student.pk)
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        form = TransactionForm()

    return render(request, 'pocketmoney/add.html', {
        'form': form,
        'student': student,
        'balance': get_balance(student),
    })


@superuser_required
def delete(request, student_pk, transaction_pk):
    """Delete one transaction. Superuser only — not even regular admins/clerks."""
    student = get_object_or_404(Student, pk=student_pk)
    transaction = get_object_or_404(Transaction, pk=transaction_pk, student=student)

    if request.method == 'POST':
        delete_transaction(transaction, request.user)
        messages.success(request, "Transaction deleted.")
        return redirect('pocketmoney:detail', student_pk=student.pk)

    return render(request, 'pocketmoney/transaction_confirm_delete.html', {
        'student': student,
        'transaction': transaction,
    })
