"""Range-aware media file serving.

Django's built-in ``static()`` helper serves media with a plain
``FileResponse``.  It answers every request with ``200 OK`` and never
honours the ``Range`` header, which is exactly what Safari on iOS (and
Safari on macOS) refuses to play: the browser asks for a byte range, gets a
full-body response, and the video never starts.  This view implements the
subset of RFC 7233 that browsers need so uploaded proof videos play
inline on phones.
"""

import mimetypes
import os
import re

from django.conf import settings
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.utils.http import http_date

RANGE_HEADER_RE = re.compile(r'^bytes=(?P<start>\d*)-(?P<end>\d*)$')
FILE_CHUNK_SIZE = 64 * 1024


def _safe_media_path(path):
    """Resolve ``path`` inside ``MEDIA_ROOT`` or raise ``Http404``."""
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    candidate = os.path.abspath(os.path.join(media_root, path.lstrip('/\\')))

    if os.path.commonpath([media_root, candidate]) != media_root:
        raise Http404('Media path is outside MEDIA_ROOT')

    if not os.path.isfile(candidate):
        raise Http404('Media file not found')

    return candidate


def _content_type(fullpath):
    guessed, _ = mimetypes.guess_type(fullpath)
    return guessed or 'application/octet-stream'


def _file_stream(fileobj, length):
    """Yield up to ``length`` bytes from ``fileobj`` in chunks."""
    try:
        remaining = length
        while remaining > 0:
            chunk = fileobj.read(min(FILE_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        fileobj.close()


def serve_media(request, path):
    """Serve a file from ``MEDIA_ROOT`` with HTTP range support."""
    fullpath = _safe_media_path(path)
    stat = os.stat(fullpath)
    file_size = stat.st_size
    content_type = _content_type(fullpath)

    range_header = request.META.get('HTTP_RANGE', '').strip()
    match = RANGE_HEADER_RE.match(range_header) if range_header else None

    start, end = 0, file_size - 1
    partial = False

    if match:
        raw_start, raw_end = match.group('start'), match.group('end')

        if raw_start == '' and raw_end == '':
            match = None
        elif raw_start == '':
            # Suffix range: the last N bytes.
            start = max(file_size - int(raw_end), 0)
            partial = True
        else:
            start = int(raw_start)
            if raw_end:
                end = int(raw_end)
            partial = True

    if partial:
        if start >= file_size:
            response = HttpResponse(status=416)
            response['Content-Range'] = 'bytes */%d' % file_size
            response['Accept-Ranges'] = 'bytes'
            return response
        end = min(end, file_size - 1)

    length = end - start + 1
    filename = os.path.basename(fullpath)

    common_headers = {
        'Accept-Ranges': 'bytes',
        'Last-Modified': http_date(stat.st_mtime),
        'Content-Disposition': 'inline; filename="%s"' % filename,
    }

    if request.method == 'HEAD':
        response = HttpResponse(content_type=content_type, status=206 if partial else 200)
        response['Content-Length'] = length
        if partial:
            response['Content-Range'] = 'bytes %d-%d/%d' % (start, end, file_size)
        for key, value in common_headers.items():
            response[key] = value
        return response

    fileobj = open(fullpath, 'rb')
    if start:
        fileobj.seek(start)

    response = StreamingHttpResponse(
        _file_stream(fileobj, length),
        content_type=content_type,
        status=206 if partial else 200,
    )
    response['Content-Length'] = length
    if partial:
        response['Content-Range'] = 'bytes %d-%d/%d' % (start, end, file_size)
    for key, value in common_headers.items():
        response[key] = value

    return response
