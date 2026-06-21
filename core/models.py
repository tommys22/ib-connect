"""
Database models for the alumni map.

Two worlds live here and must stay separate:

1. SHARED, community-built data: `Alumni` (plus, in later phases, the
   verification / edit / flag tables). This holds ONLY public, professional
   info and is owned by the whole cohort.

2. PRIVATE, per-student data: `Outreach`. This is one student's own notes and
   personal contact details for an alumnus. It is never shown to anyone else
   and never merged back into the shared `Alumni` record.
"""

from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from django.utils import timezone

# How long an entry stays "fresh" before we nudge for re-verification.
REVERIFY_AFTER = timedelta(days=182)  # ~6 months


class User(AbstractUser):
    """
    Our user is a standard Django user plus a single `is_admin` flag.

    `is_admin` gates the maintainer-only review pages (pending edits, flags).
    It is intentionally separate from Django's built-in `is_staff`/`is_superuser`
    so the Django admin site and our own review queue can be managed independently.

    Note: we keep username-based login (Django's default). The signup form sets
    `username` equal to the student's @uw.edu email, so students log in with
    their email address.
    """

    is_admin = models.BooleanField(
        default=False,
        help_text="Can access the review queue (pending edits and flags).",
    )

    def __str__(self):
        return self.email or self.username


class Alumni(models.Model):
    """
    A shared, community-built directory entry for one alumnus.

    PRIVACY RULE: only public, professional information belongs here. Personal
    contact info (personal email, phone) must NEVER be stored on this model —
    that lives on `Outreach`, which is private to each student.
    """

    # --- Status (used by flagging / admin review in later phases) ---
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        FLAGGED = "flagged", "Flagged"

    # --- Public professional fields ---
    name = models.CharField(max_length=200)
    grad_year = models.PositiveIntegerField(null=True, blank=True)
    major = models.CharField(max_length=200, blank=True)
    firm = models.CharField(max_length=200, blank=True)
    firm_tier = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. Bulge bracket, Boutique, MM — however you classify firms.",
    )
    group_division = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200, blank=True)
    office_city = models.CharField(max_length=120, blank=True)
    linkedin_url = models.URLField(blank=True)
    open_to_chat = models.BooleanField(
        default=False,
        help_text="Has this alumnus indicated they're open to chatting with students?",
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Where this entry came from (e.g. LinkedIn, personal network).",
    )

    # --- Crowdsourcing / trust metadata ---
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.APPROVED,  # entries go live immediately so the map fills fast
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # keep the entry even if the contributor's account is removed
        null=True,
        blank=True,
        related_name="alumni_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # `verified_count` is DERIVED from AlumniVerification rows (added in Phase 2).
    # We store it on the row as a denormalized counter so list/sort queries stay fast.
    verified_count = models.PositiveIntegerField(default=0)
    last_verified = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "alumni"  # Django would otherwise say "Alumnis"
        ordering = ["name"]

    def __str__(self):
        firm = f" — {self.firm}" if self.firm else ""
        return f"{self.name}{firm}"

    @property
    def needs_reverification(self):
        """
        True when the entry was verified at least once but that confirmation is
        now older than ~6 months. Drives the subtle "needs re-verification"
        badge. (Never-verified entries don't get the badge; they simply show
        as "not yet verified".)
        """
        if not self.last_verified:
            return False
        return self.last_verified < timezone.localdate() - REVERIFY_AFTER


class AlumniVerification(models.Model):
    """
    One student's confirmation that an alumnus entry is "still accurate".

    There is at most one row per (alumni, user). Re-confirming updates
    `verified_at` to refresh the date rather than adding a second row.
    `Alumni.verified_count` is derived from the number of these rows.
    """

    alumni = models.ForeignKey(
        Alumni, on_delete=models.CASCADE, related_name="verifications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="verifications"
    )
    verified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # Enforce "one confirmation per student per alumnus" at the DB level.
        constraints = [
            models.UniqueConstraint(
                fields=["alumni", "user"], name="unique_verification_per_user"
            )
        ]

    def __str__(self):
        return f"{self.user} verified {self.alumni}"


class AlumniEdit(models.Model):
    """
    A suggested correction to an alumnus, submitted by a student.

    Students never overwrite shared data directly. Instead they propose changes,
    which sit as `pending` until the maintainer accepts (applies them) or rejects
    them on the review page.

    `proposed_changes` is a JSON dict of {field_name: new_value} holding ONLY the
    fields the student actually changed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    alumni = models.ForeignKey(
        Alumni, on_delete=models.CASCADE, related_name="edits"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="edits_suggested",
    )
    proposed_changes = models.JSONField(default=dict)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]  # oldest first in the review queue

    def __str__(self):
        return f"Edit to {self.alumni} ({self.status})"


class AlumniFlag(models.Model):
    """
    A student's report that an alumnus entry is wrong or inappropriate.

    Flags show up in the maintainer's review queue. `resolved` lets the
    maintainer mark a flag as handled so it leaves the open list. (The spec's
    core fields are alumni/user/reason/created_at; `resolved` is a small,
    practical addition so resolved flags don't linger forever.)
    """

    alumni = models.ForeignKey(
        Alumni, on_delete=models.CASCADE, related_name="flags"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="flags_raised",
    )
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]  # oldest first

    def __str__(self):
        return f"Flag on {self.alumni}"


class Outreach(models.Model):
    """
    One student's PRIVATE outreach tracking for one alumnus.

    This is where personal contact info and private notes live. It is scoped to
    a single `student` and must never be exposed to other users or copied into
    the shared `Alumni` record.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,  # if the student leaves, their private notes go too
        related_name="outreach_entries",
    )
    alumni = models.ForeignKey(
        Alumni,
        on_delete=models.CASCADE,
        related_name="outreach_entries",
    )

    # Private contact details — deliberately NOT on the shared Alumni model.
    personal_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)

    # Simple personal pipeline state + free-form notes.
    stage = models.CharField(
        max_length=40,
        blank=True,
        help_text="Your own status, e.g. 'to contact', 'emailed', 'call booked'.",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A student keeps at most one private outreach record per alumnus.
        unique_together = ("student", "alumni")
        verbose_name_plural = "outreach"

    def __str__(self):
        return f"{self.student} -> {self.alumni}"
