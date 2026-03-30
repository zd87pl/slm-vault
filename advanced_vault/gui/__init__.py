"""Personal Vault GUI package."""

__all__ = ["main"]


def main(*args, **kwargs):
    """Lazily resolve the Flet entry point without importing the whole app on package import."""
    from .vault_app import main as vault_main

    return vault_main(*args, **kwargs)
