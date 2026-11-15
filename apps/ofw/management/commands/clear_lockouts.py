from django.core.management.base import BaseCommand
from apps.core.models import LoginAttempt


class Command(BaseCommand):
    help = "Clear all brute-force login attempt records (unlocks all accounts)."

    def handle(self, *args, **options):
        deleted = LoginAttempt.objects.all().delete()[0]
        self.stdout.write(self.style.SUCCESS(
            f"Deleted {deleted} login attempt record(s). All lockouts cleared."
        ))
