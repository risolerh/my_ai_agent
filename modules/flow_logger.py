import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class JsonLineFormatter(logging.Formatter):
    """Formatter that emits one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
        }

        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["message"] = record.getMessage()

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class FlowLogger(logging.LoggerAdapter):
    """Logger adapter with context binding and event helper."""

    def bind(self, **kwargs: Any) -> "FlowLogger":
        merged = dict(self.extra)
        merged.update(kwargs)
        return FlowLogger(self.logger, merged)

    def event(self, event: str, level: int = logging.INFO, **fields: Any) -> None:
        payload = {"event": event}
        payload.update(self.extra)
        payload.update(fields)
        self.logger.log(level, payload)


_CONFIGURED = False


def setup_flow_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger = logging.getLogger("flow")
    logger.handlers = []
    logger.propagate = False

    if _env_flag("FLOW_LOG_DISABLED", default=False):
        logger.disabled = True
        _CONFIGURED = True
        return

    level_name = os.getenv("FLOW_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)

    _CONFIGURED = True


def get_flow_logger(component: str, **context: Any) -> FlowLogger:
    setup_flow_logging()
    base_logger = logging.getLogger(f"flow.{component}")
    context = {"component": component, **context}
    return FlowLogger(base_logger, context)
