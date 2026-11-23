"""Typed API errors. Messages are written for end users: no paths, no stack traces, no internals."""
from __future__ import annotations

import re

_PATH_RE = re.compile(r"([A-Za-z]:[\\/][^\s\"'<>|]*|/(?:Users|home|var|tmp|opt|mnt)/[^\s\"'<>|]*)")


def scrub(text: str) -> str:
    """Remove filesystem paths from any string before it leaves the process."""
    return _PATH_RE.sub("<path>", text)


def scrub_obj(obj):
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, list):
        return [scrub_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub_obj(v) for k, v in obj.items()}
    return obj


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None, model: str | None = None):
        super().__init__(message)
        self.message = scrub(message)
        if code:
            self.code = code
        if status:
            self.status = status
        self.model = model

    def body(self) -> dict:
        d = {"error": {"code": self.code, "message": self.message}}
        if self.model:
            d["error"]["model"] = self.model
        return d


class NotFound(ApiError):
    status = 404
    code = "not_found"


class ModelUnavailable(ApiError):
    """A model's outputs/runtime are missing or unusable. The UI shows a clear 'not available' state."""

    status = 503
    code = "model_unavailable"


class TooManyRequests(ApiError):
    status = 429
    code = "rate_limited"


class QueueFull(ApiError):
    status = 429
    code = "queue_full"


class PayloadTooLarge(ApiError):
    status = 413
    code = "payload_too_large"
