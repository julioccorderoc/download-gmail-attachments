#!/usr/bin/env python3
"""Download Gmail attachments by message ID."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from _gws import GwsError, fetch_message, fetch_attachment
from _mime import walk_parts, filter_parts
from _fileops import decode_attachment, sanitize_filename, resolve_collision, atomic_write, compute_sha256
from _manifest import FileEntry, SkippedEntry, build_manifest

logger = logging.getLogger(__name__)


def _format_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    else:
        return f"{n / (1024 * 1024 * 1024):.1f} GB"


def run(args: list[str]) -> int:
    """Main pipeline. Returns exit code."""
    parser = argparse.ArgumentParser(description="Download Gmail attachments")
    parser.add_argument("message_id", help="Gmail message ID")
    parser.add_argument("--to", required=True, dest="output_dir", help="Output directory")
    parser.add_argument("--filter", dest="pattern", help="Filename glob pattern")
    parser.add_argument("--include-inline", action="store_true", help="Include inline images")
    parser.add_argument("--max-size", type=float, default=100, help="Max attachment size in MB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    parser.add_argument("--json-summary", action="store_true", help="Print summary JSON to stdout")
    opts = parser.parse_args(args)

    output_path = Path(opts.output_dir)

    # 1. Fetch message metadata
    try:
        metadata = fetch_message(opts.message_id)
    except GwsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return e.exit_code

    # 2. Walk MIME tree
    parts = walk_parts(metadata["payload"])

    # 3. Filter parts
    kept, skipped_dicts = filter_parts(
        parts,
        pattern=opts.pattern,
        include_inline=opts.include_inline,
        max_size_mb=opts.max_size,
    )

    # Convert skipped dicts to SkippedEntry objects
    skipped_entries = [
        SkippedEntry(
            filename=s["filename"],
            reason=s["reason"],
            size_bytes=s["size_bytes"],
        )
        for s in skipped_dicts
    ]

    # Create output directory
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error creating output directory: {e}", file=sys.stderr)
        return 5

    # 4. Download each kept part (unless dry-run)
    file_entries: list[FileEntry] = []

    if not kept:
        # No attachments after filtering — still write manifest, return 4
        manifest = build_manifest(
            opts.message_id, metadata, file_entries, skipped_entries, str(output_path)
        )
        manifest.write(output_path)

        total_parts = len(file_entries) + len(skipped_entries)
        total_bytes = sum(f.size_bytes for f in file_entries)
        print(
            f"Downloaded {len(file_entries)}/{total_parts} attachments "
            f"({_format_bytes(total_bytes)}) \u2192 {output_path}/",
            file=sys.stderr,
        )

        if opts.json_summary:
            print(json.dumps(asdict(manifest.summary), indent=2))

        return 4

    for part in kept:
        if opts.dry_run:
            # Dry-run: record entry with null path and sha256
            sanitized = sanitize_filename(part.filename)
            file_entries.append(
                FileEntry(
                    filename=sanitized,
                    original_filename=part.filename,
                    mime_type=part.mime_type,
                    size_bytes=part.size,
                    sha256=None,
                    disposition=part.disposition,
                    path=None,
                )
            )
            continue

        # Fetch attachment data
        try:
            att_data = fetch_attachment(opts.message_id, part.attachment_id)
        except GwsError as e:
            print(f"Error fetching attachment: {e}", file=sys.stderr)
            return e.exit_code

        # Decode base64
        raw_bytes = decode_attachment(att_data["data"])

        # Verify size
        reported_size = att_data.get("size", 0)
        if len(raw_bytes) != reported_size:
            logger.warning(
                "Size mismatch for %r: reported %d bytes, got %d bytes",
                part.filename,
                reported_size,
                len(raw_bytes),
            )

        # Compute SHA-256
        sha = compute_sha256(raw_bytes)

        # Sanitize filename
        sanitized = sanitize_filename(part.filename)

        # Resolve collisions
        file_path = resolve_collision(output_path / sanitized)

        # Atomic write
        try:
            atomic_write(file_path, raw_bytes)
        except OSError as e:
            print(f"Error writing file: {e}", file=sys.stderr)
            return 5

        file_entries.append(
            FileEntry(
                filename=file_path.name,
                original_filename=part.filename,
                mime_type=part.mime_type,
                size_bytes=len(raw_bytes),
                sha256=sha,
                disposition=part.disposition,
                path=str(file_path),
            )
        )

    # 5. Build manifest
    manifest = build_manifest(
        opts.message_id, metadata, file_entries, skipped_entries, str(output_path)
    )

    # 6. Write manifest
    try:
        manifest.write(output_path)
    except OSError as e:
        print(f"Error writing manifest: {e}", file=sys.stderr)
        return 5

    # 7. Print stderr summary
    total_parts = len(file_entries) + len(skipped_entries)
    total_bytes = sum(f.size_bytes for f in file_entries)
    print(
        f"Downloaded {len(file_entries)}/{total_parts} attachments "
        f"({_format_bytes(total_bytes)}) \u2192 {output_path}/",
        file=sys.stderr,
    )

    # 8. JSON summary to stdout
    if opts.json_summary:
        print(json.dumps(asdict(manifest.summary), indent=2))

    return 0


def main() -> None:
    """Entry point."""
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
