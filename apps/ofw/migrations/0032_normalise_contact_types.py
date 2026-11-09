"""Give legacy emergency contacts a real type.

Older rows can have a blank ``contact_type`` (for example contacts created by
the OFW portal before it started setting the type explicitly).  The dashboard
already guesses "Family" for owned rows and "Other" for staff-only rows, but
the guess is not stored, so the edit form shows an empty dropdown and the
portal filters see an unknown value.  Normalise the data once so the list,
badges and portal queries always agree.
"""

from django.db import migrations
from django.db.models import Q


def normalise_contact_types(apps, schema_editor):
    EmergencyContact = apps.get_model('kabayan', 'EmergencyContact')
    blank = Q(contact_type='') | Q(contact_type__isnull=True)

    (
        EmergencyContact.objects
        .filter(blank, user__isnull=False)
        .update(contact_type='family')
    )
    (
        EmergencyContact.objects
        .filter(blank)
        .update(contact_type='other')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('kabayan', '0031_link_ofw_agencies'),
    ]

    operations = [
        migrations.RunPython(
            normalise_contact_types,
            migrations.RunPython.noop,
        ),
    ]
