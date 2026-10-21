"""Structured logging with a per-request correlation id.

Every log line carries the request id of the HTTP request that produced it,
so one optimisation can be traced end-to-end with a single grep / log query.
"""
import json
import logging
import logging.handlers
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes every LogRecord has; anything else was passed via `extra=` and is logged as a field.
_STD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "color_message"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in vars(record).items():
            if key not in _STD_ATTRS and key != "request_id":
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, fmt: str, log_file: str | None = None) -> None:
    formatter: logging.Formatter
    if fmt == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.handlers.RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        root.addHandler(handler)

    # Our middleware writes one access line per request; silence uvicorn's duplicate.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # numba/shap are chatty at DEBUG
    logging.getLogger("numba").setLevel(logging.WARNING)
