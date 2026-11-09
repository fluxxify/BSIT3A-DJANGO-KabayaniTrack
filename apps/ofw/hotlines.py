"""Automatic emergency hotlines for an OFW's deployment country.

Country entries are bundled as a JSON fallback so every location has at least
one number even when management has not added an ``EmergencyContact`` yet.
Database records always take priority, which lets staff replace or correct a
number without editing code.
"""

import json
import re
from pathlib import Path

from .locations import canonical_country
from .models import EmergencyContact

_DATA_FILE = Path(__file__).resolve().parent / 'data' / 'country_hotlines.json'
_DATA = json.loads(_DATA_FILE.read_text(encoding='utf-8'))
COUNTRY_HOTLINES = _DATA['countries']
PHILIPPINE_HOTLINES = _DATA['philippines']

_TYPE_LABELS = dict(EmergencyContact.ContactType.choices)


class StaticHotline:
    """A read-only hotline row that behaves like an ``EmergencyContact``.

    The portal templates were written against model instances.  This small
    adapter supplies the same fields/properties without creating hundreds of
    database rows for numbers that are only used as a fallback.
    """

    automatic = True
    is_personal = False

    def __init__(
        self,
        *,
        name,
        contact_type,
        phone,
        country='',
        city='',
        email='',
        website='',
        address='',
        notes='',
    ):
        self.name = name
        self.contact_type = contact_type
        self.phone = phone
        self.country = country
        self.city = city
        self.email = email
        self.website = website
        self.address = address
        self.notes = notes

    def __str__(self):
        return f'{self.name} ({self.get_contact_type_display()})'

    def get_contact_type_display(self):
        return _TYPE_LABELS.get(
            self.contact_type, self.contact_type.replace('_', ' ').title()
        )

    @property
    def dial_number(self):
        return re.sub(r'[^\d+]', '', self.phone or '')

    @property
    def whatsapp_url(self):
        # Emergency service numbers are not WhatsApp/Viber contacts.
        return ''

    @property
    def viber_url(self):
        return ''

    def website_url(self):
        return self.website or ''


def _entries(rows, country):
    return [
        StaticHotline(country=country, **row)
        for row in rows
    ]


def automatic_local_hotlines(location_country):
    """Return bundled emergency rows for ``location_country``.

    The Philippines is handled by the national-hotline list instead, so it is
    not repeated in the local section.
    """
    country = canonical_country(location_country)
    if not country or country == 'Philippines':
        return []
    return _entries(COUNTRY_HOTLINES.get(country, []), country)


def philippine_national_hotlines():
    """Return the always-visible Philippine national hotlines."""
    return _entries(PHILIPPINE_HOTLINES, 'Philippines')


def _dedupe_hotlines(contacts):
    """Keep the first row for each dialable number, preserving priority."""
    seen = set()
    result = []
    for contact in contacts:
        key = contact.dial_number or (contact.phone or '').strip()
        if key and key in seen:
            continue
        seen.add(key)
        result.append(contact)
    return result


def hotlines_for_country(location_country):
    """Public hotlines for an OFW's deployment country plus PH national ones.

    Database entries are authoritative and come first.  Bundled country data
    fills in local emergency numbers when management has not added any, so an
    OFW always has at least one local number plus the Philippine hotlines.
    Returns a ``(local_hotlines, national_hotlines)`` tuple.
    """
    country = canonical_country(location_country)
    public_contacts = list(
        EmergencyContact.objects
        .filter(contact_type__in=EmergencyContact.PUBLIC_TYPES)
        .order_by('country', 'contact_type', 'name')
    )

    db_local = []
    db_national = []
    for contact in public_contacts:
        contact_country = canonical_country(contact.country)
        if country and country != 'Philippines' and contact_country == country:
            db_local.append(contact)
        elif contact_country == 'Philippines':
            db_national.append(contact)

    local = _dedupe_hotlines(
        db_local + automatic_local_hotlines(country)
    )
    national = _dedupe_hotlines(
        db_national + philippine_national_hotlines()
    )
    return local, national
