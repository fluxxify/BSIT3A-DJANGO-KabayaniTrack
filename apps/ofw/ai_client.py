"""Nemotron 3.5 Super (NVIDIA) text LLM client for KabayaniTrack.

All AI features are optional and degrade gracefully when ``NVIDIA_API_KEY`` is
not set.  The client uses the standard library only (no extra dependencies)
and keeps every request under a short timeout so a slow model never blocks an
OFW portal or management request.

Endpoint (OpenAI-compatible chat/completions):

    POST {NVIDIA_API_BASE_URL}/chat/completions
    Authorization: Bearer {NVIDIA_API_KEY}
    Content-Type: application/json

Body:

    {
      "model": "nvidia/nemotron-3.5-super",
      "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
      "temperature": 0.3,
      "max_tokens": 256,
      "stream": false
    }
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_CHAT_URL = f'{settings.NVIDIA_API_BASE_URL.rstrip("/")}/chat/completions'


class NemotronUnavailable(Exception):
    """Raised when the NVIDIA API cannot be reached or returns an error."""


def _headers():
    return {
        'Authorization': f'Bearer {settings.NVIDIA_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def chat(messages, *, temperature=0.3, max_tokens=256):
    """Send a chat-completion request to Nemotron 3.5 Super.

    ``messages`` is a list of ``{'role': 'system'|'user'|'assistant',
    'content': '...'}`` dicts.  Returns the assistant's reply text, or raises
    :class:`NemotronUnavailable` when the key is missing, the network fails,
    or the API returns an error.
    """
    if not settings.NVIDIA_API_KEY:
        raise NemotronUnavailable('NVIDIA_API_KEY is not set.')

    payload = {
        'model': settings.NVIDIA_MODEL,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': False,
    }
    data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(_CHAT_URL, data=data, headers=_headers(), method='POST')

    try:
        with urllib.request.urlopen(request, timeout=settings.NVIDIA_API_TIMEOUT) as response:
            body = json.loads(response.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as exc:
        logger.error('NVIDIA API HTTP %s: %s', exc.code, exc.read().decode('utf-8', 'replace')[:200])
        raise NemotronUnavailable(f'API error {exc.code}.')
    except (urllib.error.URLError, OSError) as exc:
        logger.error('NVIDIA API network error: %s', exc)
        raise NemotronUnavailable('Network error.')
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error('NVIDIA API bad response: %s', exc)
        raise NemotronUnavailable('Bad response.')

    choices = body.get('choices') or []
    if not choices:
        raise NemotronUnavailable('Empty response.')
    return (choices[0].get('message') or {}).get('content', '').strip()
