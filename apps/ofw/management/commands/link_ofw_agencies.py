"""Link OFW profiles to an agency so agency dashboards can see them.

Agency staff only see OFW profiles whose ``agency_org`` foreign key points to
their own agency. Profiles created through an agency link
(``/a/<slug>/register/``) are linked automatically, but older self-registrations
can store the agency only as free text or leave it blank. Those profiles are
invisible to every agency until they are linked.

Usage::

    python manage.py link_ofw_agencies --dry-run
    python manage.py link_ofw_agencies

    # Fix one specific OFW when the saved text does not match an agency.
    python manage.py link_ofw_agencies --username juan_dela_cruz --agency owwa
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.ofw.models import OFWProfile
from apps.users.models import Agency, AgencyStaff


class Command(BaseCommand):
    help = 'Link OFW profiles without an agency using their saved agency name.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without saving anything.',
        )
        parser.add_argument(
            '--username',
            help=(
                'Show this OFW\'s agency link, or use with --agency to '
                'assign the OFW to that agency.'
            ),
        )
        parser.add_argument(
            '--agency',
            help='Agency slug or name. Use together with --username.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        username = (options['username'] or '').strip()
        agency_ref = (options['agency'] or '').strip()

        if username and not agency_ref:
            self._show_status(username)
            return

        if agency_ref and not username:
            raise CommandError(
                'Use --username and --agency together to assign an OFW. '
                'Run without arguments to link profiles using their saved '
                'agency name.'
            )

        if username and agency_ref:
            self._assign_one(
                username=username, agency_ref=agency_ref, dry_run=dry_run,
            )
            return

        profiles = (
            OFWProfile.objects
            .filter(agency_org__isnull=True)
            .select_related('user')
            .order_by('id')
        )
        linked = 0
        unmatched = []

        for profile in profiles:
            text = (profile.agency or '').strip()
            agency = self._find_agency(text) if text else None
            if agency is None:
                unmatched.append(profile)
                continue
            self._assign(profile, agency, dry_run)
            linked += 1
            self.stdout.write(
                f'  #{profile.pk} {profile.user.username}: '
                f'{text!r} -> {agency.name}'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run: nothing was saved.'))
        self.stdout.write(self.style.SUCCESS(
            f'Linked {linked} OFW profile(s) to an agency.'
        ))

        if not unmatched:
            return

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'{len(unmatched)} profile(s) still have no matching agency:'
        ))
        for profile in unmatched:
            text = (profile.agency or '').strip() or '(blank)'
            self.stdout.write(
                f'  #{profile.pk} {profile.user.username} '
                f'({profile.full_name}) - saved agency: {text}'
            )
        self.stdout.write('')
        self.stdout.write(
            'Assign one manually with:\n'
            '  python manage.py link_ofw_agencies '
            '--username <username> --agency <agency-slug>'
        )

    def _show_status(self, username):
        profiles = OFWProfile.objects.filter(
            user__username__iexact=username
        ).select_related('user', 'agency_org').order_by('id')
        if not profiles.exists():
            raise CommandError(f'No OFW profile found for {username!r}.')

        for profile in profiles:
            self.stdout.write(
                f'#{profile.pk} {profile.user.username} ({profile.full_name})'
            )
            if profile.agency_org_id:
                staff_names = list(
                    AgencyStaff.objects
                    .filter(agency=profile.agency_org)
                    .values_list('user__username', flat=True)
                )
                self.stdout.write(
                    f'  Agency: {profile.agency_org.name} '
                    f'({profile.agency_org.slug})'
                )
                self.stdout.write(
                    '  Visible to agency staff: '
                    + (', '.join(staff_names) or 'no agency staff account yet')
                )
            else:
                self.stdout.write(self.style.ERROR(
                    '  Agency: NOT LINKED - no agency dashboard can see this OFW'
                ))
                self.stdout.write(
                    f'  Saved agency text: {(profile.agency or "").strip() or "(blank)"}'
                )
                matched = self._find_agency(profile.agency)
                suggestion = (
                    f'--agency {matched.slug}' if matched
                    else '--agency <agency-slug>'
                )
                self.stdout.write(
                    '  Fix: python manage.py link_ofw_agencies '
                    f'--username {profile.user.username} {suggestion}'
                )

    def _assign_one(self, *, username, agency_ref, dry_run):
        if not username or not agency_ref:
            raise CommandError(
                'Use --username and --agency together for a single assignment.'
            )

        profiles = OFWProfile.objects.filter(
            user__username__iexact=username
        ).select_related('user')
        if not profiles.exists():
            raise CommandError(f'No OFW profile found for {username!r}.')

        agency = self._find_agency(agency_ref)
        if agency is None:
            raise CommandError(
                f'No agency matched {agency_ref!r}. '
                'Use the agency slug (for example: owwa).'
            )

        for profile in profiles:
            self._assign(profile, agency, dry_run)
            self.stdout.write(
                f'  #{profile.pk} {profile.user.username} -> {agency.name}'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run: nothing was saved.'))
        self.stdout.write(self.style.SUCCESS(
            f'Linked {profiles.count()} OFW profile(s) to {agency.name}.'
        ))

    @staticmethod
    def _find_agency(value):
        value = (value or '').strip()
        if not value:
            return None
        return Agency.objects.filter(
            Q(name__iexact=value) | Q(slug__iexact=value),
            is_active=True,
        ).first()

    @staticmethod
    def _assign(profile, agency, dry_run):
        profile.agency_org = agency
        # Keep the legacy free-text field in sync for exports and old screens.
        profile.agency = agency.name
        if not dry_run:
            profile.save(update_fields=['agency_org', 'agency'])
