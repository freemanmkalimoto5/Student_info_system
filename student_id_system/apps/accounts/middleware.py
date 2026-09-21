from django.shortcuts import redirect
from django.urls import reverse


class AdminProfileMiddleware:
    """
    If a logged-in user has an AdminProfile that isn't completed yet
    (i.e. they were just added as an admin via Settings > Add Admin),
    redirect every request to the "complete your profile" form until
    they finish it. Accounts without an AdminProfile at all (the
    original superuser, or parent logins) are unaffected.
    """
    EXEMPT_PATH_NAMES = {'accounts:complete_profile', 'accounts:logout'}

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = {reverse(name) for name in self.EXEMPT_PATH_NAMES}

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, 'admin_profile', None)
            if profile and not profile.profile_completed:
                is_exempt = (
                    request.path in self.exempt_paths
                    or request.path.startswith('/static/')
                    or request.path.startswith('/media/')
                )
                if not is_exempt:
                    return redirect('accounts:complete_profile')
        return self.get_response(request)
