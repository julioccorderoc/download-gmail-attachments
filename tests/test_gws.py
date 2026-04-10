"""Tests for _gws module — gws CLI wrapper with retry and error handling."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from _gws import GwsError, fetch_attachment, fetch_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

KEYRING_NOISE = "Using keyring backend: keyring\n"


def _completed(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Build a CompletedProcess for mocking."""
    return subprocess.CompletedProcess(
        args=["gws"], stdout=stdout, stderr=stderr, returncode=returncode
    )


# ---------------------------------------------------------------------------
# fetch_message — happy path
# ---------------------------------------------------------------------------


class TestFetchMessage:
    """Tests for fetch_message()."""

    def test_returns_parsed_json(self, sample_message_metadata: dict) -> None:
        """Successful call returns parsed JSON dict from stdout."""
        raw_json = json.dumps(sample_message_metadata)
        with patch("_gws.subprocess.run", return_value=_completed(stdout=raw_json)):
            result = fetch_message("19d77c4017cb684d")
        assert result == sample_message_metadata
        assert result["id"] == "19d77c4017cb684d"

    def test_calls_gws_with_correct_args(self) -> None:
        """Verify the exact subprocess command constructed."""
        dummy = _completed(stdout='{"id":"abc"}')
        with patch("_gws.subprocess.run", return_value=dummy) as mock_run:
            fetch_message("abc123")
        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]  # positional arg 0 is the command list/str
        # Should contain the gws command parts
        assert "gws" in cmd[0] if isinstance(cmd, list) else "gws" in cmd
        params_json = json.loads(args.kwargs.get("input", "{}")) if "input" in (args.kwargs or {}) else None
        # Alternatively check the full command string
        call_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        assert "gmail" in call_str
        assert "users" in call_str
        assert "messages" in call_str
        assert "get" in call_str
        assert "abc123" in call_str

    def test_filters_keyring_noise_from_stderr(self) -> None:
        """The keyring backend line must be stripped; no error raised."""
        result_json = '{"id":"msg1"}'
        cp = _completed(stdout=result_json, stderr=KEYRING_NOISE)
        with patch("_gws.subprocess.run", return_value=cp):
            result = fetch_message("msg1")
        assert result["id"] == "msg1"


# ---------------------------------------------------------------------------
# fetch_attachment — happy path
# ---------------------------------------------------------------------------


class TestFetchAttachment:
    """Tests for fetch_attachment()."""

    def test_returns_parsed_json(self, sample_attachment_response: dict) -> None:
        """Successful call returns parsed JSON dict."""
        raw_json = json.dumps(sample_attachment_response)
        with patch("_gws.subprocess.run", return_value=_completed(stdout=raw_json)):
            result = fetch_attachment("msg1", "att1")
        assert result == sample_attachment_response
        assert result["size"] == 13

    def test_calls_gws_with_correct_args(self) -> None:
        """Verify the subprocess command includes attachments get."""
        dummy = _completed(stdout='{"size":1,"data":"AA"}')
        with patch("_gws.subprocess.run", return_value=dummy) as mock_run:
            fetch_attachment("msg_x", "att_y")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        call_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        assert "attachments" in call_str
        assert "msg_x" in call_str
        assert "att_y" in call_str


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    """Test that returncode/stderr are mapped to GwsError with correct exit_code."""

    def test_auth_failure_raises_exit_code_1(self) -> None:
        """Auth error (returncode 1) raises GwsError with exit_code=1."""
        cp = _completed(
            stderr="Error: authentication failed\n", returncode=1
        )
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1")
        assert exc_info.value.exit_code == 1

    def test_not_found_raises_exit_code_2(self) -> None:
        """Not-found error (returncode 2) raises GwsError with exit_code=2."""
        cp = _completed(
            stderr="Error: Requested entity was not found.\n", returncode=2
        )
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("nonexistent")
        assert exc_info.value.exit_code == 2

    def test_transient_api_error_raises_exit_code_3(self) -> None:
        """Transient/API error (returncode 3) raises GwsError with exit_code=3."""
        cp = _completed(
            stderr="Error: Backend Error\n", returncode=3
        )
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1")
        assert exc_info.value.exit_code == 3

    def test_unknown_nonzero_maps_to_exit_code_3(self) -> None:
        """Unknown nonzero return codes are treated as transient (exit_code=3)."""
        cp = _completed(stderr="Error: something unexpected\n", returncode=42)
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1")
        assert exc_info.value.exit_code == 3

    def test_gws_error_contains_stderr_message(self) -> None:
        """GwsError message includes filtered stderr."""
        cp = _completed(
            stderr=KEYRING_NOISE + "Error: token expired\n",
            returncode=1,
        )
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError, match="token expired"):
                fetch_message("msg1")


# ---------------------------------------------------------------------------
# stderr filtering
# ---------------------------------------------------------------------------


class TestStderrFiltering:
    """Ensure keyring noise is stripped before error parsing."""

    def test_keyring_only_stderr_is_treated_as_clean(self) -> None:
        """If stderr only has keyring noise and rc=0, no error."""
        cp = _completed(stdout='{"id":"m1"}', stderr=KEYRING_NOISE, returncode=0)
        with patch("_gws.subprocess.run", return_value=cp):
            result = fetch_message("m1")
        assert result["id"] == "m1"

    def test_keyring_noise_stripped_from_error_message(self) -> None:
        """The keyring line should NOT appear in GwsError messages."""
        cp = _completed(
            stderr=KEYRING_NOISE + "Error: forbidden\n",
            returncode=1,
        )
        with patch("_gws.subprocess.run", return_value=cp):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1")
        assert "keyring" not in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Test exponential backoff for retryable (transient) errors."""

    def test_retries_on_transient_then_succeeds(self) -> None:
        """Mock 2 transient failures then success; verify retries and result."""
        fail = _completed(stderr="Error: rate limit\n", returncode=3)
        success = _completed(stdout='{"id":"ok"}')
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", side_effect=[fail, fail, success]):
            result = fetch_message("msg1", _sleep=sleep_mock)

        assert result["id"] == "ok"
        assert sleep_mock.call_count == 2
        # First sleep should be around 1s (base), second around 2s
        first_delay = sleep_mock.call_args_list[0][0][0]
        second_delay = sleep_mock.call_args_list[1][0][0]
        assert 0.5 <= first_delay <= 2.0  # 1s with jitter
        assert 1.0 <= second_delay <= 4.0  # 2s with jitter

    def test_raises_after_max_retries_exhausted(self) -> None:
        """After 5 retries, raises GwsError."""
        fail = _completed(stderr="Error: rate limit\n", returncode=3)
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", return_value=fail):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1", _sleep=sleep_mock)
        assert exc_info.value.exit_code == 3
        # 5 retries = 5 sleeps (initial attempt + 5 retries = 6 calls total)
        assert sleep_mock.call_count == 5

    def test_no_retry_on_auth_failure(self) -> None:
        """Auth errors (exit_code=1) must NOT be retried."""
        fail = _completed(stderr="Error: auth failed\n", returncode=1)
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", return_value=fail):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1", _sleep=sleep_mock)
        assert exc_info.value.exit_code == 1
        assert sleep_mock.call_count == 0

    def test_no_retry_on_not_found(self) -> None:
        """Not-found errors (exit_code=2) must NOT be retried."""
        fail = _completed(stderr="Error: not found\n", returncode=2)
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", return_value=fail):
            with pytest.raises(GwsError) as exc_info:
                fetch_message("msg1", _sleep=sleep_mock)
        assert exc_info.value.exit_code == 2
        assert sleep_mock.call_count == 0

    def test_429_like_error_retried(self) -> None:
        """A 429-like rate-limit error (transient, rc=3) retries then succeeds."""
        rate_limit = _completed(
            stderr="Error: 429 Too Many Requests\n", returncode=3
        )
        ok = _completed(stdout='{"id":"done"}')
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", side_effect=[rate_limit, rate_limit, ok]):
            result = fetch_message("msg1", _sleep=sleep_mock)
        assert result["id"] == "done"
        assert sleep_mock.call_count == 2

    def test_fetch_attachment_also_retries(self) -> None:
        """fetch_attachment uses the same retry logic."""
        fail = _completed(stderr="Error: backend\n", returncode=3)
        ok = _completed(stdout='{"size":1,"data":"AA"}')
        sleep_mock = MagicMock()

        with patch("_gws.subprocess.run", side_effect=[fail, ok]):
            result = fetch_attachment("m1", "a1", _sleep=sleep_mock)
        assert result["size"] == 1
        assert sleep_mock.call_count == 1
