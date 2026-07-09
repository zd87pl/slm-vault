"""Data models for Private Language Model profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

UTC = timezone.utc  # datetime.UTC alias needs 3.11+; project supports 3.10


DEFAULT_SYSTEM_PROMPT = (
    "You are Enclave, a private local language model. "
    "Answer from the user's local context when it is available. "
    "Do not expose large raw passages. Prefer concise synthesis and cite document names."
)


@dataclass
class WDVAAdapterReference:
    """A WDVA adapter attached to a Private Language Model profile."""

    name: str
    encrypted_path: str
    key_path: str
    weight: float = 1.0
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "WDVAAdapterReference":
        """Deserialize from a dictionary."""
        return cls(
            name=payload["name"],
            encrypted_path=payload["encrypted_path"],
            key_path=payload["key_path"],
            weight=float(payload.get("weight", 1.0)),
            description=payload.get("description", ""),
            keywords=list(payload.get("keywords", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class PrivateModelProfile:
    """Configuration for a local Private Language Model."""

    name: str
    description: str = ""
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    keywords: List[str] = field(default_factory=list)
    model_name: Optional[str] = None
    wdva_adapters: List[WDVAAdapterReference] = field(default_factory=list)
    schema_version: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        """Update the timestamp after mutation."""
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize profile configuration."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "keywords": self.keywords,
            "model_name": self.model_name,
            "wdva_adapters": [adapter.to_dict() for adapter in self.wdva_adapters],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PrivateModelProfile":
        """Deserialize profile configuration."""
        return cls(
            name=payload["name"],
            description=payload.get("description", ""),
            system_prompt=payload.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
            keywords=list(payload.get("keywords", [])),
            model_name=payload.get("model_name"),
            wdva_adapters=[
                WDVAAdapterReference.from_dict(item)
                for item in payload.get("wdva_adapters", [])
            ],
            schema_version=int(payload.get("schema_version", 1)),
            created_at=payload.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=payload.get("updated_at", datetime.now(UTC).isoformat()),
        )
