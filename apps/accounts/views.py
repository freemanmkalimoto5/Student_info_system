from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Max
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseNotAllowed

from apps.students.models import Student

from .decorators import admin_required, full_admin_required, superuser_required, is_clerk
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
    profile, _ = AdminProfile.objects.get_or_create(
        user=request.user, defaults={'profile_completed': True}
    )
    if request.method == 'POST':
        form = SiteSettingsForm(request.POST, request.FILES, instance=site_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully.")
            return redirect('accounts:settings')
    else:
        form = SiteSettingsForm(instance=site_settings)

    return render(request, 'accounts/settings.html', {
        'form': form,
        'current_theme': profile.theme,
        'theme_choices': AdminProfile.THEME_CHOICES,
    })


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


@superuser_required
def add_admin(request):
    """
    Superuser-only: create a new login as a Superuser, a full Admin, or
    a restricted Clerk. Admins and clerks cannot reach this page. The new
    account completes their own profile on first login (see
    complete_profile below).
    """
    if request.method == 'POST':
        form = AddAdminForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']
            make_superuser = role == 'superuser'
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                is_staff=True,
                is_superuser=make_superuser,
            )
            # A superuser's access comes from is_superuser itself; their
            # profile row just holds their details ('admin' is its neutral role).
            AdminProfile.objects.create(
                user=user, profile_completed=False,
                role='admin' if make_superuser else role,
            )
            messages.success(
                request,
                f"{role.title()} account \"{user.username}\" created. "
                f"They'll be asked to complete their profile on first login."
            )
            return redirect('accounts:administrators')
    else:
        form = AddAdminForm()

    return render(request, 'accounts/add_admin.html', {'form': form})


@login_required
def complete_profile(request):
    """
    Shown automatically (via AdminProfileMiddleware) to a newly added
    admin/clerk the first time they log in. Nothing else in the system
    opens until every field here is filled in.
    """
    profile = getattr(request.user, 'admin_profile', None)
    if profile is None or profile.profile_completed:
        return redirect('students:list')

    if request.method == 'POST':
        form = AdminProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            first = form.cleaned_data['first_name']
            middle = form.cleaned_data['middle_name']
            last = form.cleaned_data['last_name']

            obj = form.save(commit=False)          # also carries the uploaded photo
            obj.full_name = f"{first} {middle} {last}"
            obj.profile_completed = True
            obj.save()

            # First/last name and email live on the User; the real name makes the
            # sidebar and the audit log show who this person is, not just a username.
            request.user.email = form.cleaned_data['email']
            request.user.first_name = first
            request.user.last_name = last
            request.user.save(update_fields=['email', 'first_name', 'last_name'])

            messages.success(request, "Profile completed — welcome aboard!")
            return redirect('students:list')
    else:
        form = AdminProfileForm(instance=profile, initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        })

    return render(request, 'accounts/complete_profile.html', {'form': form})


@superuser_required
def administrators(request):
    """
    Superuser-only overview of every staff login: who they are, how to
    reach them, role, whether they have finished their first-login profile,
    when they last signed in, and how much they have done in the system.
    """
    users = (
        User.objects.filter(is_staff=True)
        .select_related('admin_profile')
        .annotate(action_count=Count('audit_actions', distinct=True),
                  last_action=Max('audit_actions__timestamp'))
        .order_by('-is_superuser', 'date_joined')
    )
    students_added = dict(
        Student.objects.exclude(added_by=None).order_by()
        .values_list('added_by').annotate(n=Count('id'))
    )

    admins = []
    counts = {'superuser': 0, 'admin': 0, 'clerk': 0, 'pending': 0}
    for u in users:
        profile = getattr(u, 'admin_profile', None)

        if u.is_superuser:
            role_key, role_label = 'superuser', 'Superuser'
        elif profile and profile.role == 'clerk':
            role_key, role_label = 'clerk', 'Clerk'
        else:
            role_key, role_label = 'admin', 'Admin'
        counts[role_key] += 1

        # The original superuser (from createsuperuser) has no profile row and
        # is never "pending"; a superuser ADDED through the app has one and
        # must finish the first-login form like everyone else.
        awaiting = (profile is None and not u.is_superuser) or (profile is not None and not profile.profile_completed)
        if awaiting:
            counts['pending'] += 1
        if awaiting and u.last_login is None:
            state, state_label = 'pending', 'Has not logged in yet'
        elif awaiting:
            state, state_label = 'pending', 'Profile pending'
        elif u.is_superuser:
            state, state_label = 'super', 'Superuser'
        else:
            state, state_label = 'ok', 'Profile complete'

        full_name = (profile.full_name if profile and profile.full_name else '') or u.get_full_name()
        phone = profile.phone if profile else ''
        position = profile.position if profile else ''
        admins.append({
            'user': u,
            'profile': profile,
            'display_name': full_name or u.username,
            'full_name': full_name,
            'email': u.email,
            'phone': phone,
            'position': position,
            'role_key': role_key,
            'role_label': role_label,
            'state': state,
            'state_label': state_label,
            'students_added': students_added.get(u.pk, 0),
            'search': ' '.join([u.username, full_name, u.email, phone, position, role_label]).lower(),
        })

    return render(request, 'accounts/administrators.html', {
        'admins': admins,
        'counts': counts,
    })


@full_admin_required
def audit_log(request):
    """Recent create/update/delete history for students and pocket money. Full admins only — not clerks."""
    logs = AuditLog.objects.all()[:200]
    return render(request, 'accounts/audit_log.html', {'logs': logs})


@superuser_required
def audit_log_delete(request, pk):
    """Delete one audit log entry. Superuser only — not even regular admins/clerks."""
    log = get_object_or_404(AuditLog, pk=pk)
    if request.method == 'POST':
        log.delete()
        messages.success(request, "Audit log entry deleted.")
        return redirect('accounts:audit_log')
    return render(request, 'accounts/audit_log_confirm_delete.html', {'log': log})


@superuser_required
def audit_log_clear_all(request):
    """Wipe the entire audit log. Superuser only."""
    if request.method == 'POST':
        count = AuditLog.objects.count()
        AuditLog.objects.all().delete()
        messages.success(request, f"Cleared {count} audit log entr{'y' if count == 1 else 'ies'}.")
        return redirect('accounts:audit_log')
    return render(request, 'accounts/audit_log_confirm_clear.html', {
        'count': AuditLog.objects.count(),
    })



@login_required
def set_theme(request):
    """Saves the caller's own theme choice (Light / Dark / Match System)
    and sends them back wherever they came from."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    theme = request.POST.get('theme', '')
    valid_values = {key for key, _label in AdminProfile.THEME_CHOICES}
    if theme not in valid_values:
        messages.error(request, "Unknown theme choice.")
    else:
        profile, _ = AdminProfile.objects.get_or_create(
            user=request.user, defaults={'profile_completed': True}
        )
        profile.theme = theme
        profile.save(update_fields=['theme'])
        messages.success(request, "Theme updated.")

    next_url = request.POST.get('next') or 'accounts:settings'
    return redirect(next_url)
