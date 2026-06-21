"""
Forms for the alumni map.

For now this only holds the signup form. Phase 1+ will add the add-alumnus,
suggest-edit, and flag forms.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Alumni, AlumniFlag, User

# Only allow students to register: any university email (ends in ".edu").
# This keeps signups student-only while opening it beyond a single school.
STUDENT_EMAIL_SUFFIX = ".edu"

# The public, professional fields of an alumnus. Defined once and reused by both
# the "add" form and the "suggest edit" form so they can never drift apart.
# (Personal email/phone are intentionally absent — they aren't on the model.)
PUBLIC_ALUMNI_FIELDS = [
    "name", "grad_year", "major", "firm", "firm_tier",
    "group_division", "title", "office_city", "linkedin_url",
    "open_to_chat", "source",
]


class SignUpForm(UserCreationForm):
    """
    Registration form that requires a real university (.edu) email.

    We don't show a separate "username" box. Instead the email IS the username,
    so students simply log in with their school email and password.
    """

    email = forms.EmailField(
        required=True,
        help_text="Use your university (.edu) email address.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)  # password1/password2 come from UserCreationForm

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # Allow any university email so students at any school can join.
        if not email.endswith(STUDENT_EMAIL_SUFFIX):
            raise forms.ValidationError("Please sign up with a university (.edu) email address.")
        # Don't let two people register the same email.
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Use the email as the username so login is by email.
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class AlumniForm(forms.ModelForm):
    """
    Form to add an alumnus to the SHARED directory.

    PRIVACY: this form deliberately exposes ONLY public, professional fields.
    Personal email/phone aren't even on the Alumni model, so there's no way to
    submit them here — they belong on a student's private Outreach record.

    Fields NOT shown (set automatically by the view): status, added_by,
    verified_count, last_verified, created_at.
    """

    class Meta:
        model = Alumni
        fields = PUBLIC_ALUMNI_FIELDS
        widgets = {
            "grad_year": forms.NumberInput(attrs={"placeholder": "e.g. 2021"}),
            "linkedin_url": forms.URLInput(attrs={"placeholder": "https://www.linkedin.com/in/…"}),
        }


class FlagForm(forms.ModelForm):
    """Report an entry as wrong/inappropriate. Just asks for a short reason."""

    class Meta:
        model = AlumniFlag
        fields = ["reason"]
        widgets = {
            "reason": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "What's wrong with this entry? (e.g. wrong firm, duplicate, inappropriate)",
            }),
        }


class SuggestEditForm(forms.ModelForm):
    """
    Form to SUGGEST corrections to an existing alumnus.

    Important: submitting this does NOT change the shared record directly. The
    view pre-fills it with the current values, figures out which fields the
    student actually changed, and saves those as a pending AlumniEdit for the
    maintainer to accept or reject. Same public fields as AlumniForm.
    """

    class Meta:
        model = Alumni
        fields = PUBLIC_ALUMNI_FIELDS
