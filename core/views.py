"""
Views for the alumni map.

Phase 0 (this file's current scope):
- signup            : create a @uw.edu account
- alumni_list       : the shared directory, with search + sort
- alumni_detail     : one alumnus's public record

Later phases add: add-alumnus + dedup, verify, suggest-edit, admin review,
flagging, and contribution counts.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AlumniForm, FlagForm, SignUpForm, SuggestEditForm
from .models import Alumni, AlumniEdit, AlumniFlag, AlumniVerification


def admin_required(view):
    """
    Decorator for maintainer-only pages (the review queue).

    - Not logged in  -> send to the login page.
    - Logged in but not an admin -> 403 Forbidden (they shouldn't be here).
    - Admin -> allowed through.
    """
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


# --- Dedup helpers (Phase 1) -------------------------------------------------
# Goal: stop two students from creating duplicate entries for the same person.
# We use "normalized exact" matching (case- and whitespace-insensitive), NOT
# fuzzy matching, so the behaviour is predictable and easy to reason about.

def _norm(value):
    """Lowercase and collapse all runs of whitespace to a single space."""
    return " ".join((value or "").split()).lower()


def _norm_url(url):
    """Normalize a LinkedIn URL for comparison: lowercase, no trailing slash."""
    return (url or "").strip().lower().rstrip("/")


def find_possible_duplicates(name, firm, linkedin_url, exclude_pk=None):
    """
    Return existing alumni that look like the same person as the submission.

    A row matches if EITHER:
      - its LinkedIn URL matches (strongest signal), or
      - its name AND firm both match (normalized).

    This scans all alumni in Python. That's intentionally simple and is fine at
    cohort scale (hundreds–low thousands). If the directory ever gets large,
    swap this for indexed/normalized DB columns.
    """
    n_url = _norm_url(linkedin_url)
    n_name = _norm(name)
    n_firm = _norm(firm)

    matches = []
    candidates = Alumni.objects.all()
    if exclude_pk:
        candidates = candidates.exclude(pk=exclude_pk)

    for alum in candidates:
        # 1. Same LinkedIn URL.
        if n_url and _norm_url(alum.linkedin_url) == n_url:
            matches.append(alum)
            continue
        # 2. Same name + firm.
        if n_name and _norm(alum.name) == n_name and _norm(alum.firm) == n_firm:
            matches.append(alum)
    return matches


def signup(request):
    """Register a new @uw.edu student and log them straight in."""
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # log in immediately after signup
            return redirect("alumni_list")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


# Sort options exposed in the directory UI. Maps a URL value -> queryset ordering.
SORT_OPTIONS = {
    "name": ("Name (A–Z)", ["name"]),
    "recent": ("Recently added", ["-created_at"]),
    "verified": ("Most verified", ["-verified_count", "name"]),
}


@login_required
def alumni_list(request):
    """
    The shared directory. Supports a free-text search box and a sort dropdown.

    We only show entries that aren't hidden. (Flagging in Phase 4 can set an
    entry's status to 'flagged'; we keep those out of the public list.)
    """
    alumni = Alumni.objects.exclude(status=Alumni.Status.FLAGGED)

    # --- Search across the public text fields ---
    query = request.GET.get("q", "").strip()
    if query:
        alumni = alumni.filter(
            Q(name__icontains=query)
            | Q(firm__icontains=query)
            | Q(major__icontains=query)
            | Q(title__icontains=query)
            | Q(office_city__icontains=query)
        )

    # --- Sort ---
    sort = request.GET.get("sort", "name")
    if sort not in SORT_OPTIONS:
        sort = "name"
    alumni = alumni.order_by(*SORT_OPTIONS[sort][1])

    context = {
        "alumni": alumni,
        "query": query,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
    }
    return render(request, "core/alumni_list.html", context)


@login_required
def alumni_detail(request, pk):
    """One alumnus's public record."""
    alumnus = get_object_or_404(Alumni, pk=pk)

    # Hidden (flagged) entries are invisible to regular students. Admins can
    # still open them to review and, if appropriate, restore them.
    if alumnus.status == Alumni.Status.FLAGGED and not request.user.is_admin:
        raise Http404

    # Has the current student already confirmed this entry? Controls the button
    # label ("Confirm" vs "Re-confirm").
    already_verified = AlumniVerification.objects.filter(
        alumni=alumnus, user=request.user
    ).exists()
    return render(request, "core/alumni_detail.html", {
        "alumnus": alumnus,
        "already_verified": already_verified,
        "flag_form": FlagForm(),  # inline "report" form on the detail page
    })


@login_required
@require_POST  # state-changing action -> POST only (button is a small form)
def alumni_verify(request, pk):
    """
    Record that the current student confirms this entry is still accurate.

    - First time: creates an AlumniVerification row.
    - Re-confirming: refreshes that row's timestamp (no second row).
    Then we recompute the denormalized `verified_count` from the rows and set
    `last_verified` to today.
    """
    alumnus = get_object_or_404(Alumni, pk=pk)

    _, created = AlumniVerification.objects.update_or_create(
        alumni=alumnus,
        user=request.user,
        defaults={"verified_at": timezone.now()},
    )

    # verified_count is derived: it's simply how many distinct students confirmed.
    alumnus.verified_count = alumnus.verifications.count()
    alumnus.last_verified = timezone.localdate()
    alumnus.save(update_fields=["verified_count", "last_verified"])

    if created:
        messages.success(request, "Thanks — marked as still accurate.")
    else:
        messages.success(request, "Thanks — re-confirmed. Freshness date updated.")
    return redirect("alumni_detail", pk=pk)


# --- Suggested edits (Phase 3) ----------------------------------------------

@login_required
def alumni_suggest_edit(request, pk):
    """
    Let a student propose corrections to an alumnus.

    We pre-fill the form with the current values. On submit we compare what they
    entered to the current record, keep only the fields that actually changed,
    and store those as a PENDING AlumniEdit. The shared record is NOT touched
    here — the maintainer applies changes later from the review queue.
    """
    alumnus = get_object_or_404(Alumni, pk=pk)

    if request.method == "POST":
        # Snapshot the current values BEFORE validating. (A ModelForm bound to an
        # instance overwrites that instance's attributes in memory during
        # validation, which would make our old-vs-new diff see no changes. So we
        # don't pass instance here, and we read originals straight off `alumnus`.)
        original = {f: getattr(alumnus, f) for f in SuggestEditForm.Meta.fields}

        form = SuggestEditForm(request.POST)
        if form.is_valid():
            # Build a dict of only the fields the student actually changed.
            changes = {}
            for field in SuggestEditForm.Meta.fields:
                new_value = form.cleaned_data[field]
                if new_value != original[field]:
                    changes[field] = new_value

            if not changes:
                messages.info(request, "No changes detected — nothing was submitted.")
                return redirect("alumni_detail", pk=pk)

            AlumniEdit.objects.create(
                alumni=alumnus,
                user=request.user,
                proposed_changes=changes,
                status=AlumniEdit.Status.PENDING,
            )
            messages.success(
                request,
                "Thanks! Your suggested edit was submitted for review.",
            )
            return redirect("alumni_detail", pk=pk)
    else:
        form = SuggestEditForm(instance=alumnus)

    return render(request, "core/suggest_edit.html", {"form": form, "alumnus": alumnus})


# --- Admin review queue (Phase 3) -------------------------------------------

def describe_changes(edit):
    """
    Turn an edit's {field: new_value} dict into a readable list of
    {label, old, new} rows for the review page.
    """
    rows = []
    for field, new_value in edit.proposed_changes.items():
        try:
            label = Alumni._meta.get_field(field).verbose_name
        except Exception:
            label = field
        rows.append({
            "label": label,
            "old": getattr(edit.alumni, field, ""),
            "new": new_value,
        })
    return rows


@login_required
@require_POST
def alumni_report(request, pk):
    """Let any student report an entry. Creates an (unresolved) AlumniFlag."""
    alumnus = get_object_or_404(Alumni, pk=pk)
    form = FlagForm(request.POST)
    if form.is_valid():
        flag = form.save(commit=False)
        flag.alumni = alumnus
        flag.user = request.user
        flag.save()
        messages.success(request, "Thanks — your report was sent to the maintainer.")
    else:
        messages.error(request, "Please add a short reason for the report.")
    return redirect("alumni_detail", pk=pk)


@admin_required
def review_queue(request):
    """Maintainer-only page: pending suggested edits AND open flags."""
    pending_edits = (
        AlumniEdit.objects.filter(status=AlumniEdit.Status.PENDING)
        .select_related("alumni", "user")
    )
    edits = [{"edit": e, "changes": describe_changes(e)} for e in pending_edits]

    open_flags = (
        AlumniFlag.objects.filter(resolved=False)
        .select_related("alumni", "user")
    )

    # Entries currently hidden (status=flagged). Listed here so you always have a
    # way back to restore them — otherwise, once a flag is resolved, a hidden
    # entry would have no link anywhere.
    hidden = Alumni.objects.filter(status=Alumni.Status.FLAGGED)

    return render(request, "core/review_queue.html", {
        "edits": edits,
        "flags": open_flags,
        "hidden": hidden,
    })


@admin_required
@require_POST
def review_flag(request, flag_id, action):
    """
    Resolve a flag.

    - hide:    hide the entry from the directory (status -> flagged) and resolve.
    - dismiss: leave the entry as-is, just mark the flag resolved.
    """
    flag = get_object_or_404(AlumniFlag, pk=flag_id)

    if flag.resolved:
        messages.info(request, "That flag was already resolved.")
        return redirect("review_queue")

    if action == "hide":
        flag.alumni.status = Alumni.Status.FLAGGED
        flag.alumni.save(update_fields=["status"])
        flag.resolved = True
        flag.save(update_fields=["resolved"])
        messages.success(request, f"Hid {flag.alumni.name} from the directory.")
    elif action == "dismiss":
        flag.resolved = True
        flag.save(update_fields=["resolved"])
        messages.success(request, "Flag dismissed; entry left as-is.")
    else:
        raise PermissionDenied  # unknown action

    return redirect("review_queue")


@admin_required
@require_POST
def alumni_restore(request, pk):
    """Un-hide a flagged entry by setting its status back to approved."""
    alumnus = get_object_or_404(Alumni, pk=pk)
    alumnus.status = Alumni.Status.APPROVED
    alumnus.save(update_fields=["status"])
    messages.success(request, f"Restored {alumnus.name} to the directory.")
    return redirect("alumni_detail", pk=pk)


@admin_required
@require_POST
def alumni_delete(request, pk):
    """Permanently delete an entry (maintainer only). Unlike 'hide', this can't be undone."""
    alumnus = get_object_or_404(Alumni, pk=pk)
    name = alumnus.name
    alumnus.delete()
    messages.success(request, f"Permanently deleted {name}.")
    return redirect("alumni_list")


# --- Contributions / profile (Phase 5) --------------------------------------

@login_required
def profile(request):
    """
    The student's own profile, showing how much they've contributed to the map:
    entries added, verifications made, and suggested edits that were accepted.
    """
    user = request.user

    entries_added = Alumni.objects.filter(added_by=user).count()
    verifications_made = AlumniVerification.objects.filter(user=user).count()
    accepted_edits = AlumniEdit.objects.filter(
        user=user, status=AlumniEdit.Status.ACCEPTED
    ).count()

    context = {
        "entries_added": entries_added,
        "verifications_made": verifications_made,
        "accepted_edits": accepted_edits,
        # A single headline number rewarding overall participation.
        "total_contributions": entries_added + verifications_made + accepted_edits,
    }
    return render(request, "core/profile.html", context)


@admin_required
@require_POST
def review_edit(request, edit_id, action):
    """
    Accept or reject a suggested edit.

    - accept: apply the proposed changes to the alumnus, mark the edit accepted.
    - reject: just mark the edit rejected (record left unchanged).
    """
    edit = get_object_or_404(AlumniEdit, pk=edit_id)

    if edit.status != AlumniEdit.Status.PENDING:
        messages.info(request, "That edit was already resolved.")
        return redirect("review_queue")

    if action == "accept":
        # Apply each proposed field value to the shared record.
        for field, value in edit.proposed_changes.items():
            setattr(edit.alumni, field, value)
        edit.alumni.save()
        edit.status = AlumniEdit.Status.ACCEPTED
        edit.save(update_fields=["status"])
        messages.success(request, f"Applied the edit to {edit.alumni.name}.")
    elif action == "reject":
        edit.status = AlumniEdit.Status.REJECTED
        edit.save(update_fields=["status"])
        messages.success(request, "Edit rejected.")
    else:
        raise PermissionDenied  # unknown action

    return redirect("review_queue")


@login_required
def alumni_add(request):
    """
    Add an alumnus to the shared directory, with a dedup check.

    Flow:
      1. Student fills the form and submits.
      2. We look for possible duplicates. If we find any (and they haven't
         already confirmed "this is a new person"), we DON'T save — instead we
         show the matches and ask "Is this the same person?" so they can open
         and verify the existing entry rather than duplicating it.
      3. If there are no matches, or they click "add as a new person anyway",
         we create the entry with added_by = them and status = approved.
    """
    if request.method == "POST":
        form = AlumniForm(request.POST)
        # Set when the student has seen the duplicate warning and chosen to
        # create a new entry anyway.
        confirm_new = request.POST.get("confirm_new") == "1"

        if form.is_valid():
            cd = form.cleaned_data
            duplicates = []
            if not confirm_new:
                duplicates = find_possible_duplicates(
                    cd["name"], cd["firm"], cd["linkedin_url"]
                )

            if duplicates:
                # Pause and ask before creating a possible duplicate.
                return render(request, "core/alumni_form.html", {
                    "form": form,
                    "duplicates": duplicates,
                })

            # No duplicates (or user overrode) -> create the entry.
            alumnus = form.save(commit=False)
            alumnus.added_by = request.user
            alumnus.status = Alumni.Status.APPROVED  # live immediately
            alumnus.save()
            messages.success(
                request, f"Added {alumnus.name} to the map. Thanks for contributing!"
            )
            return redirect("alumni_detail", pk=alumnus.pk)
    else:
        form = AlumniForm()

    return render(request, "core/alumni_form.html", {"form": form})
