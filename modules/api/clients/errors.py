"""Typed failures of the REST client: a failure is never returned as if it were a result."""
from __future__ import annotations

from typing import Any, Optional


class ApiError(Exception):
    """Base class for all client-side failures."""


class ApiTimeout(ApiError):
    """The server did not answer within the configured connect/read timeout."""


class ApiConnectionError(ApiError):
    """The server could not be reached (refused, reset, DNS)."""


class ApiMalformedResponse(ApiError):
    """A *successful* answer whose body is not valid JSON or does not match the documented shape.

    Also raised when an error status carries a non-JSON body and JSON was expected (for example an HTML 502).
    """

    def __init__(self, message: str, body: Optional[str] = None):
        super().__init__(message)
        self.body = body


class ApiHttpError(ApiError):
    """The server answered with an unexpected HTTP status (normally an error).

    ``code`` is the frozen contract error code. If the body is not a well-formed error envelope
    (``{"error": {"code": str, "message": str}}``), ``code`` is ``None``, ``envelope_valid`` is ``False``
    and ``payload`` holds the raw decoded body. A malformed envelope never hides the real status.
    """

    def __init__(self, status: int, code: Optional[str], message: str, payload: Any = None,
                 envelope_valid: bool = True):
        super().__init__("HTTP %d %s: %s" % (status, code, message))
        self.envelope_valid = envelope_valid
        self.status = status
        self.code = code
        self.message = message
        self.payload = payload
