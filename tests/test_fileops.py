"""Tests for _fileops module — base64 decode, filename sanitization, collision, atomic write, sha256."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from _fileops import atomic_write, compute_sha256, decode_attachment, resolve_collision, sanitize_filename


# ---------------------------------------------------------------------------
# decode_attachment
# ---------------------------------------------------------------------------

class TestDecodeAttachment:
    """URL-safe base64 decoding with missing padding."""

    def test_standard_base64_no_padding(self) -> None:
        # "Hello, World!" without padding chars
        assert decode_attachment("SGVsbG8sIFdvcmxkIQ") == b"Hello, World!"

    def test_url_safe_chars(self) -> None:
        # Bytes that produce '-' and '_' in URL-safe base64 (replacing '+' and '/')
        data = bytes([0xFB, 0xEF, 0xBE])
        encoded = base64.urlsafe_b64encode(data).decode().rstrip("=")
        assert "-" in encoded or "_" in encoded  # sanity check
        assert decode_attachment(encoded) == data

    def test_url_safe_slash_replacement(self) -> None:
        # Bytes that produce '_' in URL-safe base64 (standard '/')
        data = bytes([0xFF, 0xFF, 0xFF])
        encoded = base64.urlsafe_b64encode(data).decode().rstrip("=")
        assert decode_attachment(encoded) == data

    def test_missing_one_pad_char(self) -> None:
        # "ab" base64 encodes to "YWI=" — strip one pad char
        assert decode_attachment("YWI") == b"ab"

    def test_missing_two_pad_chars(self) -> None:
        # "a" base64 encodes to "YQ==" — strip two pad chars
        assert decode_attachment("YQ") == b"a"

    def test_empty_string(self) -> None:
        assert decode_attachment("") == b""

    def test_already_padded(self) -> None:
        # Should also work if padding is already present
        assert decode_attachment("SGVsbG8sIFdvcmxkIQ==") == b"Hello, World!"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    """Filename sanitization for safe filesystem use."""

    def test_spaces_to_underscores(self) -> None:
        assert sanitize_filename("my file.pdf") == "my_file.pdf"

    def test_unicode_preserved(self) -> None:
        assert sanitize_filename("café.pdf") == "café.pdf"

    def test_path_separators_stripped(self) -> None:
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result

    def test_path_traversal_produces_safe_name(self) -> None:
        result = sanitize_filename("../../etc/passwd")
        # Must contain "etc" and "passwd" in some form
        assert "passwd" in result

    def test_long_name_truncated(self) -> None:
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 255
        assert result.endswith(".pdf")

    def test_long_name_without_extension(self) -> None:
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 255

    def test_null_bytes_removed(self) -> None:
        result = sanitize_filename("file\x00name.pdf")
        assert "\x00" not in result
        assert "filename.pdf" == result or "file_name.pdf" == result or "filename.pdf" in result

    def test_control_chars_removed(self) -> None:
        result = sanitize_filename("file\x01\x02\x03name.pdf")
        assert not any(0 < ord(c) < 32 for c in result)

    def test_empty_filename(self) -> None:
        assert sanitize_filename("") == "unnamed_attachment"

    def test_only_dots(self) -> None:
        # Filenames like "." or ".." should produce something safe
        result = sanitize_filename("..")
        assert result != ""
        assert result != ".."

    def test_whitespace_only(self) -> None:
        assert sanitize_filename("   ") == "unnamed_attachment"


# ---------------------------------------------------------------------------
# resolve_collision
# ---------------------------------------------------------------------------

class TestResolveCollision:
    """Collision resolution appending _1, _2, etc."""

    def test_no_collision(self, tmp_path: Path) -> None:
        path = tmp_path / "file.pdf"
        assert resolve_collision(path) == path

    def test_single_collision(self, tmp_path: Path) -> None:
        path = tmp_path / "file.pdf"
        path.touch()
        assert resolve_collision(path) == tmp_path / "file_1.pdf"

    def test_multiple_collisions(self, tmp_path: Path) -> None:
        path = tmp_path / "file.pdf"
        path.touch()
        (tmp_path / "file_1.pdf").touch()
        assert resolve_collision(path) == tmp_path / "file_2.pdf"

    def test_ten_plus_collisions(self, tmp_path: Path) -> None:
        path = tmp_path / "file.pdf"
        path.touch()
        for i in range(1, 11):
            (tmp_path / f"file_{i}.pdf").touch()
        assert resolve_collision(path) == tmp_path / "file_11.pdf"

    def test_collision_with_already_numbered_file(self, tmp_path: Path) -> None:
        # If file_1.pdf exists but file.pdf doesn't, no collision
        (tmp_path / "file_1.pdf").touch()
        path = tmp_path / "file.pdf"
        assert resolve_collision(path) == path

    def test_no_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "README"
        path.touch()
        assert resolve_collision(path) == tmp_path / "README_1"

    def test_double_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "archive.tar.gz"
        path.touch()
        result = resolve_collision(path)
        assert result.name.startswith("archive")
        assert result.name.endswith(".tar.gz") or result.name.endswith(".gz")
        assert result != path


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    """Atomic file writing via temp file + os.replace."""

    def test_writes_correct_content(self, tmp_path: Path) -> None:
        target = tmp_path / "output.bin"
        data = b"Hello, World!"
        atomic_write(target, data)
        assert target.read_bytes() == data

    def test_no_partial_file_on_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "output.bin"
        with patch("_fileops.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                atomic_write(target, b"data")
        # Target should not exist (no partial write)
        assert not target.exists()

    def test_temp_file_cleaned_on_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "output.bin"
        with patch("_fileops.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_write(target, b"data")
        # No leftover temp files in the directory
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0

    def test_temp_file_cleaned_on_success(self, tmp_path: Path) -> None:
        target = tmp_path / "output.bin"
        atomic_write(target, b"data")
        # Only the target file should remain
        remaining = list(tmp_path.iterdir())
        assert remaining == [target]

    def test_parent_directory_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "subdir" / "output.bin"
        (tmp_path / "subdir").mkdir()
        atomic_write(target, b"data")
        assert target.read_bytes() == b"data"

    def test_parent_directory_missing_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "nonexistent" / "output.bin"
        with pytest.raises((FileNotFoundError, OSError)):
            atomic_write(target, b"data")

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "output.bin"
        target.write_bytes(b"old")
        atomic_write(target, b"new")
        assert target.read_bytes() == b"new"


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------

class TestComputeSha256:
    """SHA-256 hex digest computation."""

    def test_known_input(self) -> None:
        assert compute_sha256(b"Hello, World!") == (
            "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        )

    def test_empty_bytes(self) -> None:
        assert compute_sha256(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_returns_lowercase_hex(self) -> None:
        result = compute_sha256(b"test")
        assert result == result.lower()
        assert len(result) == 64
