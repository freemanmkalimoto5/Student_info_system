from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.accounts.views import landing

urlpatterns = [
    path('admin/', admin.site.urls),

    path('students/', include('apps.students.urls')),
    path('qrcodes/', include('apps.qrcodes.urls')),
    path('verify/', include('apps.verification.urls')),   # public scan endpoint
    path('accounts/', include('apps.accounts.urls')),
    path('pocketmoney/', include('apps.pocketmoney.urls')),

    # Public welcome page — logged-in users are bounced straight to
    # their student list from inside the view itself.
    path('', landing, name='landing'),
]

# Serve uploaded media (student photos, QR codes) during development.
# In production this is handled by nginx/whatever serves static files.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
