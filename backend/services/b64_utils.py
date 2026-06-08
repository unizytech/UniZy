"""Padding-tolerant base64 decoding for audio chunk data.

Web clients (MediaRecorder and others) occasionally emit base64 audio whose
length is not a multiple of 4 — i.e. the trailing '=' padding was stripped, or a
partial slice was taken. Standard ``base64.b64decode()`` then raises
``binascii.Error("Incorrect padding")``, which previously aborted the entire
recording with a PROCESSING_FAILED webhook.

``b64decode_padded`` restores the missing '=' padding before decoding so a single
malformed chunk no longer kills the session. The cost is O(1) when the input is
already correctly padded (the common case) — only malformed input incurs one
extra string copy of up to 3 trailing pad characters.
"""

import base64


def b64decode_padded(data):
    """base64-decode ``data`` (str or bytes), restoring missing '=' padding first.

    Behaves identically to ``base64.b64decode()`` for well-formed input, and is
    tolerant of input whose length is not a multiple of 4 (the common web-client
    defect). Returns ``b""`` for empty/None input.
    """
    if not data:
        return b""
    pad = b"=" if isinstance(data, (bytes, bytearray)) else "="
    remainder = len(data) % 4
    if remainder:
        data = data + pad * (4 - remainder)
    return base64.b64decode(data)
