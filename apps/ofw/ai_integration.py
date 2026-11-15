"""AI integration for KabayaniTrack using Nemotron 3.5 Super.

Features (all optional, degrade gracefully when ``NVIDIA_API_KEY`` is unset):

* ``categorize_concern(description)`` - suggests a Concern category + severity
  from the OFW's free-text description.  Management can accept or override.
* ``triage_welfare(notes, current_status, condition)`` - suggests a welfare
  status change from check-in / assessment notes.
* ``ofw_chatbot(question, context)`` - answers OFW questions about their case,
  hotlines, safe places, and how to use the portal.

Each function returns a plain dict and never raises: on any failure it returns
``{'ok': False, 'error': '...'}`` so callers can fall back to manual entry.
"""

import json
import logging

from .ai_client import NemotronUnavailable, chat

logger = logging.getLogger(__name__)

_CONCERN_CATEGORIES = [
    'salary', 'contract', 'health', 'abuse', 'documents',
    'illegal_recruitment', 'work_environment', 'other',
]
_CONCERN_SEVERITIES = ['low', 'medium', 'high', 'critical']
_WELFARE_STATUSES = ['active', 'needs_support', 'distressed', 'repatriated', 'missing']


def _parse_json_response(text, expected_keys):
    """Best-effort JSON parse of an LLM reply; falls back to key scanning."""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    # Scan for known values in the raw text.
    found = {}
    for key in expected_keys:
        for value in _CONCERN_CATEGORIES + _CONCERN_SEVERITIES + _WELFARE_STATUSES:
            if value in text.lower():
                found.setdefault(key, value)
    return found


def categorize_concern(description):
    """Suggest ``(category, severity)`` from a concern description.

    Returns ``{'ok': True, 'category': ..., 'severity': ..., 'reasoning': ...}``
    or ``{'ok': False, 'error': ...}`` on failure.  Staff must review and may
    override the suggestion before saving.
    """
    if not description or not description.strip():
        return {'ok': False, 'error': 'No description to categorize.'}

    system = (
        'You are a careful case officer for an OFW (Overseas Filipino Worker) '
        'welfare system.  Read the concern description and return ONLY a JSON '
        'object with three keys: ``category``, ``severity``, ``reasoning``.  '
        f'Valid categories: {", ".join(_CONCERN_CATEGORIES)}.  '
        f'Valid severities: {", ".join(_CONCERN_SEVERITIES)}.  '
        '``reasoning`` is one short sentence explaining why.  No markdown, no '
        'extra text.'
    )
    user = f'Description: {description.strip()}'

    try:
        reply = chat([{'role': 'system', 'content': system},
                      {'role': 'user', 'content': user}], temperature=0.2, max_tokens=150)
    except NemotronUnavailable as exc:
        return {'ok': False, 'error': str(exc)}

    data = _parse_json_response(reply, ('category', 'severity'))
    category = data.get('category', 'other')
    severity = data.get('severity', 'medium')
    if category not in _CONCERN_CATEGORIES:
        category = 'other'
    if severity not in _CONCERN_SEVERITIES:
        severity = 'medium'
    return {
        'ok': True,
        'category': category,
        'severity': severity,
        'reasoning': data.get('reasoning', 'Suggested by AI.'),
    }


def triage_welfare(notes, current_status, condition=None):
    """Suggest a welfare status from notes / check-in condition.

    Returns ``{'ok': True, 'status': ..., 'reasoning': ...}`` or
    ``{'ok': False, 'error': ...}``.  The suggestion never lowers urgency:
    Distressed stays Distressed unless a staff member explicitly lowers it.
    """
    if not notes and not condition:
        return {'ok': False, 'error': 'No notes or condition to triage.'}

    system = (
        'You are a welfare triage officer for an OFW monitoring system.  '
        f'Current status: {current_status}.  Valid statuses: '
        f'{", ".join(_WELFARE_STATUSES)}.  Return ONLY a JSON object with '
        'keys ``status`` and ``reasoning``.  The suggested status must never '
        'be lower urgency than the current status (active < needs_support '
        '< distressed; repatriated and missing are separate flags).  '
        '``reasoning`` is one short sentence.  No markdown, no extra text.'
    )
    user = f'Notes: {notes or ""}\nCondition: {condition or "n/a"}'

    try:
        reply = chat([{'role': 'system', 'content': system},
                      {'role': 'user', 'content': user}], temperature=0.2, max_tokens=150)
    except NemotronUnavailable as exc:
        return {'ok': False, 'error': str(exc)}

    data = _parse_json_response(reply, ('status',))
    status = data.get('status', current_status)
    if status not in _WELFARE_STATUSES:
        status = current_status
    return {
        'ok': True,
        'status': status,
        'reasoning': data.get('reasoning', 'Suggested by AI.'),
    }


def ofw_chatbot(question, context=None):
    """Answer an OFW's question about their case, hotlines, or the portal.

    ``context`` is an optional dict with keys like ``country``, ``city``,
    ``welfare_status``, ``open_concerns``.  Returns
    ``{'ok': True, 'answer': ...}`` or ``{'ok': False, 'error': ...}``.
    """
    if not question or not question.strip():
        return {'ok': False, 'error': 'No question provided.'}

    ctx = context or {}
    context_lines = [
        f'Country of deployment: {ctx.get("country", "not set")}',
        f'City abroad: {ctx.get("city", "not set")}',
        f'Welfare status: {ctx.get("welfare_status", "not set")}',
        f'Open concerns: {ctx.get("open_concerns", 0)}',
    ]
    system = (
        'You are a helpful assistant for KabayaniTrack, an OFW monitoring and '
        'support portal.  Answer the OFW\'s question in plain English, in the '
        'same language they used.  Be concise, reassuring, and practical.  '
        'If you cannot answer from the context, say so and suggest they '
        'contact their agency or use the emergency SOS button.  Never invent '
        'phone numbers, case statuses, or personal data.  No markdown.'
    )
    user = (
        'Context:\n' + '\n'.join(context_lines) +
        f'\n\nQuestion: {question.strip()}'
    )

    try:
        answer = chat([{'role': 'system', 'content': system},
                       {'role': 'user', 'content': user}],
                      temperature=0.4, max_tokens=300)
    except NemotronUnavailable as exc:
        return {'ok': False, 'error': str(exc)}

    if not answer:
        return {'ok': False, 'error': 'Empty response from assistant.'}
    return {'ok': True, 'answer': answer}
