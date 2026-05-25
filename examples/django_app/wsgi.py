"""
Django Example — Sentinel SDK
Add 2 lines to your Django app for AI auto-healing!

SETUP STEPS:
1. Add to settings.py INSTALLED_APPS:
      'sentinel_sdk',
2. Add to wsgi.py (shown below)
"""

# ─── wsgi.py ──────────────────────────────────────────────────────
import os
from django.core.wsgi import get_wsgi_application
from sentinel_sdk import Sentinel

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

application = get_wsgi_application()

# ── 2 Lines ───────────────────────────────────────────────────────
Sentinel(
    api_key          = "YOUR_GEMINI_API_KEY",
    app_name         = "DjangoDemo",
    elastic_url      = "https://your-deployment.es.io",
    elastic_password = "your_elastic_password",
    email_to         = "you@example.com",
    smtp_user        = "alerts@gmail.com",
    smtp_pass        = "gmail_app_password",
    whatsapp_to      = "whatsapp:+919876543210",
    twilio_sid       = "ACxxxxxxxx",
    twilio_token     = "xxxxxxxx",
).attach(application)
# ─────────────────────────────────────────────────────────────────


# ─── settings.py (add these lines) ───────────────────────────────
"""
INSTALLED_APPS = [
    ...
    'sentinel_sdk',   # ← Add this
]

MIDDLEWARE = [
    ...
    # Sentinel auto-injects itself — no middleware needed manually
]
"""


# ─── views.py (example views to test Sentinel) ───────────────────
"""
from django.http import JsonResponse

def home(request):
    return JsonResponse({"status": "running", "app": "DjangoDemo"})

def crash(request):
    # This will trigger Sentinel automatically!
    raise ConnectionError("ECONNREFUSED: DB connection refused on port 5432")

def memory_error(request):
    raise MemoryError("OutOfMemoryError: heap space exhausted")
"""


# ─── urls.py (example urls to test) ──────────────────────────────
"""
from django.urls import path
from . import views

urlpatterns = [
    path('',       views.home,         name='home'),
    path('crash/', views.crash,        name='crash'),
    path('memory/',views.memory_error, name='memory'),
]
"""
