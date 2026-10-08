"""Bound decoded HTTP response bytes before JSON or HTML parsing."""
import requests

MAX_BYTES = 20 * 1024 * 1024
MAX_FILING_BYTES = 64 * 1024 * 1024


def get_bounded(url, *, max_bytes=None, client=None, **kwargs):
    """Stream through the caller's requests client; always close the response.

    iter_content counts decompressed bytes, so compressed response bombs also
    hit the budget. The returned local Response supports existing text/json APIs.
    """
    limit = MAX_BYTES if max_bytes is None else max_bytes
    if type(limit) is not int or limit <= 0:
        raise ValueError('invalid HTTP byte budget')
    kwargs.setdefault('timeout', (10, 40))
    response = (client or requests).get(url, stream=True, **kwargs)
    try:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > limit:
                raise ValueError('HTTP response exceeds byte budget')
            chunks.append(chunk)
        result = requests.Response()
        result.status_code = response.status_code
        result.headers.update(response.headers)
        result.encoding = response.encoding or 'utf-8'
        result._content = b''.join(chunks)
        result._content_consumed = True
        return result
    finally:
        response.close()
