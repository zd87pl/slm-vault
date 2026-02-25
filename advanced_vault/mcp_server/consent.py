"""
Consent Manager for Vault Access

Handles user consent for vault access requests from MCP clients.
Supports OS notifications, permission database, per-app consent,
per-document permissions, and time-limited access.
"""

import os
import json
import logging
import platform
import fnmatch
from pathlib import Path
from typing import Optional, Dict, List, Any, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


class ConsentDecision(Enum):
    """User consent decision."""
    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"
    DENY_ALWAYS = "deny_always"


class AccessScope(Enum):
    """Scope of access permission."""
    ALL = "all"  # Access to everything
    DOCUMENTS = "documents"  # Only document queries (agent_*)
    SECRETS = "secrets"  # Only secret access (vault_*)
    SPECIFIC = "specific"  # Specific documents/folders only


@dataclass
class AgentPermission:
    """
    Permission settings for a specific agent.

    Supports granular control:
    - Per-document permissions
    - Per-folder permissions
    - Tool restrictions
    - Time-limited access
    """
    agent_id: str
    auto_approve: bool = False
    denied: bool = False
    scope: AccessScope = field(default=AccessScope.ALL)
    allowed_documents: List[str] = field(default_factory=list)  # Document IDs or patterns
    allowed_folders: List[str] = field(default_factory=list)  # Folder paths (glob patterns)
    allowed_tools: List[str] = field(default_factory=list)  # Specific tool names
    denied_tools: List[str] = field(default_factory=list)  # Blocked tools
    expires_at: Optional[str] = None  # ISO timestamp for time-limited access
    max_queries_per_hour: Optional[int] = None  # Rate limiting
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_access: Optional[str] = None
    access_count: int = 0

    def is_expired(self) -> bool:
        """Check if permission has expired."""
        if self.expires_at is None:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.utcnow() > expiry
        except ValueError:
            return False

    def can_access_tool(self, tool_name: str) -> bool:
        """Check if this permission allows access to a specific tool."""
        # Check if tool is explicitly denied
        if tool_name in self.denied_tools:
            return False

        # If allowed_tools is specified, only those tools are allowed
        if self.allowed_tools:
            return tool_name in self.allowed_tools

        # Check scope-based access
        if self.scope == AccessScope.ALL:
            return True
        elif self.scope == AccessScope.DOCUMENTS:
            return tool_name.startswith("agent_")
        elif self.scope == AccessScope.SECRETS:
            return tool_name.startswith("vault_") or tool_name.startswith("langchain_")

        return True

    def can_access_document(self, document_path: str) -> bool:
        """Check if this permission allows access to a specific document."""
        if self.scope == AccessScope.SECRETS:
            return False

        if not self.allowed_documents and not self.allowed_folders:
            return True  # No restrictions

        # Check document patterns
        for pattern in self.allowed_documents:
            if fnmatch.fnmatch(document_path, pattern) or pattern in document_path:
                return True

        # Check folder patterns
        for folder in self.allowed_folders:
            if document_path.startswith(folder) or fnmatch.fnmatch(document_path, f"{folder}/*"):
                return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["scope"] = self.scope.value
        # Convert sets to lists for JSON serialization
        for key in ("allowed_tools", "denied_tools", "allowed_documents", "allowed_folders"):
            if isinstance(d.get(key), set):
                d[key] = sorted(d[key])
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPermission":
        """Create from dictionary."""
        data = data.copy()
        if "scope" in data:
            data["scope"] = AccessScope(data["scope"])
        # Convert lists back to sets for set-typed fields
        for key in ("allowed_tools", "denied_tools", "allowed_documents", "allowed_folders"):
            if isinstance(data.get(key), list):
                data[key] = set(data[key])
        return cls(**data)


class ConsentManager:
    """
    Manages user consent for vault access requests.
    
    Features:
    - OS notifications for access requests
    - Permission database for app-specific settings
    - Per-app consent tracking
    - "Always Allow" option
    """
    
    def __init__(self, vault_path: str = "~/.vault"):
        """
        Initialize consent manager.
        
        Args:
            vault_path: Base directory for vault storage
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        
        # Permission database path
        self.permissions_db_path = self.vault_path / "permissions.json"
        self.permissions: Dict[str, Dict] = {}
        
        # Load existing permissions
        self._load_permissions()
        
        logger.info(f"Initialized ConsentManager at {self.vault_path}")
    
    def _load_permissions(self):
        """Load permission database from disk."""
        if self.permissions_db_path.exists():
            try:
                with open(self.permissions_db_path, 'r') as f:
                    self.permissions = json.load(f)
                logger.info(f"Loaded {len(self.permissions)} app permissions")
            except Exception as e:
                logger.error(f"Failed to load permissions: {e}")
                self.permissions = {}
        else:
            self.permissions = {}
    
    def _save_permissions(self):
        """Save permission database to disk."""
        try:
            with open(self.permissions_db_path, 'w') as f:
                json.dump(self.permissions, f, indent=2)
            os.chmod(self.permissions_db_path, 0o600)  # Secure permissions
        except Exception as e:
            logger.error(f"Failed to save permissions: {e}")
    
    def _get_app_identifier(self) -> str:
        """
        Get identifier for the requesting app.
        
        Returns:
            App identifier (e.g., "claude-desktop", "cursor", "unknown")
        """
        # Try to detect from environment variables (MCP may set these)
        mcp_client = os.environ.get("MCP_CLIENT", "")
        parent_process = os.environ.get("PARENT_PROCESS", "")
        
        # Check MCP-specific environment variables first
        if mcp_client:
            mcp_lower = mcp_client.lower()
            if "claude" in mcp_lower:
                return "claude-desktop"
            elif "cursor" in mcp_lower:
                return "cursor"
            elif "vscode" in mcp_lower or "code" in mcp_lower:
                return "vscode"
        
        # Try to detect from parent process env var
        if parent_process:
            parent_lower = parent_process.lower()
            if "claude" in parent_lower:
                return "claude-desktop"
            elif "cursor" in parent_lower:
                return "cursor"
            elif "vs-code" in parent_lower or "code" in parent_lower:
                return "vscode"
        
        # Try to detect from process tree
        try:
            import psutil
            current = psutil.Process()
            parent = current.parent()
            if parent:
                parent_name = parent.name().lower()
                if "claude" in parent_name:
                    return "claude-desktop"
                elif "cursor" in parent_name:
                    return "cursor"
                elif "code" in parent_name:
                    return "vscode"
        except ImportError:
            pass
        except Exception:
            pass  # If psutil fails for any reason, fall through to unknown
        
        return "unknown"
    
    def _show_notification(self, app_name: str, tool_name: str, query_preview: str = "") -> Optional[ConsentDecision]:
        """
        Show OS notification requesting consent.
        
        Args:
            app_name: Name of the requesting app
            tool_name: MCP tool being called
            query_preview: Preview of the query (for recall operations)
        
        Returns:
            User's consent decision, or None if notification failed
        """
        system = platform.system()
        
        # Sanitize inputs to prevent injection in system dialogs
        safe_app_name = app_name.replace('"', '').replace("'", "").replace("\\", "")[:60]
        safe_tool = tool_name.replace('"', '').replace("'", "").replace("\\", "")[:40]

        title = f"{safe_app_name} wants to access your vault"
        message = f"Tool: {safe_tool}"
        if query_preview:
            preview = query_preview[:50].replace('"', "'").replace("\\", "") + ("..." if len(query_preview) > 50 else "")
            message += f"\nQuery: {preview}"

        try:
            if system == "Darwin":  # macOS
                import subprocess

                # Use AppleScript with osascript for interactive dialog
                # Escape double quotes for AppleScript string context
                safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
                safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
                script = f'''
                display dialog "{safe_msg}" buttons {{"Allow Once", "Always Allow", "Deny"}} default button 1 with title "{safe_title}" with icon caution
                set button to button returned of result
                '''
                
                try:
                    result = subprocess.run(
                        ["osascript", "-e", script],
                        capture_output=True,
                        text=True,
                        timeout=30  # 30 second timeout
                    )
                    
                    if result.returncode == 0:
                        output = result.stdout.strip()
                        if "Allow Once" in output:
                            return ConsentDecision.ALLOW_ONCE
                        elif "Always Allow" in output:
                            return ConsentDecision.ALLOW_ALWAYS
                        elif "Deny Always" in output:
                            return ConsentDecision.DENY_ALWAYS
                        elif "Deny" in output:
                            return ConsentDecision.DENY
                except subprocess.TimeoutExpired:
                    logger.warning("Notification dialog timed out")
                    return ConsentDecision.DENY
                except Exception as e:
                    logger.error(f"Failed to show macOS notification: {e}")
                    
            elif system == "Linux":
                # Try notify-send with zenity fallback
                try:
                    import subprocess
                    # Use zenity for interactive dialog
                    script = f'''
                    zenity --question --title "{title}" --text "{message}\\n\\nChoose an option:" --extra-button "Allow Once" --extra-button "Always Allow" --extra-button "Deny Always" --ok-label "Deny" --timeout=30
                    echo $?
                    '''
                    
                    result = subprocess.run(
                        ["bash", "-c", script],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    # Parse zenity output
                    if "Always Allow" in result.stdout:
                        return ConsentDecision.ALLOW_ALWAYS
                    elif "Allow Once" in result.stdout:
                        return ConsentDecision.ALLOW_ONCE
                    elif "Deny Always" in result.stdout:
                        return ConsentDecision.DENY_ALWAYS
                    else:
                        return ConsentDecision.DENY
                except Exception as e:
                    logger.error(f"Failed to show Linux notification: {e}")
                    
            elif system == "Windows":
                # Windows notifications
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    # Windows doesn't have interactive dialogs easily
                    # For now, show notification and default to deny
                    toaster.show_toast(title, message, duration=5)
                    logger.warning("Windows notification shown - defaulting to deny (interactive dialog not implemented)")
                    return ConsentDecision.DENY
                except ImportError:
                    logger.warning("win10toast not installed - cannot show Windows notifications")
                    return None
                except Exception as e:
                    logger.error(f"Failed to show Windows notification: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
        
        return None
    
    def request_consent(
        self,
        tool_name: str,
        query_preview: str = "",
        app_identifier: Optional[str] = None
    ) -> bool:
        """
        Request user consent for vault access.
        
        Args:
            tool_name: Name of the MCP tool being called
            query_preview: Preview of query (for recall operations)
            app_identifier: Optional app identifier (auto-detected if not provided)
        
        Returns:
            True if access is granted, False if denied
        """
        if app_identifier is None:
            app_identifier = self._get_app_identifier()
        
        app_name = app_identifier.replace("-", " ").title()
        
        # Check if app has "always allow" permission
        if app_identifier in self.permissions:
            app_perms = self.permissions[app_identifier]
            if app_perms.get("auto_approve", False):
                logger.info(f"Auto-approved for {app_identifier} (always allow)")
                return True
        
        # Check if app is explicitly denied (including deny_always)
        if app_identifier in self.permissions:
            app_perms = self.permissions[app_identifier]
            if app_perms.get("deny_always", False) or app_perms.get("denied", False):
                logger.info(f"Access denied for {app_identifier} (permanently denied)")
                return False
        
        # Try browser extension first (if available)
        decision = self._try_extension_consent(app_identifier, tool_name, query_preview)
        
        # Fallback to OS notification if extension not available
        if decision is None:
            decision = self._show_notification(app_name, tool_name, query_preview)
        
        if decision is None:
            # Notification failed - default to deny for security
            logger.warning("Notification failed - defaulting to deny")
            return False
        
        # Handle decision
        if decision == ConsentDecision.DENY:
            # Record one-time denial (no storage)
            logger.info(f"One-time denial for {app_identifier}")
            return False
        
        elif decision == ConsentDecision.DENY_ALWAYS:
            # Record permanent denial
            if app_identifier not in self.permissions:
                self.permissions[app_identifier] = {}
            self.permissions[app_identifier]["denied"] = True
            self.permissions[app_identifier]["deny_always"] = True
            self.permissions[app_identifier]["last_denied"] = datetime.now().isoformat()
            self._save_permissions()
            logger.info(f"Permanent denial set for {app_identifier}")
            return False
        
        elif decision == ConsentDecision.ALLOW_ALWAYS:
            # Grant and remember
            if app_identifier not in self.permissions:
                self.permissions[app_identifier] = {}
            self.permissions[app_identifier]["auto_approve"] = True
            self.permissions[app_identifier]["last_approved"] = datetime.now().isoformat()
            self._save_permissions()
            return True
        
        elif decision == ConsentDecision.ALLOW_ONCE:
            # Grant this time only
            logger.info(f"One-time access granted for {app_identifier}")
            return True
        
        return False
    
    def set_permission(self, app_identifier: str, auto_approve: bool):
        """
        Manually set permission for an app.
        
        Args:
            app_identifier: App identifier
            auto_approve: True to auto-approve, False to require consent
        """
        if app_identifier not in self.permissions:
            self.permissions[app_identifier] = {}
        
        self.permissions[app_identifier]["auto_approve"] = auto_approve
        self.permissions[app_identifier]["denied"] = False
        self.permissions[app_identifier]["last_updated"] = datetime.now().isoformat()
        self._save_permissions()
        logger.info(f"Set permission for {app_identifier}: auto_approve={auto_approve}")
    
    def get_permissions(self) -> Dict[str, Dict]:
        """Get all permissions."""
        return self.permissions.copy()

    def get_agent_permission(self, agent_id: str) -> Optional[AgentPermission]:
        """
        Get detailed permission for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentPermission object or None
        """
        if agent_id not in self.permissions:
            return None

        try:
            return AgentPermission.from_dict({
                "agent_id": agent_id,
                **self.permissions[agent_id]
            })
        except Exception as e:
            logger.warning(f"Failed to parse permission for {agent_id}: {e}")
            return None

    def set_agent_permission(self, permission: AgentPermission):
        """
        Set detailed permission for an agent.

        Args:
            permission: AgentPermission object
        """
        self.permissions[permission.agent_id] = permission.to_dict()
        del self.permissions[permission.agent_id]["agent_id"]  # Don't duplicate
        self._save_permissions()
        logger.info(f"Set agent permission for {permission.agent_id}: scope={permission.scope.value}")

    def set_document_access(
        self,
        agent_id: str,
        documents: Optional[List[str]] = None,
        folders: Optional[List[str]] = None
    ):
        """
        Set document access restrictions for an agent.

        Args:
            agent_id: Agent identifier
            documents: List of allowed document IDs or patterns
            folders: List of allowed folder paths
        """
        if agent_id not in self.permissions:
            self.permissions[agent_id] = {}

        if documents is not None:
            self.permissions[agent_id]["allowed_documents"] = documents
            self.permissions[agent_id]["scope"] = AccessScope.SPECIFIC.value

        if folders is not None:
            self.permissions[agent_id]["allowed_folders"] = folders
            self.permissions[agent_id]["scope"] = AccessScope.SPECIFIC.value

        self._save_permissions()
        logger.info(f"Set document access for {agent_id}: docs={documents}, folders={folders}")

    def set_tool_restrictions(
        self,
        agent_id: str,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None
    ):
        """
        Set tool restrictions for an agent.

        Args:
            agent_id: Agent identifier
            allowed_tools: List of allowed tool names (if set, only these are allowed)
            denied_tools: List of denied tool names
        """
        if agent_id not in self.permissions:
            self.permissions[agent_id] = {}

        if allowed_tools is not None:
            self.permissions[agent_id]["allowed_tools"] = allowed_tools

        if denied_tools is not None:
            self.permissions[agent_id]["denied_tools"] = denied_tools

        self._save_permissions()
        logger.info(f"Set tool restrictions for {agent_id}")

    def set_time_limited_access(
        self,
        agent_id: str,
        duration_hours: int = 24
    ):
        """
        Grant time-limited access to an agent.

        Args:
            agent_id: Agent identifier
            duration_hours: Hours until permission expires
        """
        if agent_id not in self.permissions:
            self.permissions[agent_id] = {}

        expires = datetime.utcnow() + timedelta(hours=duration_hours)
        self.permissions[agent_id]["auto_approve"] = True
        self.permissions[agent_id]["expires_at"] = expires.isoformat()
        self._save_permissions()
        logger.info(f"Set time-limited access for {agent_id}: {duration_hours}h")

    def check_permission(
        self,
        agent_id: str,
        tool_name: str,
        document_path: Optional[str] = None
    ) -> bool:
        """
        Check if an agent has permission for a specific access.

        Args:
            agent_id: Agent identifier
            tool_name: Tool being accessed
            document_path: Optional document being accessed

        Returns:
            True if access is allowed
        """
        perm = self.get_agent_permission(agent_id)

        if perm is None:
            return False  # No permission exists, require consent

        if perm.denied:
            return False

        if perm.is_expired():
            return False

        if not perm.can_access_tool(tool_name):
            return False

        if document_path and not perm.can_access_document(document_path):
            return False

        if perm.auto_approve:
            # Update access tracking
            self.permissions[agent_id]["last_access"] = datetime.utcnow().isoformat()
            self.permissions[agent_id]["access_count"] = perm.access_count + 1
            self._save_permissions()
            return True

        return False

    def revoke_permission(self, agent_id: str):
        """
        Revoke all permissions for an agent.

        Args:
            agent_id: Agent identifier
        """
        if agent_id in self.permissions:
            del self.permissions[agent_id]
            self._save_permissions()
            logger.info(f"Revoked permission for {agent_id}")

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all agents with permissions.

        Returns:
            List of agent info dicts
        """
        agents = []
        for agent_id, perms in self.permissions.items():
            try:
                perm = AgentPermission.from_dict({"agent_id": agent_id, **perms})
                agents.append({
                    "agent_id": agent_id,
                    "auto_approve": perm.auto_approve,
                    "denied": perm.denied,
                    "scope": perm.scope.value,
                    "expired": perm.is_expired(),
                    "expires_at": perm.expires_at,
                    "last_access": perm.last_access,
                    "access_count": perm.access_count
                })
            except Exception:
                agents.append({
                    "agent_id": agent_id,
                    "auto_approve": perms.get("auto_approve", False),
                    "denied": perms.get("denied", False)
                })
        return agents

    def _try_extension_consent(
        self,
        app_identifier: str,
        tool_name: str,
        query_preview: str = ""
    ) -> Optional[ConsentDecision]:
        """
        Try to get consent via browser extension.
        
        Uses native messaging host to communicate with extension.
        Returns None if extension not available (falls back to OS notifications).
        """
        try:
            import json
            import subprocess
            import platform
            import os
            
            # Check if native messaging host is available
            # Native messaging host is a small executable that bridges MCP server and extension
            # For POC, we'll check if extension is installed and use a simple approach
            
            # Try to use native messaging host if available
            # The host executable should be at:
            # macOS: ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.enclave.vault.json
            # Linux: ~/.config/google-chrome/NativeMessagingHosts/com.enclave.vault.json
            # Windows: Registry or similar location
            
            if platform.system() == "Darwin":
                host_config_path = Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts/com.enclave.vault.json"
            elif platform.system() == "Linux":
                host_config_path = Path.home() / ".config/google-chrome/NativeMessagingHosts/com.enclave.vault.json"
            else:
                # Windows - would use registry
                host_config_path = None
            
            # For now, extension consent is handled via message passing
            # MCP server can check extension availability, but for POC we'll use OS notifications
            # Future: Implement native messaging host executable
            
            # Check if we can detect extension via environment variable or config
            # This is a placeholder - actual implementation would use native messaging host
            
            logger.debug("Extension consent check: Native messaging host not yet implemented, using OS notifications")
            return None
            
        except Exception as e:
            logger.debug(f"Extension consent not available: {e}")
            return None


