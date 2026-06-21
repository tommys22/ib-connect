"""
Top-level URL configuration.

- /admin/        Django's built-in admin site (for you, the maintainer)
- /accounts/...  Django's built-in auth views (login, logout, password reset)
- everything else is handled by the core app (core/urls.py)
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Provides login/, logout/, and password-management routes.
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("core.urls")),
]
