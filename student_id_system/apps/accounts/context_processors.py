from .models import SiteSettings
from .decorators import user_role


def site_settings(request):
    """
    Makes `site_settings` (school name/logo/contact info) available in
    every template automatically, without each view needing to pass it.
    """
    return {'site_settings': SiteSettings.load()}


def role_context(request):
    """
    Makes `is_full_admin` / `is_clerk` available in every template, so
    e.g. the sidebar can hide Audit Log from clerks without repeating
    the role logic in each template.
    """
    role = user_role(request.user)
    return {
        'is_full_admin': role in ('superuser', 'admin'),
        'is_clerk': role == 'clerk',
    }
