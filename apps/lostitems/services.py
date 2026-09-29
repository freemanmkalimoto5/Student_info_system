"""Business logic for lost items: payments, report data, WhatsApp message."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import LostItem, LostItemPayment


def money(value):
    return f"TSh {Decimal(value):,.0f}"


# ---------------- payments ----------------
@transaction.atomic
def add_payment(item, amount, note, user):
    """Record a payment (full or partial). Status updates automatically."""
    item = LostItem.objects.select_for_update().get(pk=item.pk)
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if amount > item.balance:
        raise ValueError(f"You cannot pay more than the balance ({money(item.balance)}).")
    payment = LostItemPayment.objects.create(item=item, amount=amount, note=note, received_by=user)
    item.save()          # recalculates status / paid_at from the payments
    return payment


# ---------------- report ----------------
def report_data(student):
    items = list(student.lost_items.prefetch_related('payments').order_by('date_lost', 'id'))
    total = sum((i.price for i in items), Decimal('0'))
    paid = sum((i.amount_paid for i in items), Decimal('0'))
    balance = sum((i.balance for i in items), Decimal('0'))
    payments = sorted((p for i in items for p in i.payments.all()), key=lambda p: p.created_at)
    return {
        'items': items,
        'payments': payments,
        'total': total,
        'paid': paid,
        'balance': balance,
        'percent': int(paid * 100 / total) if total else 0,
        'generated_at': timezone.localtime(),
    }


def parent_numbers(student):
    """[(label, number)] WhatsApp number if set, else phone. Guardian only if no parent has one."""
    found, seen = [], set()

    def add(label, whatsapp, phone):
        number = (whatsapp or phone or '').strip()
        if number and number not in seen:
            seen.add(number)
            found.append((label, number))

    add('Father', student.father_whatsapp, student.father_phone)
    add('Mother', student.mother_whatsapp, student.mother_phone)
    if not found:
        add('Guardian', '', student.guardian_phone)
    return found


def build_report_text(student):
    from apps.accounts.models import SiteSettings
    site = SiteSettings.load()
    r = report_data(student)

    lines = [
        "*LOST ITEMS REPORT*",
        site.school_name,
        "",
        f"Student: {student.full_name} ({student.student_number})",
        f"Class: {student.get_grade_class_display()}",
        f"Date: {r['generated_at']:%d %b %Y}",
        "",
    ]
    if not r['items']:
        lines.append("No lost items recorded.")
    for n, item in enumerate(r['items'], start=1):
        lines.append(f"{n}. {item.item_name} (lost {item.date_lost:%d %b %Y})")
        lines.append(f"   Price: {money(item.price)}")
        lines.append(f"   Paid: {money(item.amount_paid)}")
        lines.append(f"   Balance: {money(item.balance)}")
        lines.append(f"   Status: {item.get_status_display()}")
    lines += [
        "",
        f"*Total:* {money(r['total'])}",
        f"*Paid:* {money(r['paid'])}",
        f"*Balance due:* {money(r['balance'])}",
    ]
    if r['balance'] > 0:
        lines += ["", "Please contact the school to clear the outstanding balance."]
    return "\n".join(lines)


def send_report_to_parents(student):
    """Returns (messages_attempted_ok, numbers_found)."""
    from apps.accounts.services import send_whatsapp_message

    targets = parent_numbers(student)
    message = build_report_text(student)
    ok = 0
    for _label, phone in targets:
        try:
            send_whatsapp_message(phone, message)
            ok += 1
        except Exception:
            continue
    return ok, len(targets)
