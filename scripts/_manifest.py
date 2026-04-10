"""Manifest dataclass + JSON serialization for download-gmail-attachments."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileEntry:
    """A successfully downloaded file."""

    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    disposition: str
    path: str | None  # None for dry-run


@dataclass
class SkippedEntry:
    """A part that was skipped (e.g. inline image)."""

    filename: str
    reason: str
    size_bytes: int


@dataclass
class Summary:
    """Aggregate counts for the manifest."""

    total_parts: int
    downloaded: int
    skipped: int
    total_bytes: int


@dataclass
class Manifest:
    """Full manifest for a single message's attachment download."""

    message_id: str
    subject: str
    from_: str  # "from" is reserved; serialized as "from"
    date: str
    downloaded_at: str
    output_dir: str
    files: list[FileEntry]
    skipped: list[SkippedEntry]
    summary: Summary

    def to_dict(self) -> dict:
        """Convert to dict with 'from' key (not 'from_')."""
        d = asdict(self)
        d["from"] = d.pop("from_")
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def write(self, output_dir: str | Path) -> Path:
        """Write manifest_<message-id>.json to output_dir. Returns path."""
        output_dir = Path(output_dir)
        # Sanitize message_id for use in filename
        safe_id = re.sub(r"[^\w\-.]", "_", self.message_id)
        path = output_dir / f"manifest_{safe_id}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def extract_header(headers: list[dict], name: str) -> str:
    """Extract header value by name (case-insensitive) from Gmail headers list."""
    name_lower = name.lower()
    for header in headers:
        if header.get("name", "").lower() == name_lower:
            return header.get("value", "")
    return ""


def build_manifest(
    message_id: str,
    metadata: dict,
    files: list[FileEntry],
    skipped: list[SkippedEntry],
    output_dir: str,
) -> Manifest:
    """Build a Manifest from message metadata and download results."""
    headers = metadata.get("payload", {}).get("headers", [])
    total_bytes = sum(f.size_bytes for f in files)

    return Manifest(
        message_id=message_id,
        subject=extract_header(headers, "Subject"),
        from_=extract_header(headers, "From"),
        date=extract_header(headers, "Date"),
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        output_dir=output_dir,
        files=files,
        skipped=skipped,
        summary=Summary(
            total_parts=len(files) + len(skipped),
            downloaded=len(files),
            skipped=len(skipped),
            total_bytes=total_bytes,
        ),
    )
