"""Link existing OFW profiles to an Agency using their saved agency text.

Profiles created through an agency registration link
(``/a/<slug>/register/``) already have ``agency_org`` set.  Older
self-registrations stored the agency only in the free-text ``agency`` field, so
agency dashboards cannot see them because those dashboards filter on
``agency_org``.  This data migration matches the saved text back to a real
agency, including common acronyms such as ``OWWA``.
"""

import re

from django.db import migrations


STOPWORDS = {
    'and', 'co', 'company', 'corp', 'corporation', 'for', 'inc',
    'incorporated', 'limited', 'ltd', 'of', 'the',
}


def _normalise(value):
    value = (value or '').strip().casefold()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return ' '.join(value.split())


def _acronym(name):
    words = [
        word for word in _normalise(name).split()
        if word and word not in STOPWORDS
    ]
    return ''.join(word[0] for word in words)


def _match(value, agencies):
    key = _normalise(value)
    if not key:
        return None

    aliases = []
    for agency in agencies:
        aliases.append((agency, {
            _normalise(agency.name),
            _normalise(agency.slug),
            _normalise(_acronym(agency.name)),
        }))

    for agency, forms in aliases:
        if key in forms:
            return agency

    tokens = set(key.split())
    for agency, _forms in aliases:
        acronym = _normalise(_acronym(agency.name))
        if len(acronym) >= 3 and acronym in tokens:
            return agency

    return None


def link_profiles(apps, schema_editor):
    Agency = apps.get_model('users', 'Agency')
    OFWProfile = apps.get_model('kabayan', 'OFWProfile')

    agencies = list(Agency.objects.filter(is_active=True))
    if not agencies:
        return

    profiles = (
        OFWProfile.objects
        .filter(agency_org__isnull=True)
        .exclude(agency='')
    )
    for profile in profiles.iterator():
        agency = _match(profile.agency, agencies)
        if agency is None:
            continue
        profile.agency_org = agency
        profile.agency = agency.name
        profile.save(update_fields=['agency_org', 'agency'])


class Migration(migrations.Migration):

    dependencies = [
        ('kabayan', '0030_audit_log'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(link_profiles, migrations.RunPython.noop),
    ]
