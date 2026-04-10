"""File operations for Gmail attachment handling.

Base64 decoding, filename sanitization, collision resolution,
atomic writes, and SHA-256 hashing.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import tempfile
from pathlib import Path


def decode_attachment(data: str) -> bytes:
    """Decode Gmail's URL-safe base64 attachment data.

    Gmail uses URL-safe base64: '-' instead of '+', '_' instead of '/'.
    Padding may be missing.
    """
    # Add missing padding
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename for safe filesystem use.

    - Replaces spaces with underscores
    - Strips path separators and traversal sequences
    - Removes null bytes and control characters
    - Preserves safe unicode
    - Truncates to 255 bytes while preserving extension
    - Returns 'unnamed_attachment' for empty/whitespace-only input
    """
    # Remove null bytes and control characters (except tab/newline which we also remove)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)

    # Replace path separators with underscores
    name = name.replace("/", "_").replace("\\", "_")

    # Remove leading dots and dot-dot sequences that survived separator replacement
    # e.g., "../../etc/passwd" -> ".._.._.._etc_passwd" after sep replace
    # Remove leading dot-underscore patterns
    name = re.sub(r"^[._]+", "", name)

    # Replace spaces with underscores
    name = name.replace(" ", "_")

    # Strip leading/trailing whitespace and underscores
    name = name.strip().strip("_")

    # If nothing left, use default
    if not name:
        return "unnamed_attachment"

    # Truncate to 255 bytes while preserving extension
    encoded = name.encode("utf-8")
    if len(encoded) <= 255:
        return name

    # Split into stem and extension(s) — handle .tar.gz style
    p = Path(name)
    suffixes = "".join(p.suffixes)  # e.g., ".tar.gz"
    stem = name[: len(name) - len(suffixes)] if suffixes else name
    ext_bytes = suffixes.encode("utf-8")

    # Truncate stem to fit within 255 bytes with extension
    max_stem_bytes = 255 - len(ext_bytes)
    stem_encoded = stem.encode("utf-8")
    if max_stem_bytes <= 0:
        # Extension itself is too long; just truncate the whole thing
        return name.encode("utf-8")[:255].decode("utf-8", errors="ignore")

    # Truncate stem bytes, being careful not to split a multi-byte char
    truncated_stem = stem_encoded[:max_stem_bytes].decode("utf-8", errors="ignore")

    return truncated_stem + suffixes


def resolve_collision(path: Path) -> Path:
    """If path exists, append _1, _2, etc. until unique."""
    if not path.exists():
        return path

    stem = path.stem
    # Handle compound extensions like .tar.gz
    suffixes = "".join(path.suffixes)
    # But stem from Path only strips last suffix, so recalculate
    # For "archive.tar.gz": stem="archive.tar", suffixes=".tar.gz"
    # We want stem="archive", so strip all suffixes from name
    name = path.name
    if suffixes:
        base = name[: len(name) - len(suffixes)]
    else:
        base = stem

    counter = 1
    while True:
        new_name = f"{base}_{counter}{suffixes}"
        candidate = path.parent / new_name
        if not candidate.exists():
            return candidate
        counter += 1


def atomic_write(path: Path, data: bytes) -> None:
    """Write data atomically using temp file + os.replace in same directory.

    Creates a temporary file in the same directory as target (to ensure
    same filesystem), writes data, flushes, then atomically replaces.
    Cleans up temp file on failure.
    """
    parent = path.parent
    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=parent)
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = None  # Mark as closed
        os.replace(tmp_path, path)
        tmp_path = None  # Mark as replaced (no cleanup needed)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def compute_sha256(data: bytes) -> str:
    """Return hex SHA-256 digest of data."""
    return hashlib.sha256(data).hexdigest()
