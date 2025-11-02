"""
Activity Logger for MCP Server Access

Logs all vault access attempts from MCP clients for visibility in GUI.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ActivityLogger:
    """Logs vault access activity for GUI visibility."""
    
    def __init__(self, vault_path: str = "~/.vault"):
        """
        Initialize activity logger.
        
        Args:
            vault_path: Base directory for vault storage
        """
        self.vault_path = Path(vault_path).expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)
        
        # Activity log file
        self.activity_log_path = self.vault_path / "activity.jsonl"
        
        logger.info(f"Initialized ActivityLogger at {self.vault_path}")
    
    def log_access(
        self,
        tool_name: str,
        app_identifier: str,
        query_preview: str = "",
        granted: bool = True,
        result_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log vault access attempt.
        
        Args:
            tool_name: MCP tool name (e.g., "vault_recall")
            app_identifier: App identifier (e.g., "claude-desktop")
            query_preview: Preview of query/operation
            granted: Whether access was granted
            result_summary: Brief summary of result (e.g., "Found 4 entries")
            metadata: Additional metadata
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "app_identifier": app_identifier,
            "app_name": app_identifier.replace("-", " ").title(),
            "query_preview": query_preview,
            "granted": granted,
            "result_summary": result_summary,
            "metadata": metadata or {}
        }
        
        try:
            # Append to JSONL file
            with open(self.activity_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
            
            logger.debug(f"Logged activity: {tool_name} from {app_identifier}")
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
    
    def get_recent_activity(self, limit: int = 50) -> list:
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
        except Exception as e:
            logger.error(f"Failed to read activity log: {e}")
            return []
    
    def clear_activity(self):
        """Clear activity log."""
        try:
            if self.activity_log_path.exists():
                self.activity_log_path.unlink()
            logger.info("Cleared activity log")
        except Exception as e:
            logger.error(f"Failed to clear activity log: {e}")

