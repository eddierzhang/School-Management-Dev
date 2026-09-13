"""Logs and error reporting, the same way in the API and the worker.

`HR_LOG_FORMAT=json` writes one JSON object per line for a log collector. Log
lines name routes by their template (`/api/students/{sid}`), never the filled-in
path, so a student's ID does not end up in a log system that was never meant to
hold student records. The audit log is where that belongs.

`HR_SENTRY_DSN` sends unhandled errors to Sentry with personal data turned off.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from .config import get_settings

RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        out.update({k: v for k, v in record.__dict__.items() if k not in RESERVED and not k.startswith("_")})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure(service: str) -> None:
    s = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    if s.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(f"%(asctime)s %(levelname)-5s [{service}] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(s.log_level.upper())
    logging.getLogger("uvicorn.access").disabled = True     # replaced by the route-template access log
    logging.getLogger("alembic").setLevel(logging.WARNING)   # the readiness check consults it on every call

    if s.sentry_dsn:
        try:
            import sentry_sdk
        except ImportError:
            logging.getLogger("halverson").warning("HR_SENTRY_DSN is set but sentry-sdk is not installed.")
            return
        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.app_env, send_default_pii=False,
                        max_request_body_size="never", traces_sample_rate=0.0, server_name=service)
