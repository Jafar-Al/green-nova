"""Structured JSON-lines logging to a file under the runtime logs dir (never to clients, never with request bodies or full paths)."""
from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path

from .errors import scrub


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "gn", None)
        if isinstance(extra, dict):
            d.update(extra)
        if record.exc_info:
            # stack traces stay in the log file only
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False, default=str)


def setup_logging(logs_dir: Path) -> logging.Logger:
    logger = logging.getLogger("greennova")
    if getattr(logger, "_gn_ready", False):
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        h: logging.Handler = logging.handlers.RotatingFileHandler(logs_dir / "backend.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    except OSError:
        h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logger.addHandler(h)
    logger._gn_ready = True  # type: ignore[attr-defined]
    return logger


def log(logger: logging.Logger, level: int, msg: str, **fields) -> None:
    logger.log(level, scrub(msg), extra={"gn": {k: (scrub(v) if isinstance(v, str) else v) for k, v in fields.items()}})
