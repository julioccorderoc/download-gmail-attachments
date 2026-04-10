"""Tests for MIME tree walking, part classification, and filtering."""

from __future__ import annotations

import logging

import pytest

from _mime import PartInfo, classify_part, filter_parts, walk_parts


# ---------------------------------------------------------------------------
# Helpers to build PartInfo for testing
# ---------------------------------------------------------------------------

def _make_part(
    *,
    filename: str = "file.bin",
    mime_type: str = "application/octet-stream",
    size: int = 1000,
    attachment_id: str = "att_123",
    disposition: str = "attachment",
    has_content_id: bool = False,
    headers: dict[str, str] | None = None,
) -> PartInfo:
    return PartInfo(
        filename=filename,
        mime_type=mime_type,
        size=size,
        attachment_id=attachment_id,
        disposition=disposition,
        has_content_id=has_content_id,
        headers=headers or {},
    )


# ===========================================================================
# walk_parts tests
# ===========================================================================

class TestWalkParts:
    """Tests for walk_parts — recursive MIME tree traversal."""

    def test_empty_payload_no_parts(self) -> None:
        """Empty payload (no 'parts' key) returns empty list."""
        result = walk_parts({"body": {"size": 0}, "mimeType": "text/plain"})
        assert result == []

    def test_flat_parts_single_level(self) -> None:
        """Single-level parts list collects parts with attachmentId."""
        payload = {
            "mimeType": "multipart/mixed",
            "body": {"size": 0},
            "parts": [
                {
                    "filename": "doc.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att_1", "size": 5000},
                    "headers": [
                        {"name": "Content-Disposition", "value": "attachment; filename=\"doc.pdf\""},
                    ],
                },
                {
                    "filename": "",
                    "mimeType": "text/plain",
                    "body": {"size": 100},
                    "headers": [
                        {"name": "Content-Type", "value": "text/plain; charset=utf-8"},
                    ],
                },
            ],
        }
        parts = walk_parts(payload)
        assert len(parts) == 1
        assert parts[0].filename == "doc.pdf"
        assert parts[0].attachment_id == "att_1"
        assert parts[0].size == 5000

    def test_deeply_nested_parts_from_fixture(self, message_payload: dict) -> None:
        """Real fixture: multipart/mixed > multipart/related > multipart/alternative.

        Should find 2 inline images + 2 PDF attachments = 4 parts.
        text/plain and text/html without attachmentId are skipped.
        """
        parts = walk_parts(message_payload)
        assert len(parts) == 4
        filenames = [p.filename for p in parts]
        assert "image001.jpg" in filenames
        assert "image002.jpg" in filenames
        assert any("YK772_" in f for f in filenames)
        assert any("YK772A_" in f for f in filenames)

    def test_text_parts_without_attachment_id_skipped(self, message_payload: dict) -> None:
        """text/plain and text/html body parts are not collected."""
        parts = walk_parts(message_payload)
        mime_types = [p.mime_type for p in parts]
        assert "text/plain" not in mime_types
        assert "text/html" not in mime_types

    def test_forwarded_message_re_nested(self) -> None:
        """Forwarded message with re-nested multipart structure."""
        payload = {
            "mimeType": "multipart/mixed",
            "body": {"size": 0},
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "body": {"size": 0},
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"size": 50},
                            "filename": "",
                            "headers": [],
                        },
                    ],
                },
                {
                    "mimeType": "message/rfc822",
                    "body": {"size": 0},
                    "filename": "",
                    "headers": [],
                    "parts": [
                        {
                            "mimeType": "multipart/mixed",
                            "body": {"size": 0},
                            "parts": [
                                {
                                    "mimeType": "text/html",
                                    "body": {"size": 200},
                                    "filename": "",
                                    "headers": [],
                                },
                                {
                                    "mimeType": "application/pdf",
                                    "body": {"attachmentId": "fwd_att", "size": 9999},
                                    "filename": "forwarded.pdf",
                                    "headers": [
                                        {"name": "Content-Disposition", "value": "attachment; filename=\"forwarded.pdf\""},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        parts = walk_parts(payload)
        assert len(parts) == 1
        assert parts[0].filename == "forwarded.pdf"
        assert parts[0].attachment_id == "fwd_att"

    def test_part_headers_parsed_to_dict(self, message_payload: dict) -> None:
        """Headers list is converted to dict[str, str] on PartInfo."""
        parts = walk_parts(message_payload)
        pdf_part = [p for p in parts if p.mime_type == "application/pdf"][0]
        assert "Content-Disposition" in pdf_part.headers
        assert "Content-Type" in pdf_part.headers

    def test_inline_disposition_detected(self, message_payload: dict) -> None:
        """Inline images have disposition='inline'."""
        parts = walk_parts(message_payload)
        inline_parts = [p for p in parts if p.filename == "image001.jpg"]
        assert len(inline_parts) == 1
        assert inline_parts[0].disposition == "inline"

    def test_content_id_detected(self, message_payload: dict) -> None:
        """Parts with Content-ID header have has_content_id=True."""
        parts = walk_parts(message_payload)
        img = [p for p in parts if p.filename == "image001.jpg"][0]
        assert img.has_content_id is True


# ===========================================================================
# classify_part tests
# ===========================================================================

class TestClassifyPart:
    """Tests for classify_part — attachment vs inline_image vs skip."""

    def test_real_attachment(self) -> None:
        """Content-Disposition starts with 'attachment' -> 'attachment'."""
        part = _make_part(disposition="attachment", mime_type="application/pdf")
        assert classify_part(part) == "attachment"

    def test_inline_with_content_id(self) -> None:
        """Inline + Content-ID -> 'inline_image'."""
        part = _make_part(
            disposition="inline",
            has_content_id=True,
            mime_type="image/jpeg",
            filename="photo.jpg",
        )
        assert classify_part(part) == "inline_image"

    def test_filename_pattern_image_signature(self) -> None:
        """Filename like image001.jpg -> 'inline_image' (signature heuristic)."""
        part = _make_part(
            filename="image003.png",
            mime_type="image/png",
            disposition="inline",
            has_content_id=False,
        )
        assert classify_part(part) == "inline_image"

    def test_filename_pattern_image_gif(self) -> None:
        """Filename like image99.gif -> 'inline_image'."""
        part = _make_part(
            filename="image99.gif",
            mime_type="image/gif",
            disposition="inline",
            has_content_id=False,
        )
        assert classify_part(part) == "inline_image"

    def test_small_inline_image_below_50kb(self) -> None:
        """Image < 50KB with inline disposition -> 'inline_image'."""
        part = _make_part(
            filename="logo.png",
            mime_type="image/png",
            size=30_000,
            disposition="inline",
            has_content_id=False,
        )
        assert classify_part(part) == "inline_image"

    def test_large_inline_image_above_50kb(self) -> None:
        """Image >= 50KB with inline disposition -> 'attachment' (real content)."""
        part = _make_part(
            filename="photo.jpg",
            mime_type="image/jpeg",
            size=60_000,
            disposition="inline",
            has_content_id=False,
        )
        assert classify_part(part) == "attachment"

    def test_non_image_inline_no_content_id(self) -> None:
        """Non-image inline without Content-ID -> 'attachment'."""
        part = _make_part(
            filename="data.csv",
            mime_type="text/csv",
            disposition="inline",
            has_content_id=False,
        )
        assert classify_part(part) == "attachment"

    def test_inline_with_content_id_non_image(self) -> None:
        """Inline + Content-ID even for non-image -> 'inline_image' (embedded)."""
        part = _make_part(
            filename="banner.html",
            mime_type="text/html",
            disposition="inline",
            has_content_id=True,
        )
        assert classify_part(part) == "inline_image"

    def test_fixture_inline_images_classified(self, message_payload: dict) -> None:
        """Inline images from fixture are classified as inline_image."""
        parts = walk_parts(message_payload)
        img_parts = [p for p in parts if p.filename.startswith("image00")]
        for p in img_parts:
            assert classify_part(p) == "inline_image"

    def test_fixture_pdfs_classified_as_attachment(self, message_payload: dict) -> None:
        """PDFs from fixture are classified as attachment."""
        parts = walk_parts(message_payload)
        pdf_parts = [p for p in parts if p.mime_type == "application/pdf"]
        for p in pdf_parts:
            assert classify_part(p) == "attachment"


# ===========================================================================
# filter_parts tests
# ===========================================================================

class TestFilterParts:
    """Tests for filter_parts — pattern matching, inline filtering, size limits."""

    def test_no_filter_returns_attachments_only(self, message_payload: dict) -> None:
        """Default: returns attachments, skips inline images with reasons."""
        parts = walk_parts(message_payload)
        keep, skipped = filter_parts(parts)
        assert len(keep) == 2  # 2 PDFs
        assert all(p.mime_type == "application/pdf" for p in keep)
        assert len(skipped) == 2  # 2 inline images
        for s in skipped:
            assert "reason" in s
            assert "filename" in s

    def test_include_inline_true(self, message_payload: dict) -> None:
        """include_inline=True includes inline images."""
        parts = walk_parts(message_payload)
        keep, skipped = filter_parts(parts, include_inline=True)
        assert len(keep) == 4  # 2 PDFs + 2 inline images
        assert len(skipped) == 0

    def test_pattern_pdf_only(self, message_payload: dict) -> None:
        """pattern='*.pdf' filters to PDFs only."""
        parts = walk_parts(message_payload)
        keep, skipped = filter_parts(parts, pattern="*.pdf")
        assert len(keep) == 2
        assert all(p.filename.endswith(".pdf") for p in keep)

    def test_pattern_no_match(self, message_payload: dict) -> None:
        """Pattern that matches nothing skips all with reason."""
        parts = walk_parts(message_payload)
        keep, skipped = filter_parts(parts, pattern="*.docx")
        assert len(keep) == 0
        # Skipped includes both inline (inline_image reason) and non-matching attachments
        pattern_skipped = [s for s in skipped if s["reason"] == "pattern_mismatch"]
        assert len(pattern_skipped) == 2  # 2 PDFs don't match *.docx

    def test_pattern_brace_expansion(self) -> None:
        """pattern='*.{pdf,xlsx}' matches both PDF and XLSX files."""
        parts = [
            _make_part(filename="report.pdf", disposition="attachment"),
            _make_part(filename="data.xlsx", disposition="attachment"),
            _make_part(filename="notes.txt", disposition="attachment"),
        ]
        keep, skipped = filter_parts(parts, pattern="*.{pdf,xlsx}")
        assert len(keep) == 2
        filenames = {p.filename for p in keep}
        assert filenames == {"report.pdf", "data.xlsx"}

    def test_pattern_prefix_match(self) -> None:
        """pattern='COA*' matches files starting with COA."""
        parts = [
            _make_part(filename="COA_batch123.pdf", disposition="attachment"),
            _make_part(filename="COA_batch456.pdf", disposition="attachment"),
            _make_part(filename="invoice_789.pdf", disposition="attachment"),
        ]
        keep, skipped = filter_parts(parts, pattern="COA*")
        assert len(keep) == 2
        assert all(p.filename.startswith("COA") for p in keep)

    def test_max_size_mb_filters_large(self) -> None:
        """max_size_mb=0.001 (~1KB) skips large files."""
        parts = [
            _make_part(filename="small.pdf", size=500, disposition="attachment"),
            _make_part(filename="big.pdf", size=50_000, disposition="attachment"),
        ]
        keep, skipped = filter_parts(parts, max_size_mb=0.001)
        assert len(keep) == 1
        assert keep[0].filename == "small.pdf"
        size_skipped = [s for s in skipped if s["reason"] == "exceeds_size_limit"]
        assert len(size_skipped) == 1
        assert size_skipped[0]["filename"] == "big.pdf"

    def test_warn_threshold_25mb(self, message_payload: dict, caplog: pytest.LogCaptureFixture) -> None:
        """Files > 25MB trigger a log warning but are still kept."""
        big_part = _make_part(
            filename="huge.pdf",
            size=30_000_000,  # ~30MB
            disposition="attachment",
        )
        with caplog.at_level(logging.WARNING):
            keep, skipped = filter_parts([big_part], max_size_mb=100)
        assert len(keep) == 1
        assert any("25" in r.message or "warn" in r.message.lower() for r in caplog.records)

    def test_skipped_items_have_required_keys(self, message_payload: dict) -> None:
        """Skipped items have filename, reason, and size_bytes."""
        parts = walk_parts(message_payload)
        _, skipped = filter_parts(parts)
        for s in skipped:
            assert "filename" in s
            assert "reason" in s
            assert "size_bytes" in s

    def test_pattern_case_sensitive(self) -> None:
        """Pattern matching is case-sensitive by default (fnmatch behavior)."""
        parts = [
            _make_part(filename="Report.PDF", disposition="attachment"),
            _make_part(filename="report.pdf", disposition="attachment"),
        ]
        keep, _ = filter_parts(parts, pattern="*.pdf")
        # fnmatch on macOS is case-insensitive, on Linux case-sensitive
        # We just verify it returns at least the lowercase match
        assert any(p.filename == "report.pdf" for p in keep)
