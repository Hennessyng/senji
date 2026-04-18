import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "level": record.levelname,
                "module": record.name,
                "msg": record.getMessage(),
                "ts": datetime.now(timezone.utc).isoformat(),
                "exc": self.formatException(record.exc_info) if record.exc_info else None,
            }
        )


def setup_logging(level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger("senji")
    root.setLevel(level)
    root.addHandler(handler)
    return root
