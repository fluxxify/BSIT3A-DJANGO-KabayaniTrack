"""Security middleware: Content-Security-Policy and other hardening headers."""

from django.conf import settings


class SecurityHeadersMiddleware:
    """Add security headers to every response.

    CSP is deliberately conservative: it allows the project's own static
    assets, FontAwesome, Tabler CDN resources, and inline styles/scripts
    that the Tabler theme requires.  Leaflet is self-hosted under
    static/libs/leaflet, and map tiles are images (allowed by img-src https:).
    Adjust as needed when new external providers are added.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not settings.DEBUG:
            # Content Security Policy
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' "
                "https://cdnjs.cloudflare.com https://rsms.me; "
                "style-src 'self' 'unsafe-inline' "
                "https://cdnjs.cloudflare.com https://rsms.me; "
                "img-src 'self' data: blob: https:; "
                "font-src 'self' https://cdnjs.cloudflare.com https://rsms.me; "
                "connect-src 'self'; "
                "media-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
            response['Content-Security-Policy'] = csp

        # Referrer policy already handled by SECURE_REFERRER_POLICY middleware,
        # but reinforce it here for older browsers.
        response.setdefault(
            'Referrer-Policy', 'strict-origin-when-cross-origin'
        )
        response.setdefault('X-Content-Type-Options', 'nosniff')
        response.setdefault('X-Frame-Options', 'DENY')

        return response
