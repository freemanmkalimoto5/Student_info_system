from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def user_role(user):
    """
    Returns 'superuser', 'admin', 'clerk', or 'parent'/'none' for any
    logged-in user. Staff accounts without an AdminProfile (e.g. an
    original superuser who hasn't visited Settings yet) count as
    'admin' — full access — since AdminProfile.role only exists to
    optionally *restrict* a staff account down to 'clerk'.
    """
    if not user.is_authenticated:
        return 'none'
    if user.is_superuser:
        return 'superuser'
    if user.is_staff:
        profile = getattr(user, 'admin_profile', None)
        if profile and profile.role == 'clerk':
            return 'clerk'
        return 'admin'
    if getattr(user, 'parent_account', None):
        return 'parent'
    return 'none'


def is_full_admin(user):
    """Superuser or a staff account with the 'admin' role — everything except clerks are locked out of."""
    return user_role(user) in ('superuser', 'admin')


def is_clerk(user):
    return user_role(user) == 'clerk'


def admin_required(view_func):
    """
    Restricts a view to superusers and staff accounts (admins AND
    clerks) — used for day-to-day management: Register Student, Bulk
    Import, Edit/Delete Student, adding Pocket Money transactions.
    Regular logged-in accounts (e.g. parent logins) get a clean 403.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.user.is_superuser or request.user.is_staff:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only administrators can access this page.")
    return _wrapped


def full_admin_required(view_func):
    """
    Restricts a view to superusers and 'admin'-role staff — excludes
    clerks. Used for the Audit Log and for adding new admin/clerk
    accounts (a clerk can't grant themselves or anyone else more
    access).
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if is_full_admin(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only full administrators can access this page.")
    return _wrapped


def superuser_required(view_func):
    """
    Restricts a view to Django superusers only — used for deleting
    pocket money transactions, which even a regular admin/clerk
    should not be able to erase.
    """
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("Only the superuser can perform this action.")
    return _wrapped
