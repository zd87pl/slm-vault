"""
MCP Server Setup Utilities

Helps users set up MCP server integration with Claude Desktop and ChatGPT.
"""

import os
import json
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class MCPSetupHelper:
    """Helper for setting up MCP server integration."""
    
    def __init__(self, vault_path: str = "~/.vault"):
        """
        Initialize MCP setup helper.
        
        Args:
            vault_path: Path to vault directory
        """
        self.vault_path = Path(vault_path).expanduser()
        self.system = platform.system()
        self._test_cache = None  # Cache test result
        self._test_cache_time = None
        
    def get_claude_desktop_config_path(self) -> Optional[Path]:
        """
        Get Claude Desktop config file path for current OS.
        
        Returns:
            Path to config file, or None if not found
        """
        if self.system == "Darwin":  # macOS
            config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        elif self.system == "Windows":
            appdata = os.getenv("APPDATA")
            if appdata:
                config_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
            else:
                return None
        elif self.system == "Linux":
            config_path = Path.home() / ".config" / "claude" / "claude_desktop_config.json"
        else:
            return None
        
        return config_path
    
    def detect_claude_desktop(self) -> bool:
        """
        Check if Claude Desktop is installed.
        
        Returns:
            True if Claude Desktop appears to be installed
        """
        config_path = self.get_claude_desktop_config_path()
        if config_path and config_path.exists():
            return True
        
        # Also check if Claude app exists
        if self.system == "Darwin":
            app_path = Path("/Applications") / "Claude.app"
            if app_path.exists():
                return True
        
        return False
    
    def get_python_path(self) -> str:
        """
        Get Python executable path.
        
        Returns:
            Path to Python executable
        """
        # Priority: Homebrew Python > System Python > python3
        homebrew_python = "/opt/homebrew/bin/python3"
        if Path(homebrew_python).exists():
            return homebrew_python
        
        # Also check Intel Mac location
        homebrew_intel = "/usr/local/bin/python3"
        if Path(homebrew_intel).exists():
            return homebrew_intel
        
        try:
            # Try python3 first
            result = subprocess.run(
                ["which", "python3"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                python_path = result.stdout.strip()
                # Avoid miniconda/conda Python if Homebrew is available
                if "miniconda" not in python_path.lower() and "conda" not in python_path.lower():
                    return python_path
        except Exception:
            pass
        
        try:
            # Fallback to python
            result = subprocess.run(
                ["which", "python"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                python_path = result.stdout.strip()
                if "miniconda" not in python_path.lower() and "conda" not in python_path.lower():
                    return python_path
        except Exception:
            pass
        
        # Default fallback
        return "python3"
    
    def get_project_root(self) -> Path:
        """
        Get project root directory.
        
        Returns:
            Path to project root
        """
        # Try to find project root by looking for advanced_vault/mcp_server directory
        # Start from this file's location
        current = Path(__file__).resolve()
        
        # Go up to find project root
        while current != current.parent:
            if (current / "advanced_vault" / "mcp_server").exists():
                return current
            current = current.parent
        
        # Fallback: try to find from common locations
        try:
            import sys
            for path in sys.path:
                p = Path(path)
                if (p / "advanced_vault" / "mcp_server").exists():
                    return p
        except Exception:
            pass
        
        # Last resort: current working directory
        return Path.cwd()
    
    def generate_mcp_config(self) -> Dict:
        """
        Generate MCP server configuration for Claude Desktop.
        
        Returns:
            Configuration dictionary
        """
        python_path = self.get_python_path()
        project_root = self.get_project_root()
        vault_path = str(self.vault_path)
        
        config = {
            "mcpServers": {
                "enclave": {  # Changed from "personal-vault" to "enclave" for better visibility
                    "command": python_path,
                    "args": [
                        "-m", "advanced_vault.mcp_server"
                    ],
                    "env": {
                        "VAULT_PATH": vault_path,
                        "PYTHONPATH": str(project_root)
                    }
                }
            }
        }
        
        return config
    
    def load_existing_config(self) -> Optional[Dict]:
        """
        Load existing Claude Desktop config.
        
        Returns:
            Config dictionary or None if not found
        """
        config_path = self.get_claude_desktop_config_path()
        if not config_path or not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load existing config: {e}")
            return None
    
    def merge_config(self, new_config: Dict) -> Dict:
        """
        Merge new MCP config with existing config.
        
        Args:
            new_config: New MCP server configuration
            
        Returns:
            Merged configuration
        """
        existing = self.load_existing_config()
        
        if existing is None:
            return new_config
        
        # Merge mcpServers
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        
        # Merge personal-vault server config (support both old and new names)
        # Use "enclave" as the new name for better visibility
        if "personal-vault" in existing.get("mcpServers", {}):
            # Migrate old name to new name
            existing["mcpServers"]["enclave"] = existing["mcpServers"].pop("personal-vault")
        existing["mcpServers"]["enclave"] = new_config["mcpServers"]["enclave"]
        
        return existing
    
    def write_config(self, config: Dict) -> bool:
        """
        Write configuration to Claude Desktop config file.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if successful, False otherwise
        """
        config_path = self.get_claude_desktop_config_path()
        if not config_path:
            return False
        
        try:
            # Create directory if it doesn't exist
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Wrote MCP config to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
            return False
    
    def test_mcp_server(self, use_cache: bool = True) -> Tuple[bool, str]:
        """
        Test if MCP server can start successfully.
        
        Args:
            use_cache: If True, use cached result if available (within 30 seconds)
        
        Returns:
            Tuple of (success, message)
        """
        # Check cache if enabled
        if use_cache and self._test_cache is not None and self._test_cache_time is not None:
            import time
            if time.time() - self._test_cache_time < 30:  # Cache for 30 seconds
                return self._test_cache
        
        try:
            # Try to import the module
            import sys
            project_root = self.get_project_root()
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from advanced_vault.mcp_server import create_vault_server
            
            # Create server instance
            server = create_vault_server(str(self.vault_path))
            
            # Check if server has tools registered
            if hasattr(server, 'server'):
                result = (True, "MCP server initialized successfully")
            else:
                result = (False, "MCP server missing server attribute")
            
            # Cache result
            import time
            self._test_cache = result
            self._test_cache_time = time.time()
            return result
                
        except ImportError as e:
            result = (False, f"Import error: {str(e)}")
            import time
            self._test_cache = result
            self._test_cache_time = time.time()
            return result
        except Exception as e:
            result = (False, f"Error: {str(e)}")
            import time
            self._test_cache = result
            self._test_cache_time = time.time()
            return result
    
    def get_setup_status(self) -> Dict:
        """
        Get current setup status.
        
        Returns:
            Dictionary with status information
        """
        claude_installed = self.detect_claude_desktop()
        config_path = self.get_claude_desktop_config_path()
        config_exists = config_path and config_path.exists()
        
        existing_config = self.load_existing_config() if config_exists else None
        mcp_configured = (
            existing_config is not None and
            "mcpServers" in existing_config and
            ("enclave" in existing_config.get("mcpServers", {}) or 
             "personal-vault" in existing_config.get("mcpServers", {}))  # Support both names
        )
        
        # Use cache to avoid repeated MCP server initialization
        test_success, test_message = self.test_mcp_server(use_cache=True)
        
        return {
            "claude_installed": claude_installed,
            "config_path": str(config_path) if config_path else None,
            "config_exists": config_exists,
            "mcp_configured": mcp_configured,
            "test_success": test_success,
            "test_message": test_message,
            "vault_path": str(self.vault_path),
            "python_path": self.get_python_path(),
        }
    
    def get_config_json(self) -> str:
        """
        Get config JSON as formatted string.
        
        Returns:
            Formatted JSON string
        """
        config = self.generate_mcp_config()
        return json.dumps(config, indent=2)
    
    def get_merged_config_json(self) -> str:
        """
        Get merged config JSON as formatted string.
        
        Returns:
            Formatted JSON string
        """
        new_config = self.generate_mcp_config()
        merged = self.merge_config(new_config)
        return json.dumps(merged, indent=2)


