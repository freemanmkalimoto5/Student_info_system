from django.shortcuts import redirect
from django.urls import reverse

from .models import AdminProfile


class AdminProfileMiddleware:
    """
    First-login gate for admins and clerks.

    If a logged-in staff user has not completed their profile yet (they
    were just added by a superuser), EVERY request is redirected to the
    "complete your profile" form until they finish it -- so right after
    their first login they see that form and nothing else.

    A staff account that was created some other way (for example straight
    in the Django admin) and has no AdminProfile at all gets an unfinished
    one created here, so it goes through the same form. Superusers and
    parent logins are never affected.
    """
    EXEMPT_PATH_NAMES = {'accounts:complete_profile', 'accounts:logout'}

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = {reverse(name) for name in self.EXEMPT_PATH_NAMES}

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            profile = getattr(user, 'admin_profile', None)
            if profile is None and user.is_staff and not user.is_superuser:
                profile, _ = AdminProfile.objects.get_or_create(
                    user=user, defaults={'profile_completed': False, 'role': 'admin'}
                )

            if profile and not profile.profile_completed:
                is_exempt = (
                    request.path in self.exempt_paths
                    or request.path.startswith('/static/')
                    or request.path.startswith('/media/')
                )
                if not is_exempt:
                    return redirect('accounts:complete_profile')
        return self.get_response(request)
