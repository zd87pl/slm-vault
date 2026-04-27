"""Named route constants for Enclave navigation."""

from enum import IntEnum


class Route(IntEnum):
    """Sequential sidebar indices: 0=Chat, 1=Vaults, 2=Files, 3=Settings."""

    CHAT = 0
    VAULTS = 1
    FILES = 2
    SETTINGS = 3
    NONE = -1  # For views not in the sidebar (e.g., Connections)
