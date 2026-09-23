from decimal import Decimal

from django.db.models import Sum, Case, When, F, DecimalField

from .models import Transaction


def get_balance(student):
    """
    Current pocket money balance: sum of deposits minus sum of
    withdrawals. Computed fresh each time from the transaction
    history, never stored, so it can't drift out of sync.
    """
    result = Transaction.objects.filter(student=student).aggregate(
        total=Sum(
            Case(
                When(transaction_type='deposit', then=F('amount')),
                When(transaction_type='withdrawal', then=-F('amount')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )
    return result['total'] or Decimal('0.00')


def add_transaction(student, transaction_type, amount, note, user, notify=True):
    """
    Records a deposit or withdrawal. Raises ValueError if a withdrawal
    would take the balance negative — pocket money can't go below zero.
    Logged in both the Transaction table (this app) and the shared
    AuditLog (see apps.accounts), and sends a WhatsApp notification to
    the student's parents afterward (best-effort; failures are logged,
    never block the transaction) unless notify=False (used during bulk
    CSV import so hundreds of network calls don't slow it down).
    """
    from apps.accounts.services import log_action

    if transaction_type == 'withdrawal':
        current_balance = get_balance(student)
        if amount > current_balance:
            raise ValueError(
                f"Cannot withdraw {amount} — current balance is only {current_balance}."
            )

    transaction = Transaction.objects.create(
        student=student,
        transaction_type=transaction_type,
        amount=amount,
        note=note,
        created_by=user,
    )

    audit_action = 'pocket_money_deposit' if transaction_type == 'deposit' else 'pocket_money_withdrawal'
    log_action(student, audit_action, user)

    if notify:
        _notify_parents(student, transaction)
    return transaction


def delete_transaction(transaction, user):
    """
    Deletes a transaction record. Logged to the audit trail before
    deletion (so the log still shows what was removed and by whom).
    Restricted to superusers — see apps.accounts.decorators.superuser_required
    on the view that calls this.
    """
    from apps.accounts.services import log_action

    log_action(transaction.student, 'pocket_money_deleted', user)
    transaction.delete()


def get_recent_transactions(student, limit=3):
    """The most recent deposit/withdrawal dates — used for the quick-glance summary on the detail page."""
    return Transaction.objects.filter(student=student)[:limit]


def _notify_parents(student, transaction):
    """Best-effort WhatsApp notification to whichever parents have a number on file."""
    from apps.accounts.services import send_whatsapp_message

    new_balance = get_balance(student)
    if transaction.transaction_type == 'withdrawal':
        action_line = f"Withdrawn: {transaction.amount}"
    else:
        action_line = f"Deposited: {transaction.amount}"

    message = (
        f"Pocket Money Update — {student.full_name} ({student.student_number})\n"
        f"{action_line}\n"
        f"Total Balance: {new_balance}"
    )
    if transaction.note:
        message += f"\nNote: {transaction.note}"

    for phone in _parent_notification_numbers(student):
        send_whatsapp_message(phone, message)


def _parent_notification_numbers(student):
    """WhatsApp number if set, otherwise falls back to phone number, for each parent."""
    numbers = []
    if student.father_phone:
        numbers.append(student.father_whatsapp or student.father_phone)
    if student.mother_phone:
        numbers.append(student.mother_whatsapp or student.mother_phone)
    return [n for n in numbers if n]
