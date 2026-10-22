"""Bounding and redaction for anything recorded as evidence.

Website content is untrusted. Evidence keeps only short, plain-text excerpts and URLs with
credentials and secret-looking query parameters removed. Cookies, headers, storage, and page
source are never collected in the first place.
"""

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_MESSAGE_CHARS = 1_000
MAX_STACK_CHARS = 4_000
MAX_URL_CHARS = 2_048
MAX_EVIDENCE_BYTES = 16_384

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET_PARAM = re.compile(
    r"(token|secret|passw|pwd|auth|session|sid|key|signature|sig|code|credential|jwt|bearer)",
    re.IGNORECASE,
)
# Values that look like bearer tokens or JWTs inside free text (console messages, stacks).
_INLINE_SECRET = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"
)


def clean_text(value: object, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = _CONTROL.sub("", str(value))
    text = _INLINE_SECRET.sub(lambda match: (match.group(1) or "") + "[redacted]", text)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def redact_url(url: str | None) -> str | None:
    if url is None:
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "[invalid URL]"
    if parts.scheme not in ("http", "https"):
        # data:, blob: and similar URLs can embed whole documents; keep only the scheme.
        return f"{parts.scheme}:[omitted]" if parts.scheme else clean_text(url, 200)
    netloc = parts.hostname or ""
    if port:
        netloc = f"{netloc}:{port}"
    query = urlencode(
        [
            (name, "[redacted]" if _SECRET_PARAM.search(name) else value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return clean_text(urlunsplit((parts.scheme, netloc, parts.path, query, "")), MAX_URL_CHARS)


def bounded_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return evidence that serializes to at most MAX_EVIDENCE_BYTES."""
    encoded = json.dumps(evidence, default=str)
    if len(encoded.encode()) <= MAX_EVIDENCE_BYTES:
        return evidence
    trimmed: dict[str, Any] = {}
    for name, value in evidence.items():
        if isinstance(value, list):
            value = value[:20]
        elif isinstance(value, str):
            value = clean_text(value, 1_000)
        trimmed[name] = value
    trimmed["truncated"] = True
    if len(json.dumps(trimmed, default=str).encode()) > MAX_EVIDENCE_BYTES:
        return {"truncated": True, "note": "Evidence exceeded the size limit and was dropped."}
    return trimmed
