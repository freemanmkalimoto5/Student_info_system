from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect

from .decorators import admin_required, full_admin_required, is_clerk
from .forms import SiteSettingsForm, AddAdminForm, AdminProfileForm, ClerkSettingsForm
from .models import SiteSettings, AdminProfile, AuditLog


def landing(request):
    """
    Public welcome page — the site root. No login required. If the
    person is already logged in, send them straight to their student
    list instead of showing the welcome screen again.
    """
    if request.user.is_authenticated:
        return redirect('students:list')
    return render(request, 'landing.html')


class LoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'


class LogoutView(auth_views.LogoutView):
    next_page = 'accounts:login'


@admin_required
def settings_view(request):
    """
    Full admins/superusers get the complete Settings page (school
    branding, admin management, system access). Clerks get a
    cut-down version: just their own contact info, theme, and
    language — see ClerkSettingsForm.
    """
    if is_clerk(request.user):
        return _clerk_settings(request)

    site_settings = SiteSettings.load()
    if request.method == 'POST':
        form = SiteSettingsForm(request.POST, request.FILES, instance=site_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully.")
            return redirect('accounts:settings')
    else:
        form = SiteSettingsForm(instance=site_settings)

    return render(request, 'accounts/settings.html', {'form': form})


def _clerk_settings(request):
    # Lazily create a profile if one somehow doesn't exist yet (should
    # always exist for a clerk, since add_admin creates it).
    profile, _ = AdminProfile.objects.get_or_create(
        user=request.user, defaults={'profile_completed': True}
    )

    if request.method == 'POST':
        form = ClerkSettingsForm(request.POST)
        if form.is_valid():
            request.user.email = form.cleaned_data['email']
            request.user.save(update_fields=['email'])

            profile.phone = form.cleaned_data['phone']
            profile.theme = form.cleaned_data['theme']
            profile.language = form.cleaned_data['language']
            profile.save(update_fields=['phone', 'theme', 'language'])

            messages.success(request, "Your settings were updated.")
            return redirect('accounts:settings')
    else:
        form = ClerkSettingsForm(initial={
            'email': request.user.email,
            'phone': profile.phone,
            'theme': profile.theme,
            'language': profile.language,
        })

    return render(request, 'accounts/clerk_settings.html', {'form': form})


@full_admin_required
def add_admin(request):
    """
    Lets an existing full admin/superuser create a new login — either
    a full Admin or a restricted Clerk. Clerks cannot reach this page
    themselves (full_admin_required). The new account completes their
    own profile on first login (see complete_profile below).
    """
    if request.method == 'POST':
        form = AddAdminForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                is_staff=True,
            )
            AdminProfile.objects.create(
                user=user, profile_completed=False, role=form.cleaned_data['role']
            )
            messages.success(
                request,
                f"{form.cleaned_data['role'].title()} account \"{user.username}\" created. "
                f"They'll be asked to complete their profile on first login."
            )
            return redirect('accounts:settings')
    else:
        form = AddAdminForm()

    return render(request, 'accounts/add_admin.html', {'form': form})


@login_required
def complete_profile(request):
    """
    Shown automatically (via AdminProfileMiddleware) to a newly added
    admin/clerk the first time they log in, before they can use the
    rest of the system.
    """
    profile = getattr(request.user, 'admin_profile', None)
    if profile is None or profile.profile_completed:
        return redirect('students:list')

    if request.method == 'POST':
        form = AdminProfileForm(request.POST, instance=profile)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.profile_completed = True
            obj.save()
            messages.success(request, "Profile completed — welcome aboard!")
            return redirect('students:list')
    else:
        form = AdminProfileForm(instance=profile)

    return render(request, 'accounts/complete_profile.html', {'form': form})


@full_admin_required
def audit_log(request):
    """Recent create/update/delete history for students and pocket money. Full admins only — not clerks."""
    logs = AuditLog.objects.all()[:200]
    return render(request, 'accounts/audit_log.html', {'logs': logs})
