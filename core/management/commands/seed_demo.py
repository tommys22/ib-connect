"""
Seed a few demo alumni so the directory isn't empty while you test.

Run with:  python manage.py seed_demo

Safe to run repeatedly: it won't create duplicates (matches on name+firm).
"""

from django.core.management.base import BaseCommand

from core.models import Alumni

DEMO_ALUMNI = [
    {
        "name": "Jordan Lee", "grad_year": 2019, "major": "Finance",
        "firm": "Goldman Sachs", "firm_tier": "Bulge bracket",
        "group_division": "TMT", "title": "Associate", "office_city": "New York",
        "linkedin_url": "https://www.linkedin.com/in/example-jordan-lee",
        "open_to_chat": True, "source": "Personal network",
    },
    {
        "name": "Priya Nair", "grad_year": 2021, "major": "Economics",
        "firm": "Moelis & Company", "firm_tier": "Boutique",
        "group_division": "Restructuring", "title": "Analyst", "office_city": "Los Angeles",
        "linkedin_url": "https://www.linkedin.com/in/example-priya-nair",
        "open_to_chat": True, "source": "LinkedIn",
    },
    {
        "name": "Marcus Allen", "grad_year": 2017, "major": "Accounting",
        "firm": "JPMorgan", "firm_tier": "Bulge bracket",
        "group_division": "Healthcare", "title": "Vice President", "office_city": "Seattle",
        "linkedin_url": "https://www.linkedin.com/in/example-marcus-allen",
        "open_to_chat": False, "source": "Personal network",
    },
]


class Command(BaseCommand):
    help = "Add a few demo alumni for local testing."

    def handle(self, *args, **options):
        created = 0
        for data in DEMO_ALUMNI:
            # get_or_create avoids duplicate rows if you run this more than once.
            _, was_created = Alumni.objects.get_or_create(
                name=data["name"], firm=data["firm"], defaults=data
            )
            created += 1 if was_created else 0
        self.stdout.write(self.style.SUCCESS(f"Done. Created {created} new alumni."))
