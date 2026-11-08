"""Small cache-backed rate limiter for sensitive endpoints.

The project runs on a single PythonAnywhere instance, so Django's default
local-memory cache is enough.  If the app is ever served by several
processes, point ``CACHES`` at a shared backend (Redis/Memcached) and the
counters will be shared automatically.
"""

from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

DEFAULT_MESSAGE = 'Too many requests. Please wait a moment and try again.'


def _client_key(request):
    """Identify the caller: the signed-in user, else the remote address."""
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return f'user:{user.pk}'
    address = request.META.get('REMOTE_ADDR') or 'unknown'
    return f'ip:{address}'


def rate_limit(scope, limit, window, methods=('POST',), as_json=True):
    """Allow at most ``limit`` requests per ``window`` seconds per client.

    Only requests whose method is listed in ``methods`` are counted; other
    methods pass straight through.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return view(request, *args, **kwargs)

            key = f'ratelimit:{scope}:{_client_key(request)}'
            if cache.add(key, 1, window):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    # The counter expired between add() and incr().
                    cache.add(key, 1, window)
                    count = 1

            if count > limit:
                if as_json:
                    response = JsonResponse(
                        {'error': DEFAULT_MESSAGE}, status=429,
                    )
                else:
                    response = HttpResponse(DEFAULT_MESSAGE, status=429)
                response['Retry-After'] = str(window)
                return response

            return view(request, *args, **kwargs)

        wrapper.rate_limited = True
        return wrapper

    return decorator
