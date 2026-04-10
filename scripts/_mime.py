"""MIME tree walking, part classification, and inline image detection.

Pure functions — no subprocess, no file I/O.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_INLINE_FILENAME_RE = re.compile(r"^image\d+\.(jpg|png|gif)$", re.IGNORECASE)
_SIZE_WARN_BYTES = 25 * 1024 * 1024  # 25 MB


@dataclass
class PartInfo:
    """Represents a single MIME part that has an attachmentId."""

    filename: str
    mime_type: str
    size: int
    attachment_id: str
    disposition: str  # "attachment" or "inline"
    has_content_id: bool
    headers: dict[str, str]  # header name -> value


def _headers_to_dict(headers_list: list[dict[str, str]]) -> dict[str, str]:
    """Convert Gmail's [{name, value}, ...] header list to a dict."""
    return {h["name"]: h["value"] for h in headers_list}


def _parse_disposition(headers: dict[str, str]) -> str:
    """Extract disposition type from Content-Disposition header value."""
    raw = headers.get("Content-Disposition", "")
    if raw.lower().startswith("attachment"):
        return "attachment"
    if raw.lower().startswith("inline"):
        return "inline"
    return "attachment"  # default


def walk_parts(payload: dict) -> list[PartInfo]:
    """Recursively walk MIME tree, collecting parts that have attachmentId."""
    result: list[PartInfo] = []
    _walk_recursive(payload, result)
    return result


def _walk_recursive(node: dict, acc: list[PartInfo]) -> None:
    """Recurse into MIME tree nodes."""
    parts = node.get("parts")
    if parts:
        for part in parts:
            _walk_recursive(part, acc)
        return

    # Leaf node — check for attachmentId
    body = node.get("body", {})
    attachment_id = body.get("attachmentId")
    if not attachment_id:
        return

    raw_headers = node.get("headers", [])
    headers = _headers_to_dict(raw_headers)
    disposition = _parse_disposition(headers)
    has_content_id = "Content-ID" in headers

    acc.append(
        PartInfo(
            filename=node.get("filename", ""),
            mime_type=node.get("mimeType", "application/octet-stream"),
            size=body.get("size", 0),
            attachment_id=attachment_id,
            disposition=disposition,
            has_content_id=has_content_id,
            headers=headers,
        )
    )


def classify_part(part: PartInfo) -> str:
    """Classify as 'attachment', 'inline_image', or 'skip'.

    Heuristics applied in order:
    1. Content-Disposition: attachment -> attachment
    2. Content-Disposition: inline + Content-ID -> inline_image
    3. Filename matches image\\d+\\.(jpg|png|gif) -> inline_image (signature)
    4. Image < 50KB with inline disposition -> inline_image (signature)
    5. Otherwise -> attachment
    """
    # Rule 1: explicit attachment disposition
    if part.disposition == "attachment":
        return "attachment"

    # Rule 2: inline + Content-ID
    if part.disposition == "inline" and part.has_content_id:
        return "inline_image"

    # Rule 3: filename pattern for signature images
    if _INLINE_FILENAME_RE.match(part.filename):
        return "inline_image"

    # Rule 4: small inline image (< 50KB)
    if (
        part.mime_type.startswith("image/")
        and part.size < 50_000
        and part.disposition == "inline"
    ):
        return "inline_image"

    # Default: treat as real attachment
    return "attachment"


def _expand_braces(pattern: str) -> list[str]:
    """Expand a single brace group in a glob pattern.

    e.g. '*.{pdf,xlsx}' -> ['*.pdf', '*.xlsx']
    Only handles one level of braces (no nesting).
    """
    m = re.search(r"\{([^}]+)\}", pattern)
    if not m:
        return [pattern]
    prefix = pattern[: m.start()]
    suffix = pattern[m.end() :]
    alternatives = m.group(1).split(",")
    return [f"{prefix}{alt.strip()}{suffix}" for alt in alternatives]


def filter_parts(
    parts: list[PartInfo],
    pattern: str | None = None,
    include_inline: bool = False,
    max_size_mb: float = 100,
) -> tuple[list[PartInfo], list[dict]]:
    """Filter parts by classification, glob pattern, and size limit.

    Returns (keep, skipped) where skipped items have:
        {'filename': str, 'reason': str, 'size_bytes': int}
    """
    max_size_bytes = int(max_size_mb * 1024 * 1024)
    patterns = _expand_braces(pattern) if pattern else None

    keep: list[PartInfo] = []
    skipped: list[dict] = []

    for part in parts:
        classification = classify_part(part)

        # Skip inline images unless include_inline
        if classification == "inline_image" and not include_inline:
            skipped.append({
                "filename": part.filename,
                "reason": "inline_image",
                "size_bytes": part.size,
            })
            continue

        # Skip if classification is 'skip'
        if classification == "skip":
            skipped.append({
                "filename": part.filename,
                "reason": "skip",
                "size_bytes": part.size,
            })
            continue

        # Pattern filtering
        if patterns is not None:
            if not any(fnmatch.fnmatch(part.filename, p) for p in patterns):
                skipped.append({
                    "filename": part.filename,
                    "reason": "pattern_mismatch",
                    "size_bytes": part.size,
                })
                continue

        # Size filtering
        if part.size > max_size_bytes:
            skipped.append({
                "filename": part.filename,
                "reason": "exceeds_size_limit",
                "size_bytes": part.size,
            })
            continue

        # Warn for large files (> 25MB) but still keep
        if part.size > _SIZE_WARN_BYTES:
            logger.warning(
                "File %r is %.1f MB — exceeds 25 MB warn threshold",
                part.filename,
                part.size / (1024 * 1024),
            )

        keep.append(part)

    return keep, skipped
