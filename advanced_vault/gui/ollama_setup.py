"""
Ollama Setup and Management

Detects a local Ollama install for OCR and, only after the user confirms,
downloads the model it needs. Enclave never installs or starts Ollama itself:
callers show install or start instructions instead.
"""

import logging
import shutil
import requests
import time
from typing import Optional, Callable, Tuple
import platform

logger = logging.getLogger(__name__)

OLLAMA_WEBSITE = "https://ollama.com"
OLLAMA_OCR_READY = "Ollama OCR is ready"

# Approximate download sizes from the Ollama library (https://ollama.com/library),
# shown to the user before a model download is confirmed.
APPROX_MODEL_SIZES = {
    "llama3.2-vision": "about 8 GB",
    "llama3.2-vision:latest": "about 8 GB",
    "llama3.2-vision:11b": "about 8 GB",
    "tinyllama": "about 640 MB",
    "tinyllama:latest": "about 640 MB",
    "tinyllama:1.1b": "about 640 MB",
}


def approx_model_size(model: str) -> str:
    """Return a human-readable approximate download size for an Ollama model."""
    return APPROX_MODEL_SIZES.get(model, "size unknown; see https://ollama.com/library")


def ollama_install_instructions(model: str) -> str:
    """Explain how to set up Ollama by hand (Enclave never installs it)."""
    return (
        "Ollama is not installed, and Enclave does not install it for you. "
        f"To use it, install Ollama from {OLLAMA_WEBSITE}, start it, then run "
        f"`ollama pull {model}` ({approx_model_size(model)}) in a terminal. "
        "Text-based PDFs work without it."
    )


def ollama_start_instructions() -> str:
    """Explain how to start an installed Ollama (Enclave never starts it)."""
    return (
        "Ollama is installed but not running. Start it (open the Ollama app, or run "
        "`ollama serve` in a terminal), then try again. Text-based PDFs work without it."
    )


def ollama_pull_instructions(model: str) -> str:
    """Explain how to get a missing model without an automatic download."""
    return (
        f"The Ollama model {model} ({approx_model_size(model)}) is not downloaded. "
        f"Run `ollama pull {model}` in a terminal, or download it from "
        "Settings → Run Local Setup."
    )


def ollama_download_prompt(model: str, purpose: str) -> str:
    """Confirmation text naming the model and its approximate download size."""
    return (
        f"Download the Ollama model {model} ({approx_model_size(model)}) for {purpose}? "
        "Your local Ollama app downloads it from the Ollama registry, "
        "and it is stored on this computer."
    )


class OllamaSetup:
    """
    Detects Ollama and, after the user confirms, downloads its OCR model.

    It never installs Ollama: see ollama_install_instructions().
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2-vision:11b"):
        """
        Initialize Ollama setup manager.
        
        Args:
            base_url: Ollama API base URL
            model: Vision model name to use
        """
        self.base_url = base_url
        self.model = model
        self.system = platform.system()
    
    def is_ollama_installed(self) -> bool:
        """
        Check if Ollama is installed.
        
        Returns:
            True if Ollama command is available
        """
        return shutil.which("ollama") is not None
    
    def is_ollama_running(self) -> bool:
        """
        Check if Ollama server is running.
        
        Returns:
            True if Ollama server is accessible
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def install_instructions(self) -> str:
        """How to install Ollama and this model by hand."""
        return ollama_install_instructions(self.model)

    def is_model_available(self) -> bool:
        """
        Check if the required vision model is available.
        
        Returns:
            True if model is available
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                # Check if our model or any vision model is available
                return any(
                    self.model in name or 
                    "vision" in name.lower() or 
                    "llava" in name.lower()
                    for name in model_names
                )
            return False
        except Exception:
            return False
    
    def download_model(
        self,
        progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None,
        *,
        confirmed: bool = False,
    ) -> bool:
        """
        Download the required vision model.
        
        Args:
            progress_callback: Optional callback(message, percent, time_remaining) for progress updates
                              - message: Status message
                              - percent: Progress percentage (0-100) or None if unknown
                              - time_remaining: Estimated time remaining (e.g., "2m 30s") or None
            confirmed: True only after the user confirmed a prompt naming the
                model and its size (see ollama_download_prompt). Without it,
                nothing is downloaded.
            
        Returns:
            True if model downloaded successfully
        """
        if self.is_model_available():
            logger.info(f"Model {self.model} already available")
            if progress_callback:
                progress_callback(f"Model {self.model} already available", 100.0, None)
            return True

        if not confirmed:
            logger.info(ollama_pull_instructions(self.model))
            return False
        
        if not self.is_ollama_running():
            logger.error("Ollama server not running, cannot download model")
            if progress_callback:
                progress_callback("Serwer Ollama nie działa", None, None)
            return False
        
        try:
            if progress_callback:
                progress_callback(f"Downloading model {self.model}...", 0.0, None)
            
            logger.info(f"Downloading model {self.model}...")
            
            # Use Ollama API to pull model
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                stream=True,
                timeout=600  # 10 minutes timeout for large models
            )
            
            if response.status_code == 200:
                import json
                
                # Track progress for time estimation
                start_time = time.time()
                last_update_time = start_time
                last_completed = 0
                download_speeds = []  # Track recent speeds for averaging
                last_time_remaining_str = None  # Cache last time remaining string
                last_time_remaining_update = 0  # Track when we last updated time remaining
                
                # Stream progress updates
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            
                            # Calculate progress percentage
                            percent = None
                            if total > 0:
                                percent = min(100.0, (completed / total) * 100.0)
                            
                            # Calculate download speed and time remaining
                            time_remaining = None
                            current_time = time.time()
                            
                            if completed > 0 and total > 0 and completed > last_completed:
                                # Calculate speed (bytes per second)
                                time_diff = current_time - last_update_time
                                if time_diff > 0.5:  # Update every 0.5s
                                    bytes_diff = completed - last_completed
                                    speed = bytes_diff / time_diff
                                    download_speeds.append(speed)
                                    
                                    # Keep only last 10 speeds for averaging
                                    if len(download_speeds) > 10:
                                        download_speeds.pop(0)
                                    
                                    # Calculate average speed
                                    if download_speeds:
                                        avg_speed = sum(download_speeds) / len(download_speeds)
                                        
                                        # Estimate time remaining
                                        remaining_bytes = total - completed
                                        if avg_speed > 0:
                                            remaining_seconds = remaining_bytes / avg_speed
                                            
                                            # Only update time remaining string every 3 seconds or if change is significant
                                            time_since_last_update = current_time - last_time_remaining_update
                                            if time_since_last_update >= 3.0:  # Update every 3 seconds
                                                # Format time remaining (round down for stability)
                                                if remaining_seconds < 60:
                                                    time_remaining = f"{int(remaining_seconds)}s"
                                                elif remaining_seconds < 3600:
                                                    minutes = int(remaining_seconds // 60)
                                                    # Round seconds down to nearest 5 seconds for less flickering
                                                    seconds = int((remaining_seconds % 60) // 5) * 5
                                                    if seconds == 0 and minutes > 0:
                                                        time_remaining = f"{minutes}m"
                                                    else:
                                                        time_remaining = f"{minutes}m {seconds}s"
                                                else:
                                                    hours = int(remaining_seconds // 3600)
                                                    minutes = int((remaining_seconds % 3600) // 60)
                                                    time_remaining = f"{hours}h {minutes}m"
                                                
                                                last_time_remaining_str = time_remaining
                                                last_time_remaining_update = current_time
                                            else:
                                                # Use cached value
                                                time_remaining = last_time_remaining_str
                                    
                                    last_update_time = current_time
                                    last_completed = completed
                            
                            # Format status message
                            if status and progress_callback:
                                if "pulling" in status.lower() or "downloading" in status.lower():
                                    if percent is not None:
                                        message = f"Downloading: {percent:.1f}%"
                                    else:
                                        message = f"Downloading: {status}"
                                elif "verifying" in status.lower():
                                    message = f"Weryfikacja: {status}"
                                elif "success" in status.lower() or "complete" in status.lower():
                                    message = f"Gotowe: {status}"
                                    percent = 100.0
                                    time_remaining = None  # Clear time remaining when done
                                else:
                                    message = status
                                
                                progress_callback(message, percent, time_remaining)
                                
                        except Exception as e:
                            logger.debug(f"Error parsing progress line: {e}")
                            pass
                
                # Check if model is now available
                time.sleep(2)  # Give Ollama time to register the model
                if self.is_model_available():
                    logger.info(f"Model {self.model} downloaded successfully")
                    if progress_callback:
                        progress_callback(f"Model {self.model} downloaded successfully", 100.0, None)
                    return True
                else:
                    logger.warning(f"Model {self.model} downloaded but not available")
                    if progress_callback:
                        progress_callback("Model downloaded but not available", None, None)
                    return False
            else:
                logger.error(f"Failed to download model: {response.status_code} {response.text}")
                if progress_callback:
                    progress_callback("Nie udało się pobrać modelu", None, None)
                return False
                
        except Exception as e:
            logger.error(f"Error downloading model: {e}")
            if progress_callback:
                progress_callback(f"Model download error: {str(e)}", None, None)
            return False
    
    def setup_ollama(
        self,
        progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None,
        *,
        confirmed_download: bool = False,
    ) -> Tuple[bool, str]:
        """
        Get a running Ollama ready by downloading the model it needs.

        Never installs or starts Ollama: when it is missing or stopped, the
        message says what to do. The model is downloaded only with
        confirmed_download=True, which callers pass after the user confirmed
        a prompt naming the model and its size.
        
        Args:
            progress_callback: Optional callback(message, percent, time_remaining) for progress updates
            confirmed_download: Whether the user confirmed the model download
        
        Returns:
            (success: bool, message: str)
        """
        # Create wrapper for old-style callbacks (backward compatibility)
        def wrapped_callback(msg: str, percent: Optional[float] = None, time_remaining: Optional[str] = None):
            if progress_callback:
                # Check if callback accepts 3 parameters
                import inspect
                sig = inspect.signature(progress_callback)
                if len(sig.parameters) >= 3:
                    progress_callback(msg, percent, time_remaining)
                else:
                    # Old-style callback, just pass message
                    progress_callback(msg)
        
        # Ollama must already be installed and running; never install or start it.
        if not self.is_ollama_installed():
            return False, self.install_instructions()
        if not self.is_ollama_running():
            return False, ollama_start_instructions()

        if not confirmed_download:
            if self.is_model_available():
                return True, OLLAMA_OCR_READY
            return False, ollama_pull_instructions(self.model)
        
        # Download model (this one supports detailed progress)
        if not self.download_model(wrapped_callback, confirmed=True):
            return False, f"Nie udało się pobrać modelu {self.model}"
        
        return True, OLLAMA_OCR_READY
    
    def get_status(self) -> dict:
        """
        Get current Ollama status.
        
        Returns:
            Dictionary with status information
        """
        return {
            "installed": self.is_ollama_installed(),
            "running": self.is_ollama_running(),
            "model_available": self.is_model_available(),
            "model_name": self.model,
            "base_url": self.base_url
        }

