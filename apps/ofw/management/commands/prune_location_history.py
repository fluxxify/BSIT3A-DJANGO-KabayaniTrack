from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.ofw.models import LocationTracker


class Command(BaseCommand):
    help = 'Preview or remove location pings older than a retention period.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument(
            '--execute', action='store_true',
            help='Delete matching pings. Without this flag, only show the count.',
        )

    def handle(self, *args, **options):
        days = options['days']
        if days < 1:
            self.stderr.write(self.style.ERROR('--days must be at least 1.'))
            return

        cutoff = timezone.now() - timedelta(days=days)
        old_pings = LocationTracker.objects.filter(recorded_at__lt=cutoff)
        count = old_pings.count()
        if options['execute']:
            old_pings.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} location pings older than {days} days.'
            ))
        else:
            self.stdout.write(
                f'{count} location pings are older than {days} days. '
                'Preview only; add --execute to delete them.'
            )
