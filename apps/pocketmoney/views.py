from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.accounts.decorators import admin_required, superuser_required
from apps.students.models import Student

from .forms import TransactionForm
from .models import Transaction
from .services import get_balance, add_transaction, get_recent_transactions, delete_transaction


def _can_view_student(user, student):
    if user.is_staff or user.is_superuser:
        return True
    parent_account = getattr(user, 'parent_account', None)
    if parent_account is None:
        return False
    return parent_account.students.filter(pk=student.pk).exists()


@login_required
def detail(request, student_pk):
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


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


@admin_required
def add(request, student_pk):
    """
    Record a deposit or withdrawal. Admins only.

    Two ways to call this:
    - Normal browser form submit (the existing pocketmoney/add.html page):
      works exactly as before, redirects to "next" or the Pocket Money
      detail page on success.
    - Fetch/AJAX (sends the X-Requested-With: XMLHttpRequest header, as
      used by the quick Deposit/Withdraw panel on the student's own
      profile page): returns JSON instead of redirecting, so that panel
      can update the balance in place without leaving the page.
    """
    student = get_object_or_404(Student, pk=student_pk)
    next_url = request.POST.get('next') or request.GET.get('next')
    ajax = _is_ajax(request)

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
            except ValueError as exc:
                if ajax:
                    return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
                form.add_error(None, str(exc))
            else:
                new_balance = get_balance(student)
                if ajax:
                    return JsonResponse({'ok': True, 'balance': str(new_balance)})
                messages.success(request, "Transaction recorded successfully.")
                return redirect(next_url) if next_url else redirect('pocketmoney:detail', student_pk=student.pk)
        elif ajax:
            first_error = next(iter(form.errors.values()))[0] if form.errors else "Invalid amount."
            return JsonResponse({'ok': False, 'error': first_error}, status=400)
    else:
        form = TransactionForm()

    return render(request, 'pocketmoney/add.html', {
        'form': form,
        'student': student,
        'balance': get_balance(student),
        'next': next_url,
    })


@superuser_required
def delete(request, student_pk, transaction_pk):
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
