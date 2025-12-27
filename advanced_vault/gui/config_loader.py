"""
Configuration loader for Enclave GUI application.

Loads environment variables from multiple sources in priority order:
1. System environment variables (highest priority)
2. User config file (~/.enclave/config.env)
3. Embedded defaults (lowest priority)
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Default configuration (embedded in app)
DEFAULT_CONFIG = {
    "SUPABASE_URL": "https://ibiapabkyskoazpgcymo.supabase.co",
    "SUPABASE_ANON_KEY": "",  # Must be set by user or in config file
    "ENCLAVE_BACKEND_URL": "https://keen-curiosity-production-1288.up.railway.app",
    "RUNPOD_QA_ENDPOINT_ID": "",  # Optional
    "RUNPOD_API_KEY": "",  # Optional
    "RUNPOD_QA_API_KEY": "",  # Optional
}


def load_config_file(config_path: Path) -> Dict[str, str]:
    """
    Load configuration from a .env file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Dictionary of key-value pairs
    """
    config = {}
    if not config_path.exists():
        return config
    
    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE format
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    config[key] = value
        logger.debug(f"Loaded {len(config)} config values from {config_path}")
    except Exception as e:
        logger.warning(f"Failed to load config file {config_path}: {e}")
    
    return config


def get_config() -> Dict[str, str]:
    """
    Get configuration with priority:
    1. System environment variables
    2. User config file (~/.enclave/config.env)
    3. Default values
    
    Returns:
        Dictionary of configuration values
    """
    config = DEFAULT_CONFIG.copy()
    
    # Load from user config file
    user_config_path = Path.home() / ".enclave" / "config.env"
    if user_config_path.exists():
        user_config = load_config_file(user_config_path)
        config.update(user_config)
        logger.info(f"Loaded user config from {user_config_path}")
    
    # Override with system environment variables (highest priority)
    for key in DEFAULT_CONFIG.keys():
        env_value = os.getenv(key)
        if env_value:
            config[key] = env_value
    
    # Log which values are set
    set_values = {k: v for k, v in config.items() if v}
    logger.debug(f"Configuration loaded: {len(set_values)}/{len(config)} values set")
    
    return config


def apply_config(config: Optional[Dict[str, str]] = None) -> None:
    """
    Apply configuration to environment variables.
    
    Args:
        config: Optional config dict. If None, loads config automatically.
    """
    if config is None:
        config = get_config()
    
    for key, value in config.items():
        if value and not os.getenv(key):
            os.environ[key] = value
            logger.debug(f"Set {key} from config")


def get_config_value(key: str, default: str = "") -> str:
    """
    Get a configuration value.
    
    Args:
        key: Configuration key
        default: Default value if not found
        
    Returns:
        Configuration value
    """
    config = get_config()
    return config.get(key, default)


def validate_config() -> tuple[bool, list[str]]:
    """
    Validate that required configuration values are set.
    
    Returns:
        Tuple of (is_valid, list_of_missing_keys)
    """
    config = get_config()
    required_keys = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "ENCLAVE_BACKEND_URL"]
    missing = [key for key in required_keys if not config.get(key)]
    return len(missing) == 0, missing


def show_config_status() -> str:
    """
    Get a human-readable status of configuration.
    
    Returns:
        Status message
    """
    is_valid, missing = validate_config()
    config = get_config()
    
    if is_valid:
        return "✓ Configuration complete"
    else:
        missing_str = ", ".join(missing)
        return f"⚠ Configuration incomplete. Missing: {missing_str}"


if __name__ == "__main__":
    # Test the config loader
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing config loader...")
    config = get_config()
    print("\nConfiguration:")
    for key, value in config.items():
        if value:
            # Mask sensitive values
            display_value = value[:10] + "..." if len(value) > 10 else value
            print(f"  {key}: {display_value}")
        else:
            print(f"  {key}: (not set)")
    
    is_valid, missing = validate_config()
    print(f"\nValidation: {'✓ Valid' if is_valid else '✗ Invalid'}")
    if missing:
        print(f"Missing keys: {', '.join(missing)}")
    
    print(f"\nStatus: {show_config_status()}")

