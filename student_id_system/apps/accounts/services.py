"""
Account-related business logic: auto-creating parent logins,
recording audit trail entries, and sending WhatsApp notifications via
a self-hosted WAHA (WhatsApp HTTP API) server. Kept separate from
views.py so it can be called from the students app (CSV import,
create/update/delete views) without circular imports.
"""
import logging

from django.conf import settings
from django.contrib.auth.models import User

from .models import ParentAccount, AuditLog

logger = logging.getLogger(__name__)


def _unique_username(base):
    """
    Ensures usernames don't collide when two different parents happen
    to share the same exact name — appends a number to the second,
    third, etc. (e.g. "John Doe", then "John Doe2").
    """
    base = base or 'Parent'
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}{counter}"
    return username


def send_whatsapp_message(phone_number, message):
    """
    Sends a WhatsApp message through a self-hosted WAHA server
    (https://waha.devlike.pro/). Requires WAHA_BASE_URL to be set in
    .env — until then, this just logs the message and does nothing,
    so the rest of the app keeps working even without WAHA configured.

    Never raises — a failed/misconfigured WhatsApp send should never
    block the actual action (registering a student, recording pocket
    money, etc). Errors are logged instead.
    """
    if not phone_number:
        return False

    base_url = getattr(settings, 'WAHA_BASE_URL', '')
    if not base_url:
        logger.info("WAHA_BASE_URL not configured — skipping WhatsApp send to %s: %s", phone_number, message)
        return False

    chat_id = _to_whatsapp_chat_id(phone_number)

    try:
        import requests

        headers = {}
        api_key = getattr(settings, 'WAHA_API_KEY', '')
        if api_key:
            headers['X-Api-Key'] = api_key

        response = requests.post(
            f"{base_url.rstrip('/')}/api/sendText",
            json={
                'session': getattr(settings, 'WAHA_SESSION', 'default'),
                'chatId': chat_id,
                'text': message,
            },
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send WhatsApp message to %s via WAHA", phone_number)
        return False


def _to_whatsapp_chat_id(phone_number):
    """
    Converts a locally-formatted number (e.g. "0700000000") into the
    international format WAHA expects (e.g. "255700000000@c.us").
    WHATSAPP_COUNTRY_CODE in settings controls the country code used
    when a number starts with a leading 0 (defaults to Tanzania, 255).
    """
    number = phone_number.strip().replace(' ', '').replace('-', '')
    if number.startswith('+'):
        number = number[1:]
    elif number.startswith('0'):
        country_code = getattr(settings, 'WHATSAPP_COUNTRY_CODE', '255')
        number = f"{country_code}{number[1:]}"
    return f"{number}@c.us"


def sync_parent_account(student, full_name, phone, relationship, whatsapp=None):
    """
    Ensures a login exists for one parent/guardian of a student:
      - username: their name EXACTLY as typed on the student form
        (e.g. "John Doe" stays "John Doe" — not slugified/lowercased)
      - password: their phone number, exactly as entered

    Keyed by phone number, so if a sibling is registered later with
    the same parent, the existing login is reused instead of creating
    a duplicate — both students just get linked to the same account.

    A brand-new account gets a one-time WhatsApp message with their
    login details (best-effort — see send_whatsapp_message).

    Does nothing if either name or phone is missing.
    """
    if not full_name or not phone:
        return

    full_name = full_name.strip()
    phone = phone.strip()
    if not full_name or not phone:
        return

    account = ParentAccount.objects.filter(phone=phone).first()

    if account is None:
        username = _unique_username(full_name)
        user = User.objects.create_user(username=username, password=phone)
        account = ParentAccount.objects.create(
            user=user, full_name=full_name, phone=phone, relationship=relationship
        )
        welcome_number = whatsapp or phone
        send_whatsapp_message(
            welcome_number,
            f"Hello {full_name}, you've been registered as a parent/guardian on "
            f"the Student ID System.\nLogin username: {username}\n"
            f"Login password: your phone number ({phone})."
        )
    elif account.full_name != full_name:
        # Staff corrected/updated the parent's name — keep it current.
        account.full_name = full_name
        account.save(update_fields=['full_name'])

    account.students.add(student)


def sync_all_parent_accounts(student):
    """Runs sync_parent_account for father, mother, and guardian at once."""
    sync_parent_account(
        student, student.father_name, student.father_phone, 'Father',
        whatsapp=student.father_whatsapp
    )
    sync_parent_account(
        student, student.mother_name, student.mother_phone, 'Mother',
        whatsapp=student.mother_whatsapp
    )
    sync_parent_account(
        student, student.guardian_name, student.guardian_phone,
        student.guardian_relationship or 'Guardian'
    )


def log_action(student, action, user):
    """Records one audit log entry for a student create/update/delete."""
    performed_by_name = user.get_full_name() or user.username if user else ''
    AuditLog.objects.create(
        student_number=student.student_number,
        student_name=student.full_name,
        action=action,
        performed_by=user,
        performed_by_name=performed_by_name,
    )
