"""Personal Vault GUI - Flet application."""

try:
    from .vault_app import main
    __all__ = ['main']
except ImportError:
    # Flet not installed — submodules still importable directly
    __all__ = []
