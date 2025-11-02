"""
Consent Manager for Vault Access

Handles user consent for vault access requests from MCP clients.
Supports OS notifications, permission database, and per-app consent.
"""

import os
import json
import logging
import platform
from pathlib import Path
from typing import Optional, Dict, Literal
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ConsentDecision(Enum):
    """User consent decision."""
    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"


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
        # Try to detect from environment
        parent_process = os.environ.get("PARENT_PROCESS", "")
        
        if "claude" in parent_process.lower():
            return "claude-desktop"
        elif "cursor" in parent_process.lower():
            return "cursor"
        elif "vs-code" in parent_process.lower() or "code" in parent_process.lower():
            return "vscode"
        else:
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
        
        title = f"{app_name} wants to access your vault"
        message = f"Tool: {tool_name}"
        if query_preview:
            # Truncate preview
            preview = query_preview[:50] + "..." if len(query_preview) > 50 else query_preview
            message += f"\nQuery: {preview}"
        
        try:
            if system == "Darwin":  # macOS
                import subprocess
                
                # Use AppleScript with osascript for interactive dialog
                script = f'''
                display dialog "{message}" buttons {{"Allow Once", "Always Allow", "Deny"}} default button 1 with title "{title}" with icon caution
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
                    zenity --question --title "{title}" --text "{message}\\n\\nChoose an option:" --extra-button "Allow Once" --extra-button "Always Allow" --ok-label "Deny" --timeout=30
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
        
        # Check if app is explicitly denied
        if app_identifier in self.permissions:
            app_perms = self.permissions[app_identifier]
            if app_perms.get("denied", False):
                logger.info(f"Access denied for {app_identifier} (explicitly denied)")
                return False
        
        # Show notification and get user decision
        decision = self._show_notification(app_name, tool_name, query_preview)
        
        if decision is None:
            # Notification failed - default to deny for security
            logger.warning("Notification failed - defaulting to deny")
            return False
        
        # Handle decision
        if decision == ConsentDecision.DENY:
            # Record denial
            if app_identifier not in self.permissions:
                self.permissions[app_identifier] = {}
            self.permissions[app_identifier]["denied"] = True
            self.permissions[app_identifier]["last_denied"] = datetime.now().isoformat()
            self._save_permissions()
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


