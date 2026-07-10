"""
Ollama Setup and Management

Automatically installs and configures Ollama for OCR functionality.
Handles installation, model downloading, and status checking.
"""

import logging
import subprocess
import shutil
import requests
import time
from pathlib import Path
from typing import Optional, Callable, Tuple
import platform

logger = logging.getLogger(__name__)


class OllamaSetup:
    """
    Handles automatic installation and setup of Ollama for OCR.
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
    
    def install_ollama(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Install Ollama automatically.
        
        Args:
            progress_callback: Optional callback function(status_message) for progress updates
            
        Returns:
            True if installation successful
        """
        if self.is_ollama_installed():
            if progress_callback:
                progress_callback("Ollama jest już zainstalowane")
            logger.info("Ollama already installed")
            return True
        
        if progress_callback:
            progress_callback("Installing Ollama...")
        
        logger.info("Installing Ollama...")
        
        try:
            if self.system == "Darwin":  # macOS
                # Try Homebrew first (most common)
                if shutil.which("brew"):
                    if progress_callback:
                        progress_callback("Installing via Homebrew...")
                    logger.info("Installing Ollama via Homebrew...")
                    result = subprocess.run(
                        ["brew", "install", "ollama"],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode == 0:
                        logger.info("Ollama installed via Homebrew")
                        return True
                    else:
                        logger.warning(f"Homebrew installation failed: {result.stderr}")
                
                # Fallback to curl script
                if progress_callback:
                    progress_callback("Installing via install script...")
                logger.info("Installing Ollama via curl script...")
                result = subprocess.run(
                    ["curl", "-fsSL", "https://ollama.com/install.sh"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    install_script = result.stdout
                    install_process = subprocess.Popen(
                        ["sh"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = install_process.communicate(input=install_script, timeout=300)
                    if install_process.returncode == 0:
                        logger.info("Ollama installed via script")
                        return True
                    else:
                        logger.error(f"Installation script failed: {stderr}")
                
            elif self.system == "Linux":
                # Use curl script for Linux
                if progress_callback:
                    progress_callback("Installing via install script...")
                logger.info("Installing Ollama via curl script...")
                result = subprocess.run(
                    ["curl", "-fsSL", "https://ollama.com/install.sh"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    install_script = result.stdout
                    install_process = subprocess.Popen(
                        ["sh"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = install_process.communicate(input=install_script, timeout=300)
                    if install_process.returncode == 0:
                        logger.info("Ollama installed via script")
                        return True
                    else:
                        logger.error(f"Installation script failed: {stderr}")
            
            logger.error(f"Failed to install Ollama on {self.system}")
            if progress_callback:
                progress_callback("Nie udało się zainstalować Ollama automatycznie")
            return False
            
        except subprocess.TimeoutExpired:
            logger.error("Ollama installation timed out")
            if progress_callback:
                progress_callback("Instalacja Ollama przekroczyła limit czasu")
            return False
        except Exception as e:
            logger.error(f"Error installing Ollama: {e}")
            if progress_callback:
                progress_callback(f"Installation error: {str(e)}")
            return False
    
    def start_ollama_server(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Start Ollama server (non-blocking).
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if server started successfully
        """
        if self.is_ollama_running():
            logger.info("Ollama server already running")
            return True
        
        if not self.is_ollama_installed():
            logger.error("Ollama not installed, cannot start server")
            return False
        
        try:
            if progress_callback:
                progress_callback("Starting Ollama server...")
            
            logger.info("Starting Ollama server...")
            # Start Ollama in background (non-blocking)
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Wait for server to start (max 10 seconds)
            for _ in range(20):
                time.sleep(0.5)
                if self.is_ollama_running():
                    logger.info("Ollama server started successfully")
                    if progress_callback:
                        progress_callback("Serwer Ollama uruchomiony")
                    return True
            
            logger.warning("Ollama server did not start within timeout")
            if progress_callback:
                progress_callback("Serwer Ollama nie uruchomił się")
            return False
            
        except Exception as e:
            logger.error(f"Error starting Ollama server: {e}")
            if progress_callback:
                progress_callback(f"Server start error: {str(e)}")
            return False
    
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
    
    def download_model(self, progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None) -> bool:
        """
        Download the required vision model.
        
        Args:
            progress_callback: Optional callback(message, percent, time_remaining) for progress updates
                              - message: Status message
                              - percent: Progress percentage (0-100) or None if unknown
                              - time_remaining: Estimated time remaining (e.g., "2m 30s") or None
            
        Returns:
            True if model downloaded successfully
        """
        if self.is_model_available():
            logger.info(f"Model {self.model} already available")
            if progress_callback:
                progress_callback(f"Model {self.model} already available", 100.0, None)
            return True
        
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
    
    def setup_ollama(self, progress_callback: Optional[Callable[[str, Optional[float], Optional[str]], None]] = None) -> Tuple[bool, str]:
        """
        Complete setup: install, start server, download model.
        
        Args:
            progress_callback: Optional callback(message, percent, time_remaining) for progress updates
        
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
        
        # Step 1: Install Ollama
        if not self.is_ollama_installed():
            if not self.install_ollama(lambda msg: wrapped_callback(msg, None, None)):
                return False, "Nie udało się zainstalować Ollama"
        
        # Step 2: Start server
        if not self.start_ollama_server(lambda msg: wrapped_callback(msg, None, None)):
            return False, "Nie udało się uruchomić serwera Ollama"
        
        # Step 3: Download model (this one supports detailed progress)
        if not self.download_model(wrapped_callback):
            return False, f"Nie udało się pobrać modelu {self.model}"
        
        return True, "Ollama OCR gotowe do użycia"
    
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

