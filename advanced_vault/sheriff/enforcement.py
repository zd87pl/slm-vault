"""System enforcement abstraction for Data Sheriff."""

from __future__ import annotations

import platform
from dataclasses import dataclass


@dataclass
class EnforcementStatus:
    """Operational status of enforcement layer."""

    backend: str
    enabled: bool
    mode: str
    message: str


class EnforcementLayer:
    """
    Abstraction over OS-level enforcement.

    In this repository we provide a production-oriented stub that reports
    readiness and mode. Full EndpointSecurity integration is expected as
    a dedicated native component in Milestone B.
    """

    def __init__(self):
        self._status = self._detect()

    def _detect(self) -> EnforcementStatus:
        if platform.system() == "Darwin":
            return EnforcementStatus(
                backend="macos-stub",
                enabled=False,
                mode="simulate",
                message="System-level enforcement stub active; EndpointSecurity agent not installed.",
            )
        return EnforcementStatus(
            backend="unsupported",
            enabled=False,
            mode="simulate",
            message="System-level enforcement currently targeted at macOS only.",
        )

    def status(self) -> EnforcementStatus:
        """Return backend status."""
        return self._status
