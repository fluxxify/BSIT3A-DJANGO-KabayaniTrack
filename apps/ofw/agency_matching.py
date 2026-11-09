"""Match legacy free-text agency names to real :class:`Agency` rows.

Older OFW profiles can store the agency only as free text (for example
``"OWWA"``, ``"OWWA Region 6"`` or the full agency name).  Agency dashboards
scope records through the ``agency_org`` foreign key, so those profiles stay
invisible until the text is matched back to an agency.
"""

import re

from apps.users.models import Agency

# Words that should not contribute to an agency acronym.
STOPWORDS = {
    'and', 'co', 'company', 'corp', 'corporation', 'for', 'inc',
    'incorporated', 'limited', 'ltd', 'of', 'the',
}


def normalise_agency_text(value):
    """Lowercase and remove punctuation so comparisons are forgiving."""
    value = (value or '').strip().casefold()
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return ' '.join(value.split())


def agency_acronym(name):
    """Return the initials of the meaningful words in an agency name.

    ``Overseas Workers Welfare Administration`` -> ``OWWA``.
    """
    words = [
        word for word in normalise_agency_text(name).split()
        if word and word not in STOPWORDS
    ]
    return ''.join(word[0] for word in words)


def agency_aliases(agency):
    """Every normalised text form that should identify one agency."""
    return {
        value for value in (
            normalise_agency_text(agency.name),
            normalise_agency_text(agency.slug),
            normalise_agency_text(agency_acronym(agency.name)),
        ) if value
    }


def match_agency(value, agencies=None):
    """Return the agency matching ``value``, or ``None``.

    Matching is intentionally conservative:

    1. exact match against the full name, slug or acronym;
    2. a saved text such as ``"OWWA Region 6"`` matches the acronym token.

    Acronyms shorter than three letters are ignored during token matching to
    avoid accidental matches.
    """
    key = normalise_agency_text(value)
    if not key:
        return None

    if agencies is None:
        agencies = Agency.objects.filter(is_active=True)
    agencies = list(agencies)

    for agency in agencies:
        if key in agency_aliases(agency):
            return agency

    tokens = set(key.split())
    for agency in agencies:
        acronym = normalise_agency_text(agency_acronym(agency.name))
        if len(acronym) >= 3 and acronym in tokens:
            return agency

    return None


def link_profiles_to_agencies(*, dry_run=False):
    """Link unassigned OFW profiles using their saved agency text.

    Returns the list of profiles matched (or that would match when
    ``dry_run`` is true).
    """
    from .models import OFWProfile

    agencies = list(Agency.objects.filter(is_active=True))
    matched = []
    profiles = (
        OFWProfile.objects
        .filter(agency_org__isnull=True)
        .exclude(agency='')
        .select_related('user')
        .order_by('id')
    )

    for profile in profiles:
        agency = match_agency(profile.agency, agencies)
        if agency is None:
            continue
        profile.agency_org = agency
        profile.agency = agency.name
        if not dry_run:
            profile.save(update_fields=['agency_org', 'agency'])
        matched.append(profile)

    return matched
