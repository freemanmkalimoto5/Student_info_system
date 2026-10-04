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
    

def theme_context(request):
    """
    Makes {{ effective_theme }} available on EVERY page: 'light',
    'dark', or 'system' (follow the device's own light/dark setting).
    Logged-out visitors and any logged-in user without a saved
    preference yet simply get 'system'.
    """
    theme = 'system'
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        profile = getattr(user, 'admin_profile', None)
        if profile is not None:
            theme = profile.theme
    return {'effective_theme': theme}
