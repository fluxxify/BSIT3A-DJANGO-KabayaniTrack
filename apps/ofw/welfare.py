"""Safe automation for the OFW welfare status.

The rules are intentionally conservative: an automatic update may raise the
status, but it never lowers it.  Lowering a welfare status is a judgement call
that a staff member must make through a new assessment.

* The latest welfare assessment sets the profile status.
* A check-in may escalate the status (``Distressed`` -> In Danger, etc.).
* A safe check-in only clears the contactability flag ``Unreachable``.
* Logging in clears ``Unreachable`` because the OFW has just proven they can be
  reached; it never changes an In Danger or Needs Assistance status.
* Every automatic change is written to the audit log so staff can see why the
  status moved.
"""

import json
from datetime import timedelta

from django.utils import timezone

from .models import (
    AuditLog,
    CheckIn,
    OFWProfile,
    WelfareAssessment,
    WelfareStatus,
    WELFARE_STALE_DAYS,
)

# Check-in conditions that may raise the profile status.
_ESCALATION = {
    CheckIn.Condition.NEEDS_ASSISTANCE: WelfareStatus.NEEDS_SUPPORT,
    CheckIn.Condition.DISTRESSED: WelfareStatus.DISTRESSED,
    CheckIn.Condition.UNREACHABLE: WelfareStatus.MISSING,
}

# Higher means more urgent.  Used only to block automatic downgrades.
_RANK = {
    WelfareStatus.ACTIVE: 0,
    WelfareStatus.REPATRIATED: 0,
    WelfareStatus.NEEDS_SUPPORT: 1,
    WelfareStatus.MISSING: 1,
    WelfareStatus.DISTRESSED: 2,
}


def stale_cutoff():
    """Return the oldest timestamp that still counts as a current status."""
    return timezone.now() - timedelta(days=WELFARE_STALE_DAYS)


def set_profile_status(profile, status, *, source, actor=None, note=''):
    """Change the profile status and record who or what changed it.

    Uses ``queryset.update`` so it does not retrigger the profile signals.
    Returns ``True`` when the status actually changed.
    """
    previous = profile.welfare_status
    if previous == status:
        return False

    now = timezone.now()
    OFWProfile.objects.filter(pk=profile.pk).update(
        welfare_status=status,
        welfare_status_updated_at=now,
        updated_at=now,
    )
    profile.welfare_status = status
    profile.welfare_status_updated_at = now

    try:
        AuditLog.objects.create(
            user=actor if getattr(actor, 'is_authenticated', False) else None,
            action=AuditLog.Action.UPDATE,
            model_name=OFWProfile._meta.verbose_name.title(),
            object_id=str(profile.pk),
            object_repr=str(profile)[:255],
            changes=json.dumps(
                {
                    'welfare_status': {'from': previous, 'to': status},
                    'source': source,
                    'note': note,
                },
                default=str,
            ),
        )
    except Exception:
        # Auditing must never break the status update.
        pass
    return True


def _touch_status_clock(profile):
    """Record that the current status was reviewed even if it did not change."""
    now = timezone.now()
    OFWProfile.objects.filter(pk=profile.pk).update(
        welfare_status_updated_at=now,
        updated_at=now,
    )
    profile.welfare_status_updated_at = now


def sync_from_assessment(assessment):
    """Let the latest welfare assessment drive the profile status."""
    latest = (
        WelfareAssessment.objects.filter(ofw_id=assessment.ofw_id)
        .order_by('-assessment_date', '-id')
        .only('pk')
        .first()
    )
    if latest is None or latest.pk != assessment.pk:
        return False
    changed = set_profile_status(
        assessment.ofw,
        assessment.status,
        source='welfare assessment',
        actor=assessment.user,
        note=f'Assessment dated {assessment.assessment_date}',
    )
    if not changed:
        # A fresh assessment confirms the existing status, which resets the
        # "Needs review" clock even though the value did not change.
        _touch_status_clock(assessment.ofw)
    return changed


def sync_from_checkin(checkin):
    """Escalate the profile status from the latest check-in when appropriate."""
    latest = (
        CheckIn.objects.filter(ofw_id=checkin.ofw_id)
        .order_by('-checkin_date', '-id')
        .only('pk')
        .first()
    )
    if latest is None or latest.pk != checkin.pk:
        return False

    profile = checkin.ofw
    current = profile.welfare_status
    condition = checkin.condition

    if condition == CheckIn.Condition.SAFE:
        # Recovery is limited to the contactability flag.  A safe check-in does
        # not clear In Danger or Needs Assistance; staff confirm that.
        if current == WelfareStatus.MISSING:
            return set_profile_status(
                profile,
                WelfareStatus.ACTIVE,
                source='check-in',
                actor=checkin.user,
                note='Safe check-in cleared Unreachable.',
            )
        return False

    target = _ESCALATION.get(condition)
    if target is None:
        return False
    if _RANK.get(target, 0) <= _RANK.get(current, 0):
        return False
    return set_profile_status(
        profile,
        target,
        source='check-in',
        actor=checkin.user,
        note=f'Check-in reported {checkin.get_condition_display()}.',
    )


def clear_unreachable_on_login(user):
    """Logging in proves the OFW can be reached, so clear Unreachable only."""
    profiles = OFWProfile.objects.filter(
        user=user,
        welfare_status=WelfareStatus.MISSING,
    )
    changed = False
    for profile in profiles:
        changed = set_profile_status(
            profile,
            WelfareStatus.ACTIVE,
            source='login',
            actor=user,
            note='OFW logged in; cleared Unreachable.',
        ) or changed
    return changed
