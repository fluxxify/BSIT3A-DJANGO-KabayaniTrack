"""TOTP (RFC 6238) helpers for two-factor authentication.

Implemented with the standard library only so KabayaniTrack needs no extra
dependency.  Time-based one-time passwords are 6-digit codes valid for 30
seconds, with a +/-1 step window to tolerate clock drift.
"""

import base64
import hashlib
import hmac
import os
import struct
import time


def generate_secret(length=10):
    """Return a random base32-encoded secret key."""
    return base64.b32encode(os.urandom(length)).decode('ascii').rstrip('=')


def generate_totp(secret, timestep=30, now=None):
    """Generate the current 6-digit TOTP code for ``secret``."""
    now = now or int(time.time())
    key = base64.b32decode(secret + '=' * ((8 - len(secret) % 8) % 8))
    counter = struct.pack('>q', now // timestep)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{truncated % 1000000:06d}'


def verify_totp(secret, code, timestep=30, window=1, now=None):
    """Return True when ``code`` is a valid TOTP for ``secret``.

    ``window`` allows checking adjacent time steps so a clock that is a few
    seconds off still works.
    """
    now = now or int(time.time())
    code = str(code).strip()
    if not code.isdigit() or len(code) != 6:
        return False
    for offset in range(-window, window + 1):
        step = now // timestep + offset
        if generate_totp(secret, timestep, now=step * timestep) == code:
            return True
    return False


def generate_backup_codes(count=8, length=8):
    """Return a list of single-use backup codes."""
    codes = []
    while len(codes) < count:
        code = ''.join(
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[os.urandom(1)[0] % 36]
            for _ in range(length)
        )
        if code not in codes:
            codes.append(code)
    return codes
