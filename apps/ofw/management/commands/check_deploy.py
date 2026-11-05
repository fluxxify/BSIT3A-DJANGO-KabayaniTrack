"""Verify the deployment is healthy before going live.

Usage:
    python manage.py check_deploy

The command checks:

1. All Django migrations are applied (no unapplied migrations).
2. Safe locations have been seeded (``seed_safe_locations``), so the
   nearest-safe-place guide works for every OFW deployment country.
3. Django's built-in deployment checks pass (``check --deploy``).

Exit code is non-zero when any check fails, so it can be used in a deploy
script or CI pipeline.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader
from django.db import connections

from apps.ofw.models import SafeLocation


class Command(BaseCommand):
    help = 'Run pre-deployment health checks (migrations, safe locations, deploy settings).'

    def handle(self, *args, **options):
        failures = []

        # 1. All migrations applied.
        loader = MigrationLoader(connections['default'])
        applied = set(loader.applied_migrations.keys())
        unapplied = set(loader.graph.nodes) - applied
        if unapplied:
            failures.append(
                f'Unapplied migrations: {sorted(unapplied)}. '
                f'Run "python manage.py migrate --noinput".'
            )
        else:
            self.stdout.write(self.style.SUCCESS('All migrations applied.'))

        # 2. Safe locations seeded.
        active_count = SafeLocation.objects.filter(is_active=True).count()
        seeded_countries = (
            SafeLocation.objects.filter(is_active=True)
            .values_list('country', flat=True).distinct().count()
        )
        if active_count == 0:
            failures.append(
                'No active safe locations found. Run "python manage.py seed_safe_locations" '
                'so the nearest-safe-place guide works for every OFW.'
            )
        else:
            self.stdout.write(self.style.SUCCESS(
                f'{active_count} safe location(s) seeded across {seeded_countries} country/countries.'
            ))

        # 3. Django deployment checks (meaningful when DEBUG=False, i.e. on the
        #    live server).  In local development (DEBUG=True) we run the normal
        #    checks instead and note that deploy checks belong on production.
        from django.conf import settings
        if not settings.DEBUG:
            try:
                call_command('check', '--deploy', stderr=self.stderr)
                self.stdout.write(self.style.SUCCESS('Django deployment checks passed.'))
            except CommandError as exc:
                failures.append(f'Django deploy checks failed: {exc}')
        else:
            try:
                call_command('check', stderr=self.stderr)
                self.stdout.write(
                    self.style.WARNING(
                        'Local development (DEBUG=True): ran normal checks only; '
                        'deploy checks run on the live server.'
                    )
                )
            except CommandError as exc:
                failures.append(f'Django checks failed: {exc}')

        if failures:
            self.stderr.write(self.style.ERROR('Deployment health check FAILED:'))
            for failure in failures:
                self.stderr.write(self.style.ERROR(f'  - {failure}'))
            raise CommandError('Deployment is not ready. Fix the issues above before going live.')

        self.stdout.write(self.style.SUCCESS('Deployment health check PASSED. Ready to go live.'))
