"""
Activity Logger for MCP Server Access

Logs all vault access attempts from MCP clients for visibility in the GUI.
Provides search, filtering, and export capabilities for audit and compliance.

Each access event is persisted as a single JSON line in ``activity.jsonl``
inside the vault directory, enabling simple append-only writes and easy
streaming reads.
"""

import csv
import io
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from advanced_vault.enclave_control import EnclaveRuntime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Suffix appended to display names for requests arriving via MCP.
_MCP_DISPLAY_SUFFIX = "via Enclave MCP"

#: Default upper bound when bulk-reading activity entries (e.g. for export).
_BULK_READ_LIMIT = 500

#: Name of the JSONL activity log file stored inside the vault directory.
_ACTIVITY_LOG_FILENAME = "activity.jsonl"

#: Human-readable names for known MCP client identifiers.
_APP_DISPLAY_NAMES: Dict[str, str] = {
    "claude-desktop": f"Claude {_MCP_DISPLAY_SUFFIX}",
    "claude": f"Claude {_MCP_DISPLAY_SUFFIX}",
    "cursor": f"Cursor {_MCP_DISPLAY_SUFFIX}",
    "vscode": f"VS Code {_MCP_DISPLAY_SUFFIX}",
    "unknown": f"Unknown {_MCP_DISPLAY_SUFFIX}",
}

#: Fallback display name when no better match is found.
_DEFAULT_APP_DISPLAY_NAME = f"Claude {_MCP_DISPLAY_SUFFIX}"

#: Words that mark an argument as sensitive when they make up its name or one
#: of its ``_``/``-``/camelCase-separated parts, singular or plural (e.g.
#: ``api_key``, ``accessToken``, ``secrets``).
_SENSITIVE_ARGUMENT_WORDS = frozenset({
    "value", "secret", "password", "passwd", "passphrase", "pwd",
    "token", "key", "apikey", "credential", "credentials",
    "auth", "authorization", "bearer", "cookie",
})

#: Endings that mark a joined, lower-case name as sensitive (``apitoken``,
#: ``clientsecret``, ``privatekey``).
_SENSITIVE_ARGUMENT_SUFFIXES = ("token", "secret", "password", "passwd", "key")

#: Names that contain a sensitive word but carry no secret material.
_NON_SENSITIVE_ARGUMENT_NAMES = frozenset({"max_tokens"})

#: Tool arguments that carry secret material under a generic name.
_SENSITIVE_TOOL_ARGUMENTS: Dict[str, frozenset] = {
    "vault_store": frozenset({"content"}),
}


def redact_tool_arguments(tool_name: str, arguments: Any) -> Dict[str, Any]:
    """
    Return an audit-safe copy of MCP tool arguments.

    Argument names are kept so the audit trail shows what was requested, but
    the values of sensitive arguments (the ``content`` of vault_store, or any
    argument named like a value, secret, password, token or key, at any
    nesting depth) are replaced by a marker with their length. Use this
    wherever tool arguments are persisted.

    Args:
        tool_name: MCP tool name (e.g., "vault_store")
        arguments: Tool arguments as received from the client

    Returns:
        Redacted copy of the arguments (the input is not modified)
    """
    if not isinstance(arguments, Mapping):
        return {"_redacted": type(arguments).__name__}
    return _redact_mapping(tool_name, arguments)


def _redact_mapping(tool_name: str, mapping: Mapping) -> Dict[str, Any]:
    return {
        name: (
            _redaction_marker(value)
            if _is_sensitive_argument(tool_name, name)
            else _redact_value(tool_name, value)
        )
        for name, value in mapping.items()
    }


def _redact_value(tool_name: str, value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(tool_name, value)
    if isinstance(value, (list, tuple)):
        return [_redact_value(tool_name, item) for item in value]
    return value


def _is_sensitive_argument(tool_name: str, name: Any) -> bool:
    name = str(name)
    lowered = name.lower()
    if lowered in _SENSITIVE_TOOL_ARGUMENTS.get(tool_name, frozenset()):
        return True
    if lowered in _NON_SENSITIVE_ARGUMENT_NAMES:
        return False
    # Split snake/kebab/camelCase, keeping acronyms whole ("APIToken" -> api, token)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spaced).lower()
    for word in re.split(r"[^a-z0-9]+", spaced):
        singular = word[:-1] if len(word) > 3 and word.endswith("s") else word
        if singular in _SENSITIVE_ARGUMENT_WORDS or singular.endswith(_SENSITIVE_ARGUMENT_SUFFIXES):
            return True
    return False


def _redaction_marker(value: Any) -> str:
    if isinstance(value, str):
        return f"[redacted: {len(value)} chars]"
    return "[redacted]"


class ActivityLogger:
    """Logs vault access activity for GUI visibility."""
    
    def __init__(self, vault_path: str = "~/.vault", runtime: Optional[EnclaveRuntime] = None):
        """
        Initialize activity logger.
        
        Args:
            vault_path: Base directory for vault storage
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.runtime = runtime or EnclaveRuntime(vault_path=str(self.vault_path))
        
        # Activity log file
        self.activity_log_path = self.vault_path / _ACTIVITY_LOG_FILENAME
        
        logger.info(f"Initialized ActivityLogger at {self.vault_path}")
    
    def log_access(
        self,
        tool_name: str,
        app_identifier: str,
        query_preview: str = "",
        granted: bool = True,
        result_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log vault access attempt.
        
        Args:
            tool_name: MCP tool name (e.g., "vault_recall")
            app_identifier: App identifier (e.g., "claude-desktop")
            query_preview: Preview of query/operation
            granted: Whether access was granted
            result_summary: Brief summary of result (e.g., "Found 4 entries")
            metadata: Additional metadata (sensitive values are redacted
                with redact_tool_arguments before anything is written)
        """
        # Generate friendly app name
        app_name = self._format_app_name(app_identifier)

        # Never persist sensitive values, e.g. tool arguments passed as metadata
        metadata = redact_tool_arguments(tool_name, metadata or {})

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "app_identifier": app_identifier,
            "app_name": app_name,
            "query_preview": query_preview,
            "granted": granted,
            "result_summary": result_summary,
            "metadata": metadata
        }
        
        try:
            # Append to JSONL file
            with open(self.activity_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')

            self.runtime.log_event(
                subject=app_identifier,
                module=self._module_for_tool(tool_name),
                tool=tool_name,
                decision="ALLOW" if granted else "DENY",
                resource=query_preview,
                summary=result_summary or query_preview,
                metadata={
                    "app_name": app_name,
                    "granted": granted,
                    **metadata,
                },
                source="activity_logger",
            )
            
            logger.debug(f"Logged activity: {tool_name} from {app_identifier}")
        except OSError as e:
            logger.error(f"Failed to log activity: {e}")

    def _module_for_tool(self, tool_name: str) -> str:
        """Map tool names into shared control-plane modules."""
        if tool_name.startswith(("sheriff_", "sheriff.")):
            return "security"
        if tool_name in {
            "check_budget",
            "list_envelopes",
            "request_purchase",
            "approve_purchase",
            "get_transactions",
            "create_envelope",
            "freeze_all",
            "unfreeze_all",
        }:
            return "wallet"
        return "vault"
    
    def _format_app_name(self, app_identifier: str) -> str:
        """
        Format app identifier into a friendly display name.
        
        Args:
            app_identifier: App identifier (e.g., "claude-desktop", "unknown", etc.)
            
        Returns:
            Friendly app name (e.g., "Claude via Enclave MCP", "Cursor", etc.)
        """
        # Check for exact match first
        if app_identifier.lower() in _APP_DISPLAY_NAMES:
            return _APP_DISPLAY_NAMES[app_identifier.lower()]

        # Check for partial matches (e.g., "claude" in "claude-desktop")
        app_lower = app_identifier.lower()
        for key, value in _APP_DISPLAY_NAMES.items():
            if key in app_lower or app_lower in key:
                return value

        # Default: format as title case and add MCP suffix if it's an MCP request
        # (Since this logger is only used by MCP server, all requests are via MCP)
        formatted = app_identifier.replace("-", " ").replace("_", " ").title()
        if formatted.lower() not in ["unknown", "none", ""]:
            return f"{formatted} {_MCP_DISPLAY_SUFFIX}"
        else:
            return _DEFAULT_APP_DISPLAY_NAME
    
    def get_recent_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent activity entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of activity entries (most recent first)
        """
        if not self.activity_log_path.exists():
            return []
        
        try:
            entries = []
            with open(self.activity_log_path, 'r') as f:
                lines = f.readlines()
                # Read last N lines (most recent)
                for line in lines[-limit:]:
                    try:
                        entry = json.loads(line.strip())
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
            
            # Sort by timestamp (most recent first)
            entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return entries[:limit]
        except OSError as e:
            logger.error(f"Failed to read activity log: {e}")
            return []
    
    def search_activity(
        self,
        query: str = "",
        tool_filter: str = "",
        granted_filter: Optional[bool] = None,
        days: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search and filter activity entries.

        Args:
            query: Text to search for in tool_name, app_name, query_preview
            tool_filter: Filter by specific tool name
            granted_filter: Filter by granted status (True/False/None for all)
            days: Filter to last N days (None for all)
            limit: Maximum results to return

        Returns:
            Filtered list of activity entries (most recent first)
        """
        activities = self.get_recent_activity(limit=_BULK_READ_LIMIT)
        filtered = []

        cutoff = None
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        for a in activities:
            if query:
                searchable = json.dumps(a).lower()
                if query.lower() not in searchable:
                    continue
            if tool_filter and a.get("tool_name") != tool_filter:
                continue
            if granted_filter is not None and a.get("granted") != granted_filter:
                continue
            if cutoff and a.get("timestamp", "") < cutoff:
                continue
            filtered.append(a)
            if len(filtered) >= limit:
                break

        return filtered

    def export_csv(self, activities: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Export activities to CSV format.

        Args:
            activities: List of activities to export. If None, exports recent.

        Returns:
            CSV string
        """
        if activities is None:
            activities = self.get_recent_activity(limit=_BULK_READ_LIMIT)

        output = io.StringIO()
        fieldnames = [
            "timestamp", "tool_name", "app_name",
            "query_preview", "granted", "result_summary"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for a in activities:
            writer.writerow(a)
        return output.getvalue()

    def export_json(self, activities: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Export activities to JSON format.

        Args:
            activities: List of activities to export. If None, exports recent.

        Returns:
            JSON string
        """
        if activities is None:
            activities = self.get_recent_activity(limit=_BULK_READ_LIMIT)
        return json.dumps(activities, indent=2)

    def clear_activity(self) -> None:
        """Clear activity log."""
        try:
            if self.activity_log_path.exists():
                self.activity_log_path.unlink()
            logger.info("Cleared activity log")
        except OSError as e:
            logger.error(f"Failed to clear activity log: {e}")
