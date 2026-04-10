"""Wrapper around the gws CLI for Gmail API calls.

Handles subprocess invocation, JSON parsing, stderr filtering,
error classification, and exponential backoff with jitter.
"""

from __future__ import annotations

import json
import random
import subprocess
import time
from typing import Any, Callable

# Noise that gws always emits on stderr — must be stripped.
_KEYRING_NOISE = "Using keyring backend: keyring"

# Retry configuration
_MAX_RETRIES = 5
_INITIAL_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 32.0


class GwsError(Exception):
    """Error raised when a gws CLI call fails.

    Attributes:
        exit_code: Classified exit code (1=auth, 2=not found, 3=transient/API).
    """

    def __init__(self, message: str, *, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _filter_stderr(stderr: str) -> str:
    """Remove the keyring noise line from stderr, returning the rest."""
    lines = [
        line
        for line in stderr.splitlines()
        if line.strip() and line.strip() != _KEYRING_NOISE
    ]
    return "\n".join(lines)


def _classify_exit_code(returncode: int) -> int:
    """Map a gws returncode to our exit-code scheme.

    1 = auth failure, 2 = not found, 3 = transient / API error.
    Unknown codes are treated as transient (3).
    """
    if returncode == 1:
        return 1
    if returncode == 2:
        return 2
    # Everything else (including 3, 429-like, unknown) is transient
    return 3


def _is_retryable(exit_code: int) -> bool:
    """Only transient errors (exit_code 3) are retryable."""
    return exit_code == 3


def _run_gws(
    cmd: list[str],
    *,
    _sleep: Callable[[float], Any] | None = None,
) -> dict[str, Any]:
    """Execute a gws command with retry logic.

    Args:
        cmd: The full command list to pass to subprocess.run.
        _sleep: Injectable sleep function for testing. Defaults to time.sleep.

    Returns:
        Parsed JSON dict from stdout.

    Raises:
        GwsError: On non-retryable failure or after retries exhausted.
    """
    sleep_fn = _sleep if _sleep is not None else time.sleep
    backoff = _INITIAL_BACKOFF_S
    last_error: GwsError | None = None

    for attempt in range(_MAX_RETRIES + 1):  # initial + retries
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        filtered_stderr = _filter_stderr(cp.stderr)

        if cp.returncode == 0:
            return json.loads(cp.stdout)

        exit_code = _classify_exit_code(cp.returncode)
        last_error = GwsError(
            filtered_stderr or f"gws exited with code {cp.returncode}",
            exit_code=exit_code,
        )

        if not _is_retryable(exit_code):
            raise last_error

        # Don't sleep after the last attempt
        if attempt < _MAX_RETRIES:
            jitter = random.uniform(0.5, 1.5)
            sleep_fn(backoff * jitter)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)

    # All retries exhausted
    assert last_error is not None
    raise last_error


def fetch_message(
    message_id: str,
    *,
    _sleep: Callable[[float], Any] | None = None,
) -> dict[str, Any]:
    """Fetch a Gmail message by ID using gws CLI.

    Args:
        message_id: The Gmail message ID.
        _sleep: Injectable sleep for testing.

    Returns:
        Parsed message metadata dict.

    Raises:
        GwsError: On failure.
    """
    params = json.dumps({"userId": "me", "id": message_id, "format": "full"})
    cmd = [
        "gws",
        "gmail",
        "users",
        "messages",
        "get",
        "--params",
        params,
    ]
    return _run_gws(cmd, _sleep=_sleep)


def fetch_attachment(
    message_id: str,
    attachment_id: str,
    *,
    _sleep: Callable[[float], Any] | None = None,
) -> dict[str, Any]:
    """Fetch a Gmail attachment by message and attachment IDs using gws CLI.

    Args:
        message_id: The Gmail message ID.
        attachment_id: The attachment ID within the message.
        _sleep: Injectable sleep for testing.

    Returns:
        Parsed attachment dict with 'size' and 'data' fields.

    Raises:
        GwsError: On failure.
    """
    params = json.dumps(
        {"userId": "me", "messageId": message_id, "id": attachment_id}
    )
    cmd = [
        "gws",
        "gmail",
        "users",
        "messages",
        "attachments",
        "get",
        "--params",
        params,
    ]
    return _run_gws(cmd, _sleep=_sleep)
