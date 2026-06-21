"""
Promote one of your users to "admin" so they can open the review queue.

WHAT THIS DOES
  It finds the user with the email you pass in and sets their `is_admin` flag
  to True. That flag is what unlocks the maintainer-only review page (where you
  accept/reject suggested edits and, later, resolve flags).

HOW TO USE IT
  1. Make sure you've signed up an account with your school (.edu) email first.
  2. Run (from the project folder, with the venv active):

         python manage.py make_admin you@school.edu

  3. You'll see a confirmation. Now visit /review/ while logged in as that
     account.

TO UNDO (demote someone)
  Add --remove:

         python manage.py make_admin you@school.edu --remove

Note: this is separate from Django's own /admin/ site (which uses superuser /
is_staff). This flag only controls THIS app's review queue.
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Grant (or remove) review-queue access for a user by email."

    def add_arguments(self, parser):
        # The email of the account to promote. Required.
        parser.add_argument("email", help="The user's email, e.g. you@school.edu")
        # Optional flag to demote instead of promote.
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Remove admin access instead of granting it.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()

        # Find the user. We store the email as the username at signup.
        try:
            user = User.objects.get(username=email)
        except User.DoesNotExist:
            # Clear, friendly error instead of a stack trace.
            raise CommandError(
                f"No account found for '{email}'. "
                f"Sign up with that email first, then run this again."
            )

        if options["remove"]:
            user.is_admin = False
            user.save(update_fields=["is_admin"])
            self.stdout.write(self.style.WARNING(f"Removed admin access from {email}."))
        else:
            user.is_admin = True
            user.save(update_fields=["is_admin"])
            self.stdout.write(self.style.SUCCESS(
                f"Done. {email} can now open the review queue at /review/."
            ))
