"""Small persistent storage helpers for Data Sheriff."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class JSONFileStore:
    """Thread-safe JSON file store for small local metadata collections."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def load(self, default: Any) -> Any:
        """Load JSON content or return provided default."""
        with self._lock:
            if not self.path.exists():
                return default
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return default

    def save(self, value: Any) -> None:
        """Persist JSON content atomically."""
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(value, indent=2, default=str))
            tmp.replace(self.path)
