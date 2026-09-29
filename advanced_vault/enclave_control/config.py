"""Human-editable TOML config loader for the shared Enclave policy plane."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import errno
import json
import logging
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Dict, Tuple
import tomllib

from .legacy_defaults import LEGACY_DEFAULT_POLICY_TOMLS
from .models import AgentPolicy, KillSwitchState, utcnow_iso

logger = logging.getLogger(__name__)

# MCP tools that read, store or delete entries of the secrets store (API keys,
# passwords, notes). The `default` entry -- what every MCP client Enclave
# cannot identify gets -- must not allow any of them; `enclave doctor` warns
# when it does.
SECRETS_TOOLS = ("vault_store", "vault_recall", "vault_list_entries", "vault_delete", "vault_stats")

DEFAULT_POLICY_TOML = """# Enclave control-plane policy configuration
# This file is human-editable and acts as the source of truth for shared Vault + Wallet policy.

[kill_switch]
enabled = false
reason = ""
updated_at = ""

# `default` is what every app Enclave cannot identify gets -- on a default
# install, every MCP client. It allows only the document Q&A tools. Do not add
# vault_* (your stored secrets) here: to let one app use them, add them to
# that app's own entry instead (README: "Letting one app use the secrets tools").
[[agents]]
agent_id = "default"
trust_level = "standard"
allowed_modules = ["vault"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status"]
vault_scopes = ["*"]
wallet_scopes = []
wallet_auto_approve_below = 0.0
wallet_prompt_above = 0.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "local-ui"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "vault-cli"
trust_level = "operator"
allowed_modules = ["vault", "wallet", "security"]
allowed_tools = ["*"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 100.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "claude-desktop"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "cursor"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23

[[agents]]
agent_id = "openclaw"
trust_level = "brokered"
allowed_modules = ["vault", "wallet"]
allowed_tools = ["agent_*", "query_knowledge", "agent_status", "check_budget", "list_envelopes", "request_purchase", "get_transactions"]
vault_scopes = ["*"]
wallet_scopes = ["*"]
wallet_auto_approve_below = 25.0
wallet_prompt_above = 25.0
start_hour = 0
end_hour = 23
"""


@dataclass
class EnclavePolicyDocument:
    """Parsed policy document from the operator-facing TOML config."""

    kill_switch: KillSwitchState
    agents: Dict[str, AgentPolicy]


def parse_policy_document(text: str) -> EnclavePolicyDocument:
    """Parse policy TOML text into strongly-typed runtime structures."""
    payload = tomllib.loads(text)
    kill_switch_payload = dict(payload.get("kill_switch", {}))
    kill_switch = KillSwitchState(
        enabled=bool(kill_switch_payload.get("enabled", False)),
        reason=str(kill_switch_payload.get("reason", "")),
        updated_at=str(kill_switch_payload.get("updated_at") or utcnow_iso()),
    )

    agents: Dict[str, AgentPolicy] = {}
    for raw_agent in payload.get("agents", []):
        policy = AgentPolicy(
            agent_id=str(raw_agent.get("agent_id", "default")),
            trust_level=str(raw_agent.get("trust_level", "standard")),
            allowed_modules=list(raw_agent.get("allowed_modules", ["vault"])),
            allowed_tools=list(raw_agent.get("allowed_tools", ["*"])),
            vault_scopes=list(raw_agent.get("vault_scopes", ["*"])),
            wallet_scopes=list(raw_agent.get("wallet_scopes", ["*"])),
            wallet_auto_approve_below=float(raw_agent.get("wallet_auto_approve_below", 25.0)),
            wallet_prompt_above=float(raw_agent.get("wallet_prompt_above", 100.0)),
            start_hour=int(raw_agent.get("start_hour", 0)),
            end_hour=int(raw_agent.get("end_hour", 23)),
            metadata=dict(raw_agent.get("metadata", {})),
        )
        agents[policy.agent_id] = policy

    if "default" not in agents:
        agents["default"] = AgentPolicy(agent_id="default")
    return EnclavePolicyDocument(kill_switch=kill_switch, agents=agents)


# --- Replacing an unmodified default written by an earlier Enclave ---------

# A [kill_switch] value line exactly as save_kill_switch() writes it. The app
# rewrites these whenever the kill switch is toggled; they are state, not an
# edit to the policy.
_KILL_SWITCH_LINE = re.compile(r'(enabled) = (?:true|false)|(reason|updated_at) = "(?:[^"\\]|\\.)*"')


def _comparable_policy_text(text: str) -> str:
    """``text`` without the differences that are not edits to the policy.

    Those are line endings (Python's text mode writes \\r\\n on Windows),
    trailing spaces and tabs, blank lines at either end, and the kill-switch
    values. None of the whitespace is significant in TOML outside multi-line
    strings, and a file that matches a shipped default line for line cannot
    contain one, because the shipped defaults have none. Indentation, comments
    and every other value still count.
    """
    lines = []
    in_kill_switch = False
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.rstrip(" \t")
        if line.startswith("["):
            in_kill_switch = line == "[kill_switch]"
        elif in_kill_switch:
            match = _KILL_SWITCH_LINE.fullmatch(line)
            if match:
                line = f"{match.group(1) or match.group(2)} = <kill switch state>"
        lines.append(line)
    return "\n".join(lines).strip("\n")


_LEGACY_DEFAULTS_COMPARABLE = frozenset(_comparable_policy_text(text) for text in LEGACY_DEFAULT_POLICY_TOMLS)


def upgrade_legacy_default(text: str) -> str | None:
    """Return the current default to replace ``text`` with, if ``text`` is an old default.

    Every default policy shipped before this one gave the ``vault_*`` secrets
    tools to all apps Enclave cannot identify. A file that still matches one of
    them (see ``_comparable_policy_text``) was never edited, so nobody chose
    that; the result keeps its kill-switch state. Returns None for any file the
    user edited, and for the current default.
    """
    if _comparable_policy_text(text) not in _LEGACY_DEFAULTS_COMPARABLE:
        return None
    try:
        kill_switch = tomllib.loads(text)["kill_switch"]
    except (tomllib.TOMLDecodeError, KeyError):  # e.g. an invalid escape in the reason
        return None
    state = KillSwitchState(
        enabled=kill_switch["enabled"],
        reason=kill_switch["reason"],
        updated_at=kill_switch["updated_at"],
    )
    return _with_kill_switch(DEFAULT_POLICY_TOML, state)


class _PolicyFileChanged(Exception):
    """The policy file changed on disk while it was being replaced."""


def _backup_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _write_backup(path: Path, data: bytes, mode: int) -> Path:
    """Write ``data`` to a new timestamped sibling of ``path`` and return its path.

    The backup is created exclusively (O_EXCL never follows a symlink or
    overwrites a file planted at the predictable name) and with ``mode``.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    stamp = _backup_stamp()
    for counter in range(1000):
        suffix = f"{stamp}-{counter}" if counter else stamp
        backup = path.with_name(f"{path.name}.bak-{suffix}")
        try:
            fd = os.open(backup, flags, mode)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError(f"no free backup name for {path}")
    try:
        with os.fdopen(fd, "wb") as f:
            if hasattr(os, "fchmod"):
                os.fchmod(f.fileno(), mode)  # os.open applied the umask
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(backup)
        raise
    return backup


def _write_temp_sibling(path: Path, data: bytes, mode: int) -> str:
    """Write ``data`` to a new temporary file next to ``path`` and return its name."""
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            if hasattr(os, "fchmod"):
                os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return tmp_name


def _universal_newlines(text: str) -> str:
    """What ``Path.read_text`` returns for the same file."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _with_kill_switch(document: str, state: KillSwitchState) -> str:
    """Return ``document`` with its [kill_switch] values set to ``state``, other lines unchanged."""
    lines = document.splitlines()
    new_lines = []
    in_block = False
    replaced_enabled = False
    replaced_reason = False
    replaced_updated_at = False
    reason_value = json.dumps(state.reason)
    updated_value = json.dumps(state.updated_at)

    for line in lines:
        stripped = line.strip()
        if stripped == "[kill_switch]":
            in_block = True
            new_lines.append(line)
            continue
        if in_block and stripped.startswith("[") and stripped != "[kill_switch]":
            if not replaced_enabled:
                new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
                replaced_enabled = True
            if not replaced_reason:
                new_lines.append(f"reason = {reason_value}")
                replaced_reason = True
            if not replaced_updated_at:
                new_lines.append(f"updated_at = {updated_value}")
                replaced_updated_at = True
            in_block = False

        if in_block and stripped.startswith("enabled ="):
            new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
            replaced_enabled = True
            continue
        if in_block and stripped.startswith("reason ="):
            new_lines.append(f"reason = {reason_value}")
            replaced_reason = True
            continue
        if in_block and stripped.startswith("updated_at ="):
            new_lines.append(f"updated_at = {updated_value}")
            replaced_updated_at = True
            continue

        new_lines.append(line)

    if in_block:
        if not replaced_enabled:
            new_lines.append(f"enabled = {'true' if state.enabled else 'false'}")
        if not replaced_reason:
            new_lines.append(f"reason = {reason_value}")
        if not replaced_updated_at:
            new_lines.append(f"updated_at = {updated_value}")

    return "\n".join(new_lines) + "\n"


class EnclavePolicyConfig:
    """Load and persist `~/.enclave/policies.toml`."""

    def __init__(self, path: str = "~/.enclave/policies.toml"):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_exists()

    def ensure_exists(self) -> None:
        """Create a sensible default policy file when missing."""
        if self.path.exists():
            return
        self.path.write_text(DEFAULT_POLICY_TOML, encoding="utf-8")

    def load(self) -> EnclavePolicyDocument:
        """Parse the TOML file into strongly-typed runtime structures.

        A file that is still an unmodified default from an earlier Enclave is
        replaced by the current default first (see ``upgrade_legacy_default``).
        """
        return parse_policy_document(self._read_policy_text())

    def _read_policy_text(self) -> str:
        """Return the policy text to enforce, upgrading an unmodified old default on disk.

        The old file is kept as a timestamped ``.bak-`` sibling. If it cannot
        be replaced, the current default is still what gets enforced: an old
        default was never the user's choice, so failing closed costs nothing
        the user asked for. A file the user edited is returned as it is.
        """
        for _attempt in range(3):
            raw = self.path.read_bytes()
            text = _universal_newlines(raw.decode("utf-8"))
            upgraded = upgrade_legacy_default(text)
            if upgraded is None:
                return text
            try:
                backup = self._replace_legacy_default(raw, upgraded)
            except _PolicyFileChanged:
                continue  # an edit landed meanwhile; look at the file again
            except OSError as exc:
                logger.warning(
                    "%s is an unmodified default policy from an older Enclave, which let "
                    "every app Enclave cannot identify use the vault_* secrets tools. It "
                    "could not be replaced (%s), so the current default is enforced instead "
                    "without changing the file.",
                    self.path, exc,
                )
            else:
                logger.warning(
                    "Replaced %s, an unmodified default policy from an older Enclave that let "
                    "every app Enclave cannot identify use the vault_* secrets tools, with the "
                    "current default. The old file is saved as %s.",
                    self.path, backup,
                )
            return upgraded
        return upgraded  # still an old default after repeated concurrent changes

    def _replace_legacy_default(self, original: bytes, upgraded: str) -> Path:
        """Back up the file (``original``), then atomically replace it with ``upgraded``.

        Returns the backup's path. Raises _PolicyFileChanged, leaving nothing
        behind, if the file no longer holds ``original`` just before the swap.
        """
        target = self.path
        if target.is_symlink():
            # Update the file a (dotfiles-style) symlink points at, not the link.
            target = Path(os.path.realpath(target))
        # os.replace would bypass a read-only file's permissions; honour them.
        if not os.access(target, os.W_OK):
            raise PermissionError(errno.EACCES, "the file is not writable", str(target))
        mode = stat.S_IMODE(target.stat().st_mode)

        backup = _write_backup(target, original, mode)
        tmp_name = None
        try:
            tmp_name = _write_temp_sibling(target, upgraded.encode("utf-8"), mode)
            if target.read_bytes() != original:
                raise _PolicyFileChanged(str(target))
            os.replace(tmp_name, target)
        except BaseException:
            for leftover in (tmp_name, backup):
                if leftover is not None:
                    with contextlib.suppress(OSError):
                        os.unlink(leftover)
            raise
        return backup

    def save_kill_switch(self, state: KillSwitchState) -> None:
        """Persist kill-switch state while leaving the rest of the file intact."""
        document = self.path.read_text(encoding="utf-8")
        self.path.write_text(_with_kill_switch(document, state), encoding="utf-8")
