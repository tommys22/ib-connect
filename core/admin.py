"""
Register models with Django's built-in admin site (/admin/).

This gives you, the maintainer, a quick way to inspect and hand-edit data.
The dedicated review queue for pending edits/flags comes in Phase 3.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Alumni, AlumniEdit, AlumniFlag, AlumniVerification, Outreach, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Show our extra is_admin flag in the user list and edit form.
    list_display = ("username", "email", "is_admin", "is_staff", "is_active")
    # Add is_admin to the standard "Permissions" section of the user edit page.
    fieldsets = UserAdmin.fieldsets + (("App role", {"fields": ("is_admin",)}),)


@admin.register(Alumni)
class AlumniAdmin(admin.ModelAdmin):
    list_display = ("name", "firm", "grad_year", "status", "verified_count", "last_verified")
    list_filter = ("status", "firm_tier", "open_to_chat")
    search_fields = ("name", "firm", "major", "title")


@admin.register(AlumniVerification)
class AlumniVerificationAdmin(admin.ModelAdmin):
    list_display = ("alumni", "user", "verified_at")
    list_filter = ("verified_at",)


@admin.register(AlumniEdit)
class AlumniEditAdmin(admin.ModelAdmin):
    list_display = ("alumni", "user", "status", "created_at")
    list_filter = ("status",)


@admin.register(AlumniFlag)
class AlumniFlagAdmin(admin.ModelAdmin):
    list_display = ("alumni", "user", "resolved", "created_at")
    list_filter = ("resolved",)


@admin.register(Outreach)
class OutreachAdmin(admin.ModelAdmin):
    # Private per-student data — visible to you in admin, but never on the public site.
    list_display = ("student", "alumni", "stage", "updated_at")
    list_filter = ("stage",)
