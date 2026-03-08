"""Gateway model for Häfele Connect Mesh."""

from dataclasses import dataclass
from typing import Any

from ..exceptions import ValidationError


@dataclass
class Gateway:
    """Represents a Häfele Connect Mesh gateway."""

    id: str
    network_id: str
    firmware: str
    connected: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Gateway":
        """Create a Gateway instance from dictionary data."""
        try:
            return cls(
                id=data["id"],
                network_id=data["networkId"],
                firmware=data["firmware"],
                connected=data["connected"],
            )
        except KeyError as e:
            raise ValidationError(f"Invalid gateway data: {e!s}")
