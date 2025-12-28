#!/usr/bin/env python3
"""
Enclave - Secure Encrypted Vault with AI Inference
Beautiful Material Design UI for encrypted vault management
"""

import flet as ft
import os
import sys
import platform
import threading
import requests
import logging
import base64
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import time

# Check if MLX module is available
try:
    from qa_generator_mlx import MLXQAGenerator
    MLX_MODULE_AVAILABLE = True
except ImportError:
    MLX_MODULE_AVAILABLE = False

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.encrypted_kv import QueryFilter, EntryType
from advanced_vault.mcp_server.activity_logger import ActivityLogger
from auth_screen import AuthScreen
from cloud_sync import CloudSyncService
from pdf_processor import PDFProcessor
from qa_generator import QAGenerator
from training_manager import TrainingManager
from folder_manager import FolderManager
from training_queue import TrainingQueue, QueueItem, QueueItemStatus, WatchedFolder
from theme import ModernTheme
from sleek_theme import SleekTheme
from light_theme import LightTheme
from welcome_screen import WelcomeScreen
from error_helper import make_user_friendly, format_error_snackbar
from mcp_setup import MCPSetupHelper
from modern_sidebar import ModernSidebar
from config_loader import apply_config, validate_config, show_config_status

logger = logging.getLogger(__name__)

# Load configuration early (before app initialization)
apply_config()


class VaultApp:
    """Enclave - Secure Vault GUI Application."""

    def __init__(self, page: ft.Page):
        """Initialize the app."""
        # Ensure RUNPOD_QA_API_KEY is set by default from RUNPOD_API_KEY
        # This ensures QA generation endpoint works by default
        self._ensure_qa_api_key_set()
        
        self.page = page
        self.page.title = "🔐 Enclave"
        self.page.theme_mode = ft.ThemeMode.LIGHT  # Changed to light theme
        self.page.padding = 0
        
        # Set window size to 70% of screen (professional app sizing)
        # Get screen size and calculate 70%
        import platform
        if platform.system() == "Darwin":  # macOS
            # macOS typically has high DPI, so we use reasonable defaults
            # Flet will handle scaling automatically
            screen_width = 1440  # Typical MacBook width
            screen_height = 900  # Typical MacBook height
        else:
            # For other platforms, use default screen size
            screen_width = 1920
            screen_height = 1080
        
        window_width = int(screen_width * 0.7)
        window_height = int(screen_height * 0.7)
        
        # Set window size and center it
        self.page.window.width = window_width
        self.page.window.height = window_height
        self.page.window.center()
        self.page.window.min_width = 800
        self.page.window.min_height = 600
        
        # Set up light theme (Hugging Face inspired)
        self.page.theme = ft.Theme(
            color_scheme_seed=LightTheme.ACCENT_PRIMARY,
            font_family="System",
            text_theme=ft.TextTheme(
                display_large=ft.TextStyle(size=32, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                display_medium=ft.TextStyle(size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                headline_large=ft.TextStyle(size=20, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                title_large=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                body_large=ft.TextStyle(size=14, color=LightTheme.TEXT_PRIMARY),
                body_medium=ft.TextStyle(size=13, color=LightTheme.TEXT_SECONDARY),
                label_large=ft.TextStyle(size=12, weight=ft.FontWeight.W_500, color=LightTheme.TEXT_PRIMARY),
            ),
        )
        
        # Set page background (light theme)
        self.page.bgcolor = LightTheme.BG_PRIMARY

        # Backend configuration
        # Validate configuration
        is_valid, missing = validate_config()
        if not is_valid:
            logger.warning(f"Configuration incomplete. Missing: {', '.join(missing)}")
            logger.info(f"Config status: {show_config_status()}")
            # Continue anyway - some features may not work
        
        self.backend_url = os.getenv(
            "ENCLAVE_BACKEND_URL",
            "https://keen-curiosity-production-1288.up.railway.app"
        )

        # Authentication state
        self.session_data = None
        self.vault = None
        self.cloud_sync = None
        self.folder_manager = None  # Will be initialized after vault
        # Initialize PDF processor - will setup Ollama when GUI is ready
        self.pdf_processor = None  # Will be initialized after GUI is ready
        self.pdf_file_picker = None  # Will be created when Knowledge view is shown
        self.qa_generator = None
        self.training_manager = None

        # Backend connectivity state (for training service)
        self.backend_status = "unknown"  # unknown, connected, disconnected
        self.last_check = None

        # Vault setup paths
        self.vault_path = Path("~/.vault").expanduser()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self.key_path = self.vault_path / "master.key"
        self.db_path = self.vault_path / "vault.db"
        
        # Initialize MCP setup helper (after vault_path is set)
        self.mcp_setup = MCPSetupHelper(vault_path=str(self.vault_path))

        # UI state
        self.current_view = "secrets"
        self.search_query = ""
        self.selected_type = "all"
        # Track component status for UI
        self._component_status = {
            "ocr": {"status": "checking", "message": "Checking..."},  # checking, ready, installing, error
            "vault": {"status": "ready", "message": "Ready"},
            "cloud_sync": {"status": "ready", "message": "Ready"},
            "training": {"status": "ready", "message": "Ready"},
            "qa": {"status": "checking", "message": "Checking..."},  # checking, ready, installing, error
        }
        # Flag to prevent infinite refresh loops
        self._refreshing_settings = False
        
        # Training view auto-refresh timer (for pending/training jobs)
        self._training_refresh_timer = None
        self._training_refresh_active = False

        # Check for existing session
        self.check_authentication()

    def check_authentication(self):
        """Check if user is authenticated."""
        # Try to load existing session
        self.session_data = AuthScreen.load_session()

        if self.session_data:
            # User is authenticated, initialize vault
            self.initialize_vault()
            self.build_ui()
            
            # Initialize PDF processor after GUI is ready
            self._initialize_pdf_processor()
        else:
            # Show authentication screen
            self.show_auth_screen()

    def show_auth_screen(self):
        """Show authentication screen."""
        auth_screen = AuthScreen(
            page=self.page,
            backend_url=self.backend_url,
            on_auth_success=self.on_auth_success
        )

        self.page.clean()
        self.page.add(auth_screen.get_view())
        self.page.update()

    def on_auth_success(self, session_data: dict):
        """Called when authentication succeeds."""
        self.session_data = session_data

        # Initialize vault
        self.initialize_vault()

        # Sync from cloud on login
        self.sync_from_cloud()

        # Always show landing page first
        self.show_landing_page()
        
        # Check if setup is needed and show overlay if necessary
        def check_and_setup():
            # Wait a bit for components to initialize
            import time
            time.sleep(1.5)  # Give components time to initialize
            
            # Check if setup is needed
            if self._needs_setup():
                # Show setup overlay/progress dialog
                # Call directly since _auto_setup_components is not async
                self._auto_setup_components()
        
        # Initialize components and check setup in background
        self._initialize_pdf_processor()
        threading.Thread(target=check_and_setup, daemon=True).start()
    
    def _create_progress_dialog(self, title: str, initial_message: str = "Preparing...") -> tuple:
        """
        Create a professional progress dialog (70% of screen, maximized, no scroll).
        Styled like ProtonVPN - clean, modern, professional.
        
        Returns:
            Tuple of (dialog, progress_text, progress_bar, progress_percent, time_remaining_text)
        """
        # Get actual window size (70% of screen is already set in __init__)
        window_width = self.page.window.width or 1200
        window_height = self.page.window.height or 800
        
        # Dialog should be 70% of window, but with reasonable min/max
        dialog_width = min(max(int(window_width * 0.7), 500), 800)
        dialog_height = min(max(int(window_height * 0.7), 300), 500)
        
        # Content height is fixed - no scroll, content fits perfectly
        content_height = dialog_height - 120  # Account for title (60px) and padding/margins (60px)
        
        progress_text = ft.Text(
            initial_message,
            size=14,
            color=LightTheme.TEXT_PRIMARY,
            text_align=ft.TextAlign.LEFT,
            selectable=False,
        )
        progress_percent = ft.Text(
            "",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=LightTheme.ACCENT_PRIMARY,
        )
        time_remaining_text = ft.Text(
            "",
            size=12,
            color=LightTheme.TEXT_MUTED,
        )
        progress_bar = ft.ProgressBar(
            width=dialog_width - 80,  # Account for padding
            value=0.0,
            color=LightTheme.ACCENT_PRIMARY,
            bgcolor=LightTheme.BG_ELEVATED,
            bar_height=8,  # Slightly thicker for better visibility
        )
        
        # Content container - fixed height, no scroll
        content_container = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=16),
                    # Progress text with max height to prevent overflow
                    ft.Container(
                        content=progress_text,
                        height=120,  # Fixed height for message area
                        padding=ft.padding.only(bottom=8),
                    ),
                    ft.Container(height=24),
                    # Progress bar
                    progress_bar,
                    ft.Container(height=16),
                    # Status row (percentage + time)
                    ft.Row(
                        [
                            progress_percent,
                            ft.Container(expand=True),  # Spacer
                            time_remaining_text,
                        ],
                        spacing=0,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=16),
                ],
                tight=True,
                scroll=None,  # NO SCROLL - fixed height layout
                spacing=0,
            ),
            width=dialog_width - 40,
            height=content_height,
            padding=20,
        )
        
        progress_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    title,
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                padding=ft.padding.only(bottom=8),
            ),
            content=content_container,
            actions=[],
            bgcolor=LightTheme.BG_ELEVATED,
            shape=ft.RoundedRectangleBorder(radius=16),  # Modern rounded corners
        )
        
        return progress_dialog, progress_text, progress_bar, progress_percent, time_remaining_text
    
    def _setup_qa_model_with_progress(self):
        """
        Setup TinyLlama Q&A model with visible progress dialog showing percentage and time remaining.
        """
        if not self.qa_generator:
            logger.error("Q&A generator not initialized")
            return
        
        progress_dialog, progress_text, progress_bar, progress_percent, time_remaining_text = self._create_progress_dialog(
            "🔧 Setting up Q&A Generation",
            "Preparing Q&A Generation..."
        )
        
        self.page.overlay.append(progress_dialog)
        progress_dialog.open = True
        self.page.update()
        
        def update_progress(message: str, percent: Optional[float] = None, time_remaining: Optional[str] = None):
            """Update progress in dialog and component status."""
            try:
                if progress_dialog and progress_dialog.open and progress_text and progress_bar and progress_percent:
                    progress_text.value = message
                    
                    if percent is not None and percent >= 0:
                        # Only show percentage if it's valid (>= 0)
                        progress_bar.value = percent / 100.0
                        progress_percent.value = f"{percent:.1f}%"
                    else:
                        # Indeterminate progress (no percentage)
                        progress_bar.value = None
                        progress_percent.value = ""
                    
                    if time_remaining_text:
                        if time_remaining:
                            time_remaining_text.value = f"⏱️ {time_remaining} remaining"
                    
                    self.page.update()
                    
                    # Update component status
                    qa_status = self.qa_generator.get_qa_status()
                    is_mlx = qa_status.get("preferred_method") == "MLX" or "MLX" in message or "Qwen" in message
                    
                    if "Pobieranie" in message or "Downloading" in message or "Loading" in message:
                        self._component_status["qa"]["status"] = "installing"
                        if is_mlx:
                            if percent is not None:
                                self._component_status["qa"]["message"] = f"Downloading AI model... {percent:.1f}%"
                            else:
                                self._component_status["qa"]["message"] = "Downloading optimized AI model..."
                        else:
                            if percent is not None:
                                self._component_status["qa"]["message"] = f"Downloading TinyLlama... {percent:.1f}%"
                            else:
                                self._component_status["qa"]["message"] = "Downloading TinyLlama..."
                    elif "gotowe" in message.lower() or "ready" in message.lower() or "available" in message.lower():
                        self._component_status["qa"]["status"] = "ready"
                        if is_mlx:
                            self._component_status["qa"]["message"] = "Ready (Optimized AI)"
                        else:
                            self._component_status["qa"]["message"] = "Ready (Local AI)"
                    
                    # Refresh Settings if visible
                    if hasattr(self, 'current_view') and self.current_view == "settings" and not self._refreshing_settings:
                        import threading
                        def delayed_refresh():
                            threading.Event().wait(0.5)
                            if hasattr(self, 'page') and self.page and not self._refreshing_settings:
                                try:
                                    self._refreshing_settings = True
                                    self.show_settings()
                                except Exception:
                                    pass
                                finally:
                                    self._refreshing_settings = False
                        threading.Thread(target=delayed_refresh, daemon=True).start()
            except Exception as e:
                logger.debug(f"Could not update progress: {e}")
        
        # Setup Q&A model with progress callback
        try:
            success, message = self.qa_generator.setup_qa_model(progress_callback=update_progress)
            if success:
                # Update status based on actual method used
                qa_status = self.qa_generator.get_qa_status()
                if qa_status.get("preferred_method") == "MLX":
                    self._component_status["qa"]["status"] = "ready"
                    self._component_status["qa"]["message"] = "Ready (MLX Qwen2.5-3B)"
                else:
                    self._component_status["qa"]["status"] = "ready"
                    self._component_status["qa"]["message"] = "Ready (Ollama TinyLlama)"
                progress_text.value = "✅ Q&A Generation ready!"
                progress_bar.value = 1.0
                progress_percent.value = "100%"
                time_remaining_text.value = ""
                progress_dialog.actions = [
                    ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                ]
            else:
                progress_text.value = f"❌ {message}"
                progress_bar.value = None
                progress_percent.value = ""
                time_remaining_text.value = ""
                self._component_status["qa"]["status"] = "error"
                self._component_status["qa"]["message"] = message
                progress_dialog.actions = [
                    ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                ]
        except Exception as e:
            logger.error(f"Error setting up Q&A model: {e}")
            progress_text.value = f"❌ Error: {str(e)}"
            progress_bar.value = None
            progress_percent.value = ""
            time_remaining_text.value = ""
            self._component_status["qa"]["status"] = "error"
            self._component_status["qa"]["message"] = f"Error: {str(e)}"
            progress_dialog.actions = [
                ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
            ]
        
        self.page.update()
    
    def _get_qa_setup_tooltip(self) -> str:
        """Get tooltip text for Q&A setup button based on available method."""
        if not self.qa_generator:
            return "Setup Q&A Generation"
        
        qa_status = self.qa_generator.get_qa_status()
        if qa_status.get("mlx_available") and not qa_status.get("mlx_initialized"):
            return "Download optimized AI model (~3GB)"
        elif qa_status.get("preferred_method") == "MLX":
            return "Optimized AI model ready"
        else:
            return "Download TinyLlama model"

    def _setup_ollama_with_progress(self):
        """
        Setup Ollama OCR with visible progress dialog showing percentage and time remaining.
        """
        progress_dialog, progress_text, progress_bar, progress_percent, time_remaining_text = self._create_progress_dialog(
            "🔧 Setting up AI Knowledge Extraction",
            "Preparing OCR..."
        )
        
        self.page.overlay.append(progress_dialog)
        progress_dialog.open = True
        self.page.update()
        
        def update_progress(message: str, percent: Optional[float] = None, time_remaining: Optional[str] = None):
            """Update progress dialog with message, percentage, and time remaining."""
            try:
                if progress_dialog.open:
                    # Update message
                    progress_text.value = message
                    
                    # Update progress bar and percentage
                    if percent is not None and percent >= 0:
                        # Only show percentage if it's valid (>= 0)
                        progress_bar.value = percent / 100.0
                        progress_percent.value = f"{percent:.1f}%"
                    else:
                        # Indeterminate progress (no percentage)
                        progress_bar.value = None
                        progress_percent.value = ""
                    
                    # Update time remaining - only update if we have a value
                    # Keep previous value if None to prevent flickering
                    if time_remaining:
                        time_remaining_text.value = f"⏱️ {time_remaining} remaining"
                    
                    self.page.update()
            except Exception as e:
                logger.debug(f"Could not update progress: {e}")
        
        # Setup Ollama with progress callback
        try:
            success, message = self.pdf_processor.ollama_setup.setup_ollama(progress_callback=update_progress)
            if success:
                self.pdf_processor.ollama_available = self.pdf_processor._test_ollama_connection()
                progress_text.value = "✅ AI Knowledge Extraction ready!"
                progress_bar.value = 1.0
                progress_percent.value = "100%"
                time_remaining_text.value = ""
                progress_dialog.actions = [
                    ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                ]
            else:
                progress_text.value = f"❌ {message}"
                progress_bar.value = None
                progress_percent.value = ""
                time_remaining_text.value = ""
                progress_dialog.actions = [
                    ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                ]
        except Exception as e:
            logger.error(f"Error setting up Ollama: {e}")
            progress_text.value = f"❌ Error: {str(e)}"
            progress_bar.value = None
            progress_percent.value = ""
            time_remaining_text.value = ""
            progress_dialog.actions = [
                ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
            ]
        
        self.page.update()
    
    def _auto_setup_components(self):
        """Automatically setup components that need configuration."""
        try:
            # Check what needs setup
            needs_ocr = False
            needs_qa = False
            
            if hasattr(self, 'pdf_processor') and self.pdf_processor:
                if not (self.pdf_processor.smoldocling_available or self.pdf_processor.ollama_available):
                    needs_ocr = True
            else:
                needs_ocr = True  # Not initialized yet
            
            if hasattr(self, 'qa_generator') and self.qa_generator:
                qa_status = self.qa_generator.get_qa_status()
                if qa_status.get("status") != "ready":
                    needs_qa = True
                elif qa_status.get("mlx_available") and not qa_status.get("mlx_initialized"):
                    needs_qa = True
            else:
                needs_qa = True  # Not initialized yet
            
            # Show setup dialogs for missing components
            if needs_ocr:
                logger.info("OCR component needs setup - showing setup dialog")
                self._setup_ocr_with_progress()
            
            if needs_qa:
                logger.info("Q&A component needs setup - will show in Settings")
                # Q&A setup will be triggered from Settings or when user tries to use it
                # Don't auto-show here to avoid interrupting user
        
        except Exception as e:
            logger.error(f"Error in auto-setup: {e}")
    
    def _initialize_pdf_processor(self):
        """Initialize PDF processor after GUI is ready (for progress callbacks)."""
        if self.pdf_processor is None:
            # Check if anything needs setup BEFORE initializing PDFProcessor
            # First check SmolDocling (preferred on Apple Silicon)
            needs_setup = True
            smoldocling_available = False
            
            try:
                # Check if SmolDocling is already available and working
                import platform
                if platform.machine() == "arm64":
                    try:
                        # Check if SmolDocling dependencies are installed
                        import mlx_vlm
                        import docling_core
                        # If imports succeed, SmolDocling should work (model loads on first use)
                        # Don't try to load model here as it's slow - just check dependencies
                        smoldocling_available = True
                        logger.debug("SmolDocling dependencies available - no setup needed")
                    except ImportError:
                        smoldocling_available = False
                        logger.debug("SmolDocling dependencies not available")
                
                # If SmolDocling is available, no setup needed
                if smoldocling_available:
                    needs_setup = False
                    logger.debug("OCR ready (SmolDocling) - skipping setup dialog")
                else:
                    # Check Ollama as fallback
                    from advanced_vault.gui.ollama_setup import OllamaSetup
                    temp_ollama_setup = OllamaSetup()
                    ollama_ready = (temp_ollama_setup.is_ollama_installed() and 
                                   temp_ollama_setup.is_ollama_running() and 
                                   temp_ollama_setup.is_model_available())
                    if ollama_ready:
                        needs_setup = False
                        logger.debug("OCR ready (Ollama) - skipping setup dialog")
                    else:
                        logger.debug("OCR not ready - setup dialog will be shown")
            except Exception as e:
                logger.debug(f"Error checking OCR availability: {e}")
                needs_setup = True  # Default to showing setup if check fails
            
            # Create progress dialog ONLY if setup is actually needed
            progress_dialog = None
            progress_text = None
            progress_percent = None
            time_remaining_text = None
            progress_bar = None
            
            if needs_setup:
                # Create progress dialog using helper
                progress_dialog, progress_text, progress_bar, progress_percent, time_remaining_text = self._create_progress_dialog(
                    "🔧 Setting up AI Knowledge Extraction",
                    "Checking AI Knowledge Extraction..."
                )
                
                self.page.overlay.append(progress_dialog)
                progress_dialog.open = True
                self.page.update()
            
            def progress_callback(message: str, percent: Optional[float] = None, time_remaining: Optional[str] = None):
                """Update progress in snackbar, component status, and dialog."""
                try:
                    # Update progress dialog if it exists
                    if progress_dialog and progress_dialog.open and progress_text and progress_bar and progress_percent:
                        try:
                            progress_text.value = message
                            
                            if percent is not None:
                                progress_bar.value = percent / 100.0
                                progress_percent.value = f"{percent:.1f}%"
                            else:
                                progress_bar.value = None  # Indeterminate
                                progress_percent.value = ""
                            
                            if time_remaining_text:
                                if time_remaining:
                                    time_remaining_text.value = f"⏱️ {time_remaining} remaining"
                                # Don't clear the text - keep last value to prevent flickering
                                # Only update if we have a new value
                            
                            self.page.update()
                        except Exception as e:
                            logger.debug(f"Could not update progress dialog: {e}")
                    
                    # Update component status
                    if "Instalowanie" in message or "Installing" in message:
                        self._component_status["ocr"]["status"] = "installing"
                        self._component_status["ocr"]["message"] = "Installing AI Knowledge Extraction..."
                    elif "Pobieranie" in message or "Downloading" in message or "pull" in message.lower():
                        self._component_status["ocr"]["status"] = "installing"
                        # Include percentage in message if available
                        if percent is not None:
                            self._component_status["ocr"]["message"] = f"Downloading AI models... {percent:.1f}%"
                            if time_remaining:
                                self._component_status["ocr"]["message"] += f" ({time_remaining} remaining)"
                        else:
                            self._component_status["ocr"]["message"] = "Downloading AI models..."
                    elif "Uruchamianie" in message or "Starting" in message:
                        self._component_status["ocr"]["status"] = "installing"
                        self._component_status["ocr"]["message"] = "Starting AI services..."
                    elif "SmolDocling" in message:
                        self._component_status["ocr"]["status"] = "installing"
                        self._component_status["ocr"]["message"] = "Initializing SmolDocling OCR (~500MB)..."
                    elif "gotowe" in message.lower() or "ready" in message.lower() or "available" in message.lower():
                        self._component_status["ocr"]["status"] = "ready"
                        # Check which OCR engine is being used
                        if hasattr(self, 'pdf_processor') and self.pdf_processor:
                            if self.pdf_processor.smoldocling_available:
                                self._component_status["ocr"]["message"] = "Ready (SmolDocling ~500MB)"
                            elif self.pdf_processor.ollama_available:
                                self._component_status["ocr"]["message"] = "Ready (Ollama)"
                            else:
                                self._component_status["ocr"]["message"] = "Ready"
                        else:
                            self._component_status["ocr"]["message"] = "Ready"
                    else:
                        self._component_status["ocr"]["message"] = message
                    
                    # Update UI if Settings page is visible
                    if hasattr(self, 'page') and self.page:
                        # Update snackbar (with percentage if available)
                        snackbar_text = f"🔧 {message}"
                        if percent is not None:
                            snackbar_text = f"🔧 {message} ({percent:.1f}%)"
                        if time_remaining:
                            snackbar_text += f" ⏱️ {time_remaining}"
                        
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(snackbar_text),
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            duration=3000,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                        
                        # Refresh Settings if visible (but prevent infinite loop)
                        # Only refresh if Settings is actually visible and not already refreshing
                        if (hasattr(self, 'current_view') and self.current_view == "settings" 
                            and not self._refreshing_settings):
                            # Use a small delay to prevent rapid refreshes
                            import threading
                            def delayed_refresh():
                                threading.Event().wait(0.5)  # Wait 500ms
                                if hasattr(self, 'page') and self.page and not self._refreshing_settings:
                                    try:
                                        self._refreshing_settings = True
                                        self.show_settings()
                                    except Exception:
                                        pass  # Ignore errors during refresh
                                    finally:
                                        self._refreshing_settings = False
                            
                            threading.Thread(target=delayed_refresh, daemon=True).start()
                except Exception:
                    pass
            
            self.pdf_processor = PDFProcessor(
                auto_setup=True,  # Enable auto-setup now that GUI is ready
                progress_callback=progress_callback
            )
            
            # Update status based on availability
            if self.pdf_processor.smoldocling_available:
                self._component_status["ocr"]["status"] = "ready"
                self._component_status["ocr"]["message"] = "Ready (SmolDocling ~500MB)"
            elif self.pdf_processor.ollama_available:
                self._component_status["ocr"]["status"] = "ready"
                self._component_status["ocr"]["message"] = "Ready (Ollama)"
            else:
                self._component_status["ocr"]["status"] = "checking"
                self._component_status["ocr"]["message"] = "Setting up..."
                
                # Close progress dialog if setup failed
                if progress_dialog and progress_dialog.open:
                    progress_text.value = "⚠️ Setup in progress... Check Settings for details."
                    if progress_bar:
                        progress_bar.value = None
                    if progress_percent:
                        progress_percent.value = ""
                    if time_remaining_text:
                        time_remaining_text.value = ""
                    progress_dialog.actions = [
                        ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                    ]
                    self.page.update()
            
            # Close progress dialog ONLY if it was opened (setup was needed)
            # If OCR is ready and dialog was opened, show success and close
            if progress_dialog and progress_dialog.open:
                if self.pdf_processor.smoldocling_available or self.pdf_processor.ollama_available:
                    # Setup completed successfully - show success message
                    progress_text.value = "✅ AI Knowledge Extraction ready!"
                    if progress_bar:
                        progress_bar.value = 1.0
                    if progress_percent:
                        progress_percent.value = "100%"
                    if time_remaining_text:
                        time_remaining_text.value = ""
                    progress_dialog.actions = [
                        ft.TextButton("OK", on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                    ]
                    self.page.update()
                else:
                    # Setup failed - close dialog silently, user can setup from Settings
                    progress_dialog.open = False
                    self.page.update()
    
    def _needs_setup(self) -> bool:
        """Check if any components need setup."""
        try:
            # If components not initialized yet, we can't check - assume ready (will check after init)
            # This prevents welcome screen from showing on every startup
            if not hasattr(self, 'pdf_processor') or not self.pdf_processor:
                return False  # Will be initialized later, don't block on startup
            
            if not hasattr(self, 'qa_generator') or not self.qa_generator:
                return False  # Will be initialized later, don't block on startup
            
            # Check OCR status
            if not (self.pdf_processor.smoldocling_available or self.pdf_processor.ollama_available):
                return True
            
            # Check Q&A status
            qa_status = self.qa_generator.get_qa_status()
            if qa_status.get("status") != "ready":
                return True
            # Check if MLX is available but not initialized
            if qa_status.get("mlx_available") and not qa_status.get("mlx_initialized"):
                return True
            
            return False  # All components ready
        except Exception as e:
            logger.warning(f"Error checking setup status: {e}")
            return False  # Don't block on error - let user proceed
    
    def _is_first_time_user(self) -> bool:
        """Check if user is first-time (no vault entries)."""
        try:
            if not self.vault:
                return True
            
            # Check if vault has any entries
            query_filter = QueryFilter()
            result = self.vault.kv_store.search(query_filter)
            
            # Also check if database file is new (no entries)
            if not self.db_path.exists() or self.db_path.stat().st_size == 0:
                return True
            
            # Check if we have any entries after sync
            return len(result) == 0
        except Exception as e:
            logger.warning(f"Error checking first-time user status: {e}")
            return True  # Default to showing welcome screen on error
    
    def show_welcome_screen(self):
        """Show welcome screen for first-time users."""
        welcome = WelcomeScreen(
            page=self.page,
            on_start=self._on_welcome_complete,
            on_add_sample=self._add_sample_data
        )
        
        self.page.clean()
        self.page.add(welcome.get_view())
        self.page.update()
    
    def _on_welcome_complete(self):
        """Called when welcome screen is dismissed."""
        # Always go to landing page after welcome screen
        self.show_landing_page()
    
    def _add_sample_data(self):
        """Add sample data for first-time users."""
        try:
            if not self.vault:
                logger.error("Vault not initialized")
                return
            
            sample_secrets = [
                {
                    "service": "GitHub",
                    "content": "ghp_example_token_123456789",
                    "tags": ["development", "version-control"],
                    "description": "GitHub Personal Access Token"
                },
                {
                    "service": "AWS",
                    "content": "AKIAIOSFODNN7EXAMPLE",
                    "tags": ["cloud", "infrastructure"],
                    "description": "AWS Access Key"
                },
                {
                    "service": "Stripe",
                    "content": "sk_test_example_placeholder_key_not_real",
                    "tags": ["payment", "production"],
                    "description": "Stripe API Key (example)"
                },
            ]
            
            added_count = 0
            for secret in sample_secrets:
                try:
                    self.vault.store(
                        content=secret["content"],
                        data_type="secret",
                        service=secret["service"],
                        tags=secret["tags"],
                        description=secret["description"]
                    )
                    added_count += 1
                except Exception as e:
                    logger.warning(f"Failed to add sample secret {secret['service']}: {e}")
            
            logger.info(f"Added {added_count} sample secrets")
            
            # Show success message
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"✅ Added {added_count} sample secrets!"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
            
        except Exception as e:
            logger.error(f"Error adding sample data: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error adding sample data: {str(e)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def show_landing_page(self):
        """Show landing page with large action buttons - always shown after login."""
        self.current_view = "landing"
        
        # Update sidebar selection to Home
        if hasattr(self, 'sidebar'):
            self.sidebar.selected_index = -1
            sidebar_container = self.sidebar.build()
        else:
            # Initialize sidebar if not exists
            self.sidebar = ModernSidebar(
                on_nav_change=self.on_nav_change,
                selected_index=-1
            )
            sidebar_container = self.sidebar.build()
        
        self.page.clean()
        
        # Get vault statistics
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            
            # Count by type
            # SECRET includes all secret types (SECRET, API_KEY, PASSWORD, TOKEN, CREDENTIAL)
            secrets_count = len([e for e in all_entries if e.entry_type in [EntryType.SECRET, EntryType.API_KEY, EntryType.PASSWORD, EntryType.TOKEN, EntryType.CREDENTIAL]])
            # Knowledge entries use EntryType.OTHER
            knowledge_count = len([e for e in all_entries if e.entry_type == EntryType.OTHER])
            # Count trained adapters (entries with training_status:completed tag)
            adapter_count = 0
            for entry in all_entries:
                if entry.tags:
                    for tag in entry.tags:
                        if tag == "training_status:completed":
                            adapter_count += 1
                            break
        except Exception as e:
            logger.warning(f"Error getting vault stats: {e}")
            secrets_count = 0
            knowledge_count = 0
            adapter_count = 0
        
        # User info - get email from session
        user_email = "User"
        if self.session_data:
            # Email is stored in session_data["user"]["email"]
            user_info = self.session_data.get("user", {})
            user_email = user_info.get("email") or self.session_data.get("user_email") or self.session_data.get("email") or "User"
        
        # Get component status
        ocr_ready = False
        qa_ready = False
        if hasattr(self, 'pdf_processor') and self.pdf_processor:
            ocr_ready = self.pdf_processor.smoldocling_available or self.pdf_processor.ollama_available
        if hasattr(self, 'qa_generator') and self.qa_generator:
            qa_status = self.qa_generator.get_qa_status()
            qa_ready = qa_status.get("status") == "ready"
        
        # Create landing page content - centered, clean design
        content = ft.Container(
            content=ft.Column(
                [
                    # Welcome header (simplified - logo is in sidebar)
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"Welcome back, {user_email}",
                                    size=20,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_PRIMARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=8),
                                ft.Text(
                                    "Quick actions and recent activity",
                                    size=14,
                                    color=LightTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        padding=ft.padding.only(bottom=32),
                        alignment=ft.alignment.center,
                    ),
                    
                    # Compact Action Buttons - 2x2 grid (smaller)
                    ft.Container(
                        content=ft.Column(
                            [
                                # First row
                                ft.Row(
                                    [
                                        self._create_large_action_button(
                                            "📚 Add Knowledge",
                                            "Upload PDF documents\nand train AI models",
                                            ft.Icons.UPLOAD_FILE_ROUNDED,
                                            LightTheme.ACCENT_PRIMARY,
                                            lambda e: (self.page.clean(), self.build_ui(), self.page.update(), setattr(self, 'current_view', 'knowledge') or self.load_secrets()),
                                        ),
                                        self._create_large_action_button(
                                            "🔑 View Secrets",
                                            f"{secrets_count} encrypted secrets\nstored securely",
                                            ft.Icons.LOCK_ROUNDED,
                                            LightTheme.ACCENT_SUCCESS,
                                            lambda e: (self.page.clean(), self.build_ui(), self.page.update()),
                                        ),
                                    ],
                                    spacing=24,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                ft.Container(height=16),
                                # Second row
                                ft.Row(
                                    [
                                        self._create_large_action_button(
                                            "🧠 Ask Documents",
                                            f"{adapter_count} trained adapters\nready to query" if adapter_count > 0 else "Train PDFs to unlock",
                                            ft.Icons.SMART_TOY_ROUNDED,
                                            LightTheme.ACCENT_SUCCESS if adapter_count > 0 else LightTheme.TEXT_MUTED,
                                            lambda e: (self.page.clean(), self.build_ui(), self.page.update(), self.show_knowledge_view()),
                                        ),
                                        self._create_large_action_button(
                                            "⚙️ Settings",
                                            "Configure components",
                                            ft.Icons.SETTINGS_ROUNDED,
                                            LightTheme.TEXT_SECONDARY,
                                            lambda e: (self.page.clean(), self.build_ui(), self.page.update(), self.show_settings()),
                                        ),
                                    ],
                                    spacing=24,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=ft.padding.symmetric(horizontal=32),
                    ),
                    
                    ft.Container(height=32),
                    
                    # Recent Activity Section
                    self._create_recent_activity_section(),
                    
                    ft.Container(height=32),
                    
                    # Quick stats footer - clickable links
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=ft.ElevatedButton(
                                        content=ft.Column(
                                            [
                                                ft.Text(
                                                    str(knowledge_count),
                                                    size=24,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=LightTheme.ACCENT_PRIMARY,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                                                ft.Text(
                                                    "Documents",
                                                    size=12,
                                                    color=LightTheme.TEXT_SECONDARY,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                                            ],
                                            spacing=4,
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        on_click=lambda e: (self.page.clean(), self.build_ui(), self.page.update(), setattr(self, 'current_view', 'knowledge') or self.load_secrets()),
                                        style=ft.ButtonStyle(
                                            bgcolor="transparent",
                                            color=LightTheme.TEXT_PRIMARY,
                                            elevation=0,
                                            overlay_color=LightTheme.ACCENT_PRIMARY + "10",
                                        ),
                                    ),
                                    padding=16,
                                    width=120,
                                ),
                                ft.VerticalDivider(width=1, color=LightTheme.BORDER_COLOR),
                                ft.Container(
                                    content=ft.ElevatedButton(
                                        content=ft.Column(
                                            [
                                                ft.Text(
                                                    str(secrets_count),
                                                    size=24,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=LightTheme.ACCENT_SUCCESS,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                                                ft.Text(
                                                    "Secrets",
                                                    size=12,
                                                    color=LightTheme.TEXT_SECONDARY,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                                            ],
                                            spacing=4,
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        on_click=lambda e: (self.page.clean(), self.build_ui(), self.page.update(), setattr(self, 'selected_type', 'secret') or setattr(self.type_filter, 'value', 'secret') or self.load_secrets()),
                                        style=ft.ButtonStyle(
                                            bgcolor="transparent",
                                            color=LightTheme.TEXT_PRIMARY,
                                            elevation=0,
                                            overlay_color=LightTheme.ACCENT_SUCCESS + "10",
                                        ),
                                    ),
                                    padding=16,
                                    width=120,
                                ),
                                ft.VerticalDivider(width=1, color=LightTheme.BORDER_COLOR),
                                ft.Container(
                                    content=ft.ElevatedButton(
                                        content=ft.Column(
                                            [
                                                ft.Icon(
                                                    ft.Icons.CHECK_CIRCLE_ROUNDED if (ocr_ready and qa_ready) else ft.Icons.WARNING_ROUNDED,
                                                    size=24,
                                                    color=LightTheme.ACCENT_SUCCESS if (ocr_ready and qa_ready) else LightTheme.ACCENT_WARNING,
                                                ),
                                                ft.Text(
                                                    "Ready" if (ocr_ready and qa_ready) else "Setup",
                                                    size=12,
                                                    color=LightTheme.ACCENT_SUCCESS if (ocr_ready and qa_ready) else LightTheme.ACCENT_WARNING,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                                            ],
                                            spacing=4,
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        ),
                                        on_click=lambda e: (self.page.clean(), self.build_ui(), self.page.update(), self.show_settings()),
                                        style=ft.ButtonStyle(
                                            bgcolor="transparent",
                                            color=LightTheme.TEXT_PRIMARY,
                                            elevation=0,
                                            overlay_color=LightTheme.ACCENT_WARNING + "10",
                                        ),
                                    ),
                                    padding=16,
                                    width=120,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        padding=ft.padding.symmetric(vertical=24, horizontal=32),
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=12,
                        margin=ft.margin.symmetric(horizontal=48),
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=48,
            expand=True,
            alignment=ft.alignment.center,
        )
        
        # Add sidebar and content in layout (if sidebar exists)
        if hasattr(self, 'sidebar'):
            self.page.add(
                ft.Row(
                    [
                        sidebar_container,
                        content,
                    ],
                    spacing=0,
                    expand=True,
                )
            )
        else:
            # Fallback: just add content if sidebar not initialized yet
            self.page.add(content)
        self.page.update()
    
    def _create_large_action_button(self, title: str, subtitle: str, icon: str, color: str, on_click) -> ft.Container:
        """Create a compact action button (smaller for better fit)."""
        return ft.Container(
            content=ft.ElevatedButton(
                content=ft.Row(
                    [
                        ft.Icon(
                            icon,
                            size=24,
                            color=color,
                        ),
                        ft.Container(width=12),
                        ft.Column(
                            [
                                ft.Text(
                                    title,
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_PRIMARY,
                                    text_align=ft.TextAlign.LEFT,
                                ),
                                ft.Text(
                                    subtitle,
                                    size=12,
                                    color=LightTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.LEFT,
                                ),
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                            tight=True,
                        ),
                    ],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                on_click=on_click,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.BG_ELEVATED,
                    color=LightTheme.TEXT_PRIMARY,
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                    elevation=1,
                    overlay_color=LightTheme.ACCENT_PRIMARY + "10",
                    animation_duration=200,
                ),
            ),
            width=240,
        )
    
    def _create_recent_activity_section(self) -> ft.Container:
        """Create recent activity section for Home screen."""
        try:
            # Initialize activity logger
            activity_logger = ActivityLogger(vault_path=str(self.vault_path))
            
            # Get recent activity (limit to 5 for Home screen)
            activities = activity_logger.get_recent_activity(limit=5)
            
            activity_items = []
            
            # Section header
            activity_items.append(
                ft.Row(
                    [
                        ft.Text(
                            "Recent Activity",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "View All",
                            icon=ft.Icons.ARROW_FORWARD_ROUNDED,
                            on_click=lambda e: (self.page.clean(), self.build_ui(), self.page.update(), setattr(self, 'current_view', 'activity') or self.load_secrets()),
                            style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                        ),
                    ],
                    spacing=0,
                )
            )
            
            activity_items.append(ft.Container(height=16))
            
            if not activities:
                # Empty state
                activity_items.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(
                                    ft.Icons.HISTORY_ROUNDED,
                                    size=40,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                                ft.Container(height=8),
                                ft.Text(
                                    "No recent activity",
                                    size=14,
                                    color=LightTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        padding=24,
                        alignment=ft.alignment.center,
                    )
                )
            else:
                # Show activity entries (compact)
                for activity in activities:
                    timestamp = activity.get('timestamp', '')
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        # Format: "2h ago" or "Yesterday" or date
                        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                        diff = now - dt
                        if diff.total_seconds() < 3600:
                            time_str = f"{int(diff.total_seconds() / 60)}m ago"
                        elif diff.total_seconds() < 86400:
                            time_str = f"{int(diff.total_seconds() / 3600)}h ago"
                        elif diff.days == 1:
                            time_str = "Yesterday"
                        else:
                            time_str = dt.strftime('%b %d')
                    except:
                        time_str = timestamp[:10] if len(timestamp) > 10 else timestamp
                    
                    tool_name = activity.get('tool_name', 'unknown')
                    app_name = activity.get('app_name', 'Unknown App')
                    granted = activity.get('granted', False)
                    query_preview = activity.get('query_preview', '')[:50]  # Truncate
                    
                    # Tool icon mapping
                    tool_icons = {
                        'vault_store': ft.Icons.ADD_CIRCLE_ROUNDED,
                        'vault_recall': ft.Icons.SEARCH_ROUNDED,
                        'vault_list_entries': ft.Icons.LIST_ROUNDED,
                        'vault_delete': ft.Icons.DELETE_ROUNDED,
                        'vault_stats': ft.Icons.BAR_CHART_ROUNDED,
                    }
                    tool_icon = tool_icons.get(tool_name, ft.Icons.SETTINGS_ROUNDED)
                    
                    # Status color
                    status_color = LightTheme.ACCENT_SUCCESS if granted else LightTheme.ACCENT_ERROR
                    
                    # Create compact activity item
                    activity_items.append(
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        tool_icon,
                                        size=20,
                                        color=LightTheme.TEXT_SECONDARY,
                                    ),
                                    ft.Container(width=12),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                tool_name.replace('vault_', '').replace('_', ' ').title(),
                                                size=13,
                                                weight=ft.FontWeight.W_500,
                                                color=LightTheme.TEXT_PRIMARY,
                                            ),
                                            ft.Text(
                                                query_preview or app_name,
                                                size=12,
                                                color=LightTheme.TEXT_SECONDARY,
                                            ),
                                        ],
                                        spacing=2,
                                        tight=True,
                                        expand=True,
                                    ),
                                    ft.Container(width=8),
                                    ft.Column(
                                        [
                                            ft.Icon(
                                                ft.Icons.CHECK_CIRCLE_ROUNDED if granted else ft.Icons.CANCEL_ROUNDED,
                                                size=16,
                                                color=status_color,
                                            ),
                                            ft.Text(
                                                time_str,
                                                size=11,
                                                color=LightTheme.TEXT_MUTED,
                                            ),
                                        ],
                                        spacing=2,
                                        horizontal_alignment=ft.CrossAxisAlignment.END,
                                        tight=True,
                                    ),
                                ],
                                spacing=0,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=ft.padding.symmetric(horizontal=12, vertical=10),
                            bgcolor=LightTheme.BG_ELEVATED,
                            border_radius=8,
                            margin=ft.margin.only(bottom=8),
                            on_click=lambda e: (self.page.clean(), self.build_ui(), self.page.update(), setattr(self, 'current_view', 'activity') or self.load_secrets()),
                        )
                    )
            
            return ft.Container(
                content=ft.Column(
                    activity_items,
                    spacing=0,
                    tight=True,
                ),
                padding=ft.padding.all(20),
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=12,
                margin=ft.margin.symmetric(horizontal=48),
            )
            
        except Exception as e:
            logger.error(f"Error creating recent activity section: {e}")
            return ft.Container(
                content=ft.Text(
                    "Unable to load activity",
                    size=14,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                padding=20,
            )
    
    def _create_stat_card(self, title: str, count: int, subtitle: str, icon: str) -> ft.Container:
        """Create a statistics card."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=24, color=LightTheme.ACCENT_PRIMARY),
                            ft.Text(
                                str(count),
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Text(title, size=14, weight=ft.FontWeight.W_500, color=LightTheme.TEXT_PRIMARY),
                    ft.Text(subtitle, size=12, color=LightTheme.TEXT_SECONDARY),
                ],
                spacing=4,
            ),
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=12,
            width=200,
        )
    
    def _create_action_button(self, title: str, subtitle: str, icon: str, on_click) -> ft.Container:
        """Create an action button."""
        return ft.Container(
            content=ft.ElevatedButton(
                content=ft.Column(
                    [
                        ft.Icon(icon, size=32, color=LightTheme.ACCENT_PRIMARY),
                        ft.Text(title, size=14, weight=ft.FontWeight.W_500),
                        ft.Text(subtitle, size=12, color=LightTheme.TEXT_SECONDARY),
                    ],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                on_click=on_click,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.BG_ELEVATED,
                    color=LightTheme.TEXT_PRIMARY,
                    padding=ft.padding.all(24),
                ),
            ),
            width=220,
        )
    
    def _create_status_indicator(self, title: str, status: str, color: str, icon: str) -> ft.Container:
        """Create a status indicator."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=20, color=color),
                    ft.Column(
                        [
                            ft.Text(title, size=14, weight=ft.FontWeight.W_500, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(status, size=12, color=color),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
            ),
            padding=16,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=8,
            width=250,
        )

    def initialize_vault(self):
        """Initialize vault after authentication."""
        # Show loading indicator if GUI is ready
        if hasattr(self, 'page') and self.page:
            try:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("🔐 Inicjalizacja Enclave Vault..."),
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    duration=3000,
                )
                self.page.snack_bar.open = True
                self.page.update()
            except Exception:
                pass  # Ignore if UI not ready
        
        # Load or generate master key
        if self.key_path.exists():
            with open(self.key_path, "rb") as f:
                self.master_key = f.read()
            logger.info("Loaded existing master key")
        else:
            self.master_key = os.urandom(32)
            with open(self.key_path, "wb") as f:
                f.write(self.master_key)
            os.chmod(self.key_path, 0o600)
            logger.info("Generated new master key")
        
        # Update progress
        if hasattr(self, 'page') and self.page:
            try:
                self.page.snack_bar.content.value = "🔐 Tworzenie vault..."
                self.page.update()
            except Exception:
                pass

        # Initialize vault
        self.vault = HybridVault(
            master_key=self.master_key,
            kv_db_path=str(self.db_path),
            enable_router_logging=False
        )
        
        # Initialize folder manager
        self.folder_manager = FolderManager(self.vault.kv_store)
        
        # Update progress
        if hasattr(self, 'page') and self.page:
            try:
                self.page.snack_bar.content.value = "☁️ Konfiguracja synchronizacji..."
                self.page.update()
            except Exception:
                pass
        
        # Initialize Supabase client for token refresh
        supabase_client = None
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
            if supabase_url and supabase_anon_key:
                from supabase import create_client
                supabase_client = create_client(supabase_url, supabase_anon_key)
        except Exception as e:
            logger.warning(f"Failed to create Supabase client for token refresh: {e}")
        
        # Initialize cloud sync service
        if self.session_data:
            try:
                self.cloud_sync = CloudSyncService(
                    backend_url=self.backend_url,
                    session_data=self.session_data,
                    vault=self.vault.kv_store,
                    supabase_client=supabase_client
                )
                logger.info("Cloud sync service initialized")
            except Exception as e:
                logger.error(f"Failed to initialize cloud sync: {e}")
                self.cloud_sync = None
            
            # Initialize Q&A generator and training manager
            # Note: QAGenerator uses Ollama locally (TinyLlama) for Q&A generation
            # TrainingManager uses backend API (backend manages RunPod credentials)
            try:
                self.qa_generator = QAGenerator()
                logger.info("Q&A generator initialized")
                
                # Check Q&A model status (MLX preferred, Ollama fallback)
                qa_status = self.qa_generator.get_qa_status()
                
                # Always prefer MLX on Apple Silicon if available (even if dependencies missing)
                if qa_status.get("mlx_available") or (platform.machine() == "arm64" and MLX_MODULE_AVAILABLE):
                    if qa_status.get("mlx_initialized"):
                        self._component_status["qa"]["status"] = "ready"
                        self._component_status["qa"]["message"] = "Ready (Optimized AI)"
                    else:
                        # MLX available but model not downloaded yet - show setup option
                        self._component_status["qa"]["status"] = "checking"
                        self._component_status["qa"]["message"] = "Setup required (download AI model)"
                elif qa_status.get("qa_model_available"):
                    self._component_status["qa"]["status"] = "ready"
                    self._component_status["qa"]["message"] = "Ready (Ollama TinyLlama)"
                else:
                    logger.info("Q&A model not available, will setup when needed")
                    self._component_status["qa"]["status"] = "checking"
                    self._component_status["qa"]["message"] = "Q&A model not downloaded"
                
                self.training_manager = TrainingManager(
                    backend_url=self.backend_url,
                    session_data=self.session_data,
                    supabase_client=supabase_client  # Pass client for token refresh
                )
                logger.info("Q&A generator and training manager initialized")
                
                # Initialize training queue for batch processing and folder watching
                self.training_queue = TrainingQueue(
                    vault_path=str(self.vault_path),
                    on_item_updated=self._on_queue_item_updated,
                    on_item_completed=self._on_queue_item_completed,
                    on_item_failed=self._on_queue_item_failed,
                )
                self.training_queue.set_train_function(self._train_document_for_queue)
                logger.info("Training queue initialized")
            except Exception as e:
                logger.error(f"Failed to initialize training services: {e}")
                self.qa_generator = None
                self.training_manager = None
                self.training_queue = None
                self._component_status["qa"]["status"] = "error"
                self._component_status["qa"]["message"] = f"Error: {str(e)}"
    
    def _ensure_qa_api_key_set(self):
        """
        Ensure RUNPOD_QA_API_KEY is set by default from RUNPOD_API_KEY.
        This ensures the QA generation endpoint works by default when RUNPOD_API_KEY is configured.
        """
        runpod_api_key = os.getenv("RUNPOD_API_KEY")
        qa_api_key = os.getenv("RUNPOD_QA_API_KEY")
        
        if not qa_api_key and runpod_api_key:
            os.environ["RUNPOD_QA_API_KEY"] = runpod_api_key
            logger.info("Set RUNPOD_QA_API_KEY to RUNPOD_API_KEY by default (QA endpoint will be used)")
        elif qa_api_key:
            logger.debug(f"RUNPOD_QA_API_KEY already set (explicit value)")
        elif not runpod_api_key:
            logger.debug("RUNPOD_API_KEY not set - QA generation will use local MLX/Ollama fallback")

    def sync_from_cloud(self):
        """Sync entries from cloud on login."""
        if not self.cloud_sync:
            return
        
        def _sync():
            try:
                cloud_entries = self.cloud_sync.fetch_from_cloud()
                if cloud_entries:
                    # Merge with local entries (cloud wins on conflicts)
                    result = self.cloud_sync.merge_entries(cloud_entries, conflict_resolution="cloud")
                    logger.info(f"Synced {result.get('merged', 0)} entries from cloud")
            except Exception as e:
                logger.error(f"Error syncing from cloud: {e}")
        
        # Run in background thread
        thread = threading.Thread(target=_sync, daemon=True)
        thread.start()

    def logout(self):
        """Logout user."""
        # Clear session
        AuthScreen.clear_session()
        self.session_data = None
        self.vault = None

        # Show auth screen
        self.show_auth_screen()
    
    def _force_logout_and_close_dialog(self, dialog):
        """Force logout and close any open dialog (used for session expiration errors)."""
        # Close the dialog first
        dialog.open = False
        self.page.update()
        
        # Show a snackbar explaining the re-login
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text("Session expired. Please log in again to continue."),
            bgcolor=LightTheme.ACCENT_PRIMARY,
        )
        self.page.snack_bar.open = True
        self.page.update()
        
        # Perform logout
        self.logout()

    def check_backend_connectivity(self):
        """Check Compute Pipeline (backend API) connectivity."""
        # Run in background thread
        def _check():
            try:
                response = requests.get(
                    f"{self.backend_url}/health",
                    timeout=5.0
                )
                if response.status_code == 200:
                    self.backend_status = "connected"
                else:
                    self.backend_status = "error"
            except Exception as e:
                self.backend_status = "disconnected"

            self.last_check = datetime.now()

            # Update UI
            if hasattr(self, 'compute_pipeline_icon'):
                self.update_compute_pipeline_icon()
                self.page.update()

        thread = threading.Thread(target=_check, daemon=True)
        thread.start()

    def update_compute_pipeline_icon(self):
        """Update the Compute Pipeline (backend) icon based on status."""
        if not hasattr(self, 'compute_pipeline_icon'):
            return
        
        if self.backend_status == "connected":
            self.compute_pipeline_icon.icon = ft.Icons.SCIENCE_ROUNDED
            self.compute_pipeline_icon.icon_color = LightTheme.ACCENT_SUCCESS
            self.compute_pipeline_icon.tooltip = "Compute Pipeline: Connected ✓"
        elif self.backend_status == "disconnected":
            self.compute_pipeline_icon.icon = ft.Icons.SCIENCE_ROUNDED
            self.compute_pipeline_icon.icon_color = LightTheme.ACCENT_ERROR
            self.compute_pipeline_icon.tooltip = "Compute Pipeline: Disconnected"
        else:
            self.compute_pipeline_icon.icon = ft.Icons.SCIENCE_ROUNDED
            self.compute_pipeline_icon.icon_color = LightTheme.ACCENT_WARNING
            self.compute_pipeline_icon.tooltip = "Compute Pipeline: Checking..."

    def build_ui(self):
        """Build the main UI."""
        # Clear page before building to prevent duplicates
        self.page.clean()
        
        # Create Compute Pipeline (backend) connectivity indicator
        self.compute_pipeline_icon = ft.IconButton(
            icon=ft.Icons.SCIENCE_ROUNDED,
            icon_color=LightTheme.TEXT_MUTED,
            tooltip="Compute Pipeline: Checking...",
            on_click=lambda _: self.check_backend_connectivity(),
            icon_size=20
        )

        # User info for app bar
        user_email = self.session_data.get("user", {}).get("email", "User") if self.session_data else "User"

        # Modern app bar with glassmorphism effect
        self.page.appbar = ft.AppBar(
            title=ft.Row([
                ft.Container(
                    content=ft.Text("🔐", size=24),
                    margin=ft.margin.only(right=8),
                ),
                ft.Text(
                    "Enclave",
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
            ]),
            center_title=False,
            bgcolor=LightTheme.GLASS_BG,
            elevation=0,
            actions=[
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.PERSON_ROUNDED, size=16, color=LightTheme.TEXT_SECONDARY),
                        ft.Text(user_email, size=12, color=LightTheme.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                    ], spacing=5),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                ),
                ft.Container(width=8),
                ft.VerticalDivider(width=1, color=LightTheme.BORDER_COLOR),
                ft.Container(width=8),
                self.compute_pipeline_icon,
                ft.Container(width=8),
                ft.VerticalDivider(width=1, color=LightTheme.BORDER_COLOR),
                ft.Container(width=8),
                ft.PopupMenuButton(
                    icon=ft.Icons.ADD_CIRCLE_ROUNDED,
                    tooltip="Add Entry",
                    icon_size=28,
                    icon_color=LightTheme.ACCENT_PRIMARY,
                    items=[
                        ft.PopupMenuItem(
                            text="Add Secret",
                            icon=ft.Icons.LOCK_ROUNDED,
                            on_click=lambda e: self.show_add_dialog(e, default_type="secret"),
                        ),
                        ft.PopupMenuItem(
                            text="Add Knowledge",
                            icon=ft.Icons.LIGHTBULB_ROUNDED,
                            on_click=lambda e: self.show_add_dialog(e, default_type="knowledge"),
                        ),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.CREATE_NEW_FOLDER_ROUNDED,
                    tooltip="New Folder",
                    on_click=lambda _: self._show_create_folder_dialog(),
                    icon_size=28,
                    icon_color=LightTheme.ACCENT_PRIMARY,
                ),
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED,
                    tooltip="Refresh",
                    on_click=lambda _: self.load_secrets(),
                    icon_size=28,
                    icon_color=LightTheme.TEXT_SECONDARY,
                ),
                ft.IconButton(
                    ft.Icons.LOGOUT_ROUNDED,
                    tooltip="Logout",
                    on_click=lambda _: self.logout(),
                    icon_size=28,
                    icon_color=LightTheme.ACCENT_ERROR,
                ),
            ],
        )

        # Start initial connectivity check
        self.check_backend_connectivity()

        # Sleek search bar
        self.search_field = ft.TextField(
            hint_text="Search secrets...",
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=8,
            filled=True,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            color=LightTheme.TEXT_PRIMARY,
            text_size=LightTheme.FONT_SIZE_BASE,
            on_change=self.on_search_change,
            expand=True,
            height=LightTheme.INPUT_HEIGHT,
        )

        # Sleek filter dropdown
        self.type_filter = ft.Dropdown(
            width=120,
            value="all",
            options=[
                ft.dropdown.Option("all", "All"),
                ft.dropdown.Option("secret", "Secrets"),
                ft.dropdown.Option("knowledge", "Knowledge"),
            ],
            on_change=self.on_filter_change,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            color=LightTheme.TEXT_PRIMARY,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            text_size=LightTheme.FONT_SIZE_BASE,
        )

        # Search row
        search_row = ft.Row(
            [
                self.search_field,
                self.type_filter,
            ],
            spacing=LightTheme.SPACING_MD,
        )

        # Secrets list
        self.secrets_list = ft.Column(
            spacing=LightTheme.SPACING_MD,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Stats row
        self.stats_text = ft.Text("", size=LightTheme.FONT_SIZE_XS, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500)

        # Modern sidebar navigation
        self.sidebar = ModernSidebar(
            on_nav_change=self.on_nav_change,
            selected_index=-1  # Start with Home selected
        )
        sidebar_container = self.sidebar.build()

        # Main content with sleek styling
        main_content = ft.Container(
            content=ft.Column(
                [
                    search_row,
                    ft.Container(height=LightTheme.SPACING_LG),
                    self.secrets_list,
                    ft.Container(height=LightTheme.SPACING_LG),
                    self.stats_text,
                ],
                spacing=0,
                expand=True,
            ),
            padding=ft.padding.all(LightTheme.PADDING_XL),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        # Layout with modern divider
        self.page.add(
            ft.Row(
                [
                    sidebar_container,
                    main_content,
                ],
                spacing=0,
                expand=True,
            )
        )

        # Load initial data
        self.load_secrets()

    def load_secrets(self):
        """Load secrets from vault."""
        # Store header if we're in knowledge view
        header_container = None
        if self.selected_type == "knowledge" and len(self.secrets_list.controls) > 0:
            # Check if first item is the knowledge header
            first_item = self.secrets_list.controls[0]
            if isinstance(first_item, ft.Container) and isinstance(first_item.content, ft.Column):
                col_content = first_item.content.controls
                if col_content and isinstance(col_content[0], ft.Row):
                    row_content = col_content[0].controls
                    if row_content and isinstance(row_content[0], ft.Text) and "Knowledge Base" in str(row_content[0].value):
                        header_container = first_item
        
        self.secrets_list.controls.clear()
        
        # Restore header if we're in knowledge view
        if header_container:
            self.secrets_list.controls.append(header_container)

        # Get all entries
        from advanced_vault.encrypted_kv import QueryFilter, EntryType

        # Create filter based on selected type
        query_filter = QueryFilter()
        if self.selected_type == "secret":
            query_filter.entry_type = EntryType.SECRET
        # Note: "knowledge" entries are not yet stored in KV (Layer 2 not implemented)
        elif self.selected_type == "knowledge":
            # For knowledge, we still search all entries but filter by data_type in tags or description
            pass

        result = self.vault.kv_store.search(query_filter)

        # Convert EncryptedEntry objects to dicts and group by folder
        entries = []
        folders_dict = {}  # folder_name -> [entries]
        root_entries = []  # Entries without folder
        
        for entry in result:
            # Skip folder entries themselves
            if entry.entry_type == EntryType.FOLDER:
                continue
            
            entry_dict = {
                'id': entry.id,
                'service': entry.service,
                'data_type': 'knowledge' if ("knowledge" in entry.tags or "pdf" in entry.tags or "document" in entry.tags) else 'secret',
                'tags': entry.tags,
                'timestamp': entry.updated_at.timestamp() if entry.updated_at else 0,
                'description': entry.description,
                'folder': entry.folder  # Include folder name
            }
            
            # Filter knowledge entries if in knowledge view
            if self.selected_type == "knowledge":
                if entry_dict['data_type'] == 'knowledge':
                    if entry.folder:
                        if entry.folder not in folders_dict:
                            folders_dict[entry.folder] = []
                        folders_dict[entry.folder].append(entry_dict)
                    else:
                        root_entries.append(entry_dict)
            elif self.selected_type == "secret":
                if entry_dict['data_type'] == 'secret':
                    if entry.folder:
                        if entry.folder not in folders_dict:
                            folders_dict[entry.folder] = []
                        folders_dict[entry.folder].append(entry_dict)
                    else:
                        root_entries.append(entry_dict)
            else:  # "all"
                if entry.folder:
                    if entry.folder not in folders_dict:
                        folders_dict[entry.folder] = []
                    folders_dict[entry.folder].append(entry_dict)
                else:
                    root_entries.append(entry_dict)

        # Filter by search query
        if self.search_query:
            def filter_entry(e):
                return (
                    self.search_query.lower() in e.get('service', '').lower()
                    or self.search_query.lower() in ' '.join(e.get('tags', [])).lower()
                )
            
            root_entries = [e for e in root_entries if filter_entry(e)]
            for folder_name in list(folders_dict.keys()):
                folders_dict[folder_name] = [e for e in folders_dict[folder_name] if filter_entry(e)]
                if not folders_dict[folder_name]:
                    del folders_dict[folder_name]

        # Sort entries by timestamp (newest first)
        root_entries.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        for folder_name in folders_dict:
            folders_dict[folder_name].sort(key=lambda x: x.get('timestamp', 0), reverse=True)

        # Create UI: folders first, then root entries
        if folders_dict or root_entries:
            # Add folder sections
            if self.folder_manager:
                folders = self.folder_manager.list_folders()
                folder_names = {f["name"]: f for f in folders}
                
                for folder_name in sorted(folders_dict.keys()):
                    if folder_name in folder_names:
                        folder_info = folder_names[folder_name]
                        # Create collapsible folder section
                        folder_section = self._create_folder_section(folder_info, folders_dict[folder_name])
                        self.secrets_list.controls.append(folder_section)
            
            # Add root entries
            for entry in root_entries:
                card = self.create_secret_card(entry)
                self.secrets_list.controls.append(card)
        else:
            # Only show empty message if not in knowledge view (knowledge view has its own header)
            if self.selected_type != "knowledge":
                # Sleek empty state
                self.secrets_list.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(
                                    content=ft.Icon(
                                        ft.Icons.LOCK_OPEN_ROUNDED,
                                        size=48,
                                        color=LightTheme.TEXT_MUTED,
                                    ),
                                    padding=16,
                                    border_radius=12,
                                    bgcolor=LightTheme.BG_ELEVATED,
                                ),
                                ft.Container(height=LightTheme.SPACING_LG),
                                ft.Text(
                                    "Your vault is empty",
                                    size=LightTheme.FONT_SIZE_LG,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Container(height=LightTheme.SPACING_SM),
                                ft.Text(
                                    "Add your first secret to get started",
                                    size=LightTheme.FONT_SIZE_BASE,
                                    color=LightTheme.TEXT_SECONDARY,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=LightTheme.SPACING_XL),
                                ft.ElevatedButton(
                                    "Add Secret",
                                    icon=ft.Icons.ADD_ROUNDED,
                                    on_click=lambda e: self.show_add_dialog(e, default_type="secret"),
                                    style=ft.ButtonStyle(
                                        bgcolor=LightTheme.ACCENT_PRIMARY,
                                        color="white",
                                        shape=ft.RoundedRectangleBorder(radius=8),
                                        padding=ft.padding.symmetric(horizontal=LightTheme.PADDING_LG, vertical=LightTheme.PADDING_SM),
                                    ),
                                    height=LightTheme.BUTTON_HEIGHT_MD,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        alignment=ft.alignment.center,
                        expand=True,
                        padding=40,
                    )
                )

        # Update stats
        stats = self.vault.get_stats()
        layer1 = stats['layer_1']
        self.stats_text.value = f"📊 {layer1['total_entries']} entries | {len(layer1['services'])} services"

        self.page.update()

    def create_secret_card(self, entry):
        """Create a sleek card with compact styling."""
        service = entry.get('service', 'Unknown')
        data_type = entry.get('data_type', 'secret')
        tags = entry.get('tags', [])

        # Extract training status from tags FIRST (needed for icon determination)
        training_status = None
        training_job_id = None
        training_key = None
        for tag in tags:
            if tag.startswith("training_status:"):
                training_status = tag.split(":", 1)[1]
            elif tag.startswith("training_job:"):
                training_job_id = tag.split(":", 1)[1]
            elif tag.startswith("training_key:"):
                training_key = tag.split(":", 1)[1]

        # Determine icon based on type and training status
        if data_type == 'secret':
            entry_icon = ft.Icons.KEY_ROUNDED
            icon_color = LightTheme.TEXT_PRIMARY
            icon_bg_color = LightTheme.BG_ELEVATED
        elif training_status == "completed":
            entry_icon = ft.Icons.SMART_TOY_ROUNDED
            icon_color = "#FFFFFF"
            icon_bg_color = LightTheme.ACCENT_SUCCESS
        elif training_status in ["pending", "training"]:
            entry_icon = ft.Icons.MODEL_TRAINING_ROUNDED
            icon_color = LightTheme.ACCENT_WARNING
            icon_bg_color = LightTheme.BG_ELEVATED
        else:
            entry_icon = ft.Icons.LIGHTBULB_ROUNDED
            icon_color = LightTheme.TEXT_PRIMARY
            icon_bg_color = LightTheme.BG_ELEVATED
        
        # Compact icon with subtle background
        icon_bg = ft.Container(
            content=ft.Icon(
                entry_icon,
                color=icon_color,
                size=LightTheme.ICON_SIZE_SM
            ),
            width=36,
            height=36,
            border_radius=8,
            bgcolor=icon_bg_color,
            alignment=ft.alignment.center,
        )
        
        # Training status badge
        status_badge = None
        if training_status:
            status_colors = {
                "pending": LightTheme.ACCENT_WARNING,
                "training": LightTheme.ACCENT_PRIMARY,
                "completed": LightTheme.ACCENT_SUCCESS,
                "failed": LightTheme.ACCENT_ERROR
            }
            status_icons = {
                "pending": ft.Icons.HOURGLASS_EMPTY_ROUNDED,
                "training": ft.Icons.MODEL_TRAINING_ROUNDED,
                "completed": ft.Icons.SMART_TOY_ROUNDED,
                "failed": ft.Icons.ERROR_ROUNDED
            }
            status_labels = {
                "pending": "Training Queued",
                "training": "Training...",
                "completed": "🧠 AI Ready",
                "failed": "Training Failed"
            }
            status_color = status_colors.get(training_status, LightTheme.TEXT_MUTED)
            status_icon = status_icons.get(training_status, ft.Icons.INFO_ROUNDED)
            status_label = status_labels.get(training_status, training_status.title())
            
            # Make "completed" badge more prominent
            if training_status == "completed":
                status_badge = ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(status_icon, size=12, color="#FFFFFF"),
                            ft.Text(
                                status_label,
                                size=LightTheme.FONT_SIZE_XS,
                                weight=ft.FontWeight.W_600,
                                color="#FFFFFF"
                            )
                        ],
                        spacing=4,
                        tight=True
                    ),
                    bgcolor=status_color,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=12,
                )
            else:
                status_badge = ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(status_icon, size=10, color=status_color),
                            ft.Text(
                                status_label,
                                size=LightTheme.FONT_SIZE_XS,
                                weight=ft.FontWeight.W_500,
                                color=status_color
                            )
                        ],
                        spacing=3,
                        tight=True
                    ),
                    bgcolor=status_color + "15",
                    padding=ft.padding.symmetric(horizontal=6, vertical=3),
                    border_radius=6,
                    border=ft.border.all(1, status_color + "30"),
                )

        # Sleek tag chips
        regular_tags = [t for t in tags if not t.startswith("training_")]
        tag_chips = [
            ft.Container(
                content=ft.Text(tag, size=LightTheme.FONT_SIZE_XS, weight=ft.FontWeight.W_500, color=LightTheme.TEXT_SECONDARY),
                bgcolor=LightTheme.BG_HOVER,
                padding=ft.padding.symmetric(horizontal=6, vertical=3),
                border_radius=6,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )
            for tag in regular_tags[:3]  # Show max 3 tags
        ]
        
        # Add status badge to tag row if present
        tag_row_items = tag_chips.copy()
        if status_badge:
            tag_row_items.insert(0, status_badge)

        # Build action buttons with sleek styling
        action_buttons = [
            ft.IconButton(
                ft.Icons.VISIBILITY_ROUNDED,
                tooltip="View",
                on_click=lambda _, e=entry: self.view_secret(e),
                icon_color=LightTheme.TEXT_SECONDARY,
                icon_size=LightTheme.ICON_SIZE_SM,
            ),
        ]
        
        # Add "Train Model" button for PDF/knowledge entries
        if "pdf" in tags or "knowledge" in tags or "document" in tags:
            action_buttons.append(
                ft.IconButton(
                    ft.Icons.TRAIN_ROUNDED,
                    tooltip="Train Model",
                    on_click=lambda _, e=entry: self._offer_training_from_entry(e),
                    icon_color=LightTheme.ACCENT_WARNING,
                    icon_size=LightTheme.ICON_SIZE_SM,
                )
            )
        
        # Add "Ask" button for completed training entries
        if training_status == "completed" and training_job_id and training_key:
            action_buttons.append(
                ft.IconButton(
                    ft.Icons.QUESTION_ANSWER_ROUNDED,
                    tooltip="Ask Questions",
                    on_click=lambda _, job_id=training_job_id, key=training_key, svc=service: self._open_ask_dialog(job_id, key, svc),
                    icon_color=LightTheme.ACCENT_SUCCESS,
                    icon_size=LightTheme.ICON_SIZE_SM,
                )
            )
        
        action_buttons.append(
            ft.IconButton(
                ft.Icons.DELETE_OUTLINE_ROUNDED,
                tooltip="Delete",
                on_click=lambda _, e=entry: self.delete_secret(e),
                icon_color=LightTheme.ACCENT_ERROR,
                icon_size=LightTheme.ICON_SIZE_SM,
            )
        )

        # Sleek card
        return ft.Container(
            content=ft.Container(
                content=ft.Row(
                    [
                        icon_bg,
                        ft.Container(width=LightTheme.SPACING_MD),
                        ft.Column(
                            [
                                ft.Text(
                                    service,
                                    weight=ft.FontWeight.W_600,
                                    size=LightTheme.FONT_SIZE_MD,
                                    color=LightTheme.TEXT_PRIMARY
                                ),
                                ft.Container(height=4),
                                ft.Row(tag_row_items, spacing=LightTheme.SPACING_XS) if tag_row_items else ft.Container(),
                            ],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Row(
                            action_buttons,
                            spacing=LightTheme.SPACING_XS,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=LightTheme.CARD_PADDING,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=LightTheme.CARD_BORDER_RADIUS,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
            margin=ft.margin.only(bottom=LightTheme.SPACING_MD),
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

    def show_add_dialog(self, e, default_type: str = None):
        """Show add secret/knowledge dialog."""
        try:
            logger.debug("Opening add dialog")

            # Determine default type based on current view if not provided
            if default_type is None:
                if hasattr(self, 'selected_type') and self.selected_type == "knowledge":
                    default_type = "knowledge"
                else:
                    default_type = "secret"

            # Close any existing dialogs in overlay
            for overlay_item in list(self.page.overlay):
                if isinstance(overlay_item, ft.AlertDialog) and overlay_item.open:
                    overlay_item.open = False

            service_field = ft.TextField(
                label="Service (e.g., stripe, github)",
                border_radius=8,
                bgcolor=LightTheme.BG_ELEVATED,
                border_color=LightTheme.BORDER_COLOR,
                focused_border_color=LightTheme.ACCENT_PRIMARY,
            )
            content_field = ft.TextField(
                label="Secret / Knowledge",
                password=True,
                multiline=True,
                border_radius=8,
                bgcolor=LightTheme.BG_ELEVATED,
                border_color=LightTheme.BORDER_COLOR,
                focused_border_color=LightTheme.ACCENT_PRIMARY,
            )
            tags_field = ft.TextField(
                label="Tags (comma-separated)",
                hint_text="payment, production",
                border_radius=8,
                bgcolor=LightTheme.BG_ELEVATED,
                border_color=LightTheme.BORDER_COLOR,
                focused_border_color=LightTheme.ACCENT_PRIMARY,
            )
            description_field = ft.TextField(
                label="Description (optional)",
                multiline=True,
                border_radius=8,
                bgcolor=LightTheme.BG_ELEVATED,
                border_color=LightTheme.BORDER_COLOR,
                focused_border_color=LightTheme.ACCENT_PRIMARY,
            )

            type_radio = ft.RadioGroup(
                content=ft.Row([
                    ft.Radio(value="secret", label="Secret"),
                    ft.Radio(value="knowledge", label="Knowledge"),
                ]),
                value=default_type
            )
            
            # Folder dropdown (if folders exist)
            folder_dropdown = None
            if self.folder_manager:
                folders = self.folder_manager.list_folders()
                if folders:
                    folder_options = [ft.dropdown.Option("", "None (Root)")]
                    for folder in folders:
                        folder_options.append(ft.dropdown.Option(folder["name"], folder["name"]))
                    
                    folder_dropdown = ft.Dropdown(
                        label="Folder (optional)",
                        options=folder_options,
                        value="",  # Default to root
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_color=LightTheme.BORDER_COLOR,
                        focused_border_color=LightTheme.ACCENT_PRIMARY,
                    )

            def close_dialog():
                if dialog:
                    dialog.open = False
                    self.page.update()

            def add_entry(e):
                if not service_field.value or not content_field.value:
                    service_field.error_text = "Required" if not service_field.value else None
                    content_field.error_text = "Required" if not content_field.value else None
                    self.page.update()
                    return

                # Parse tags
                tags = [t.strip() for t in tags_field.value.split(',')] if tags_field.value else []
                
                # Get folder name
                folder_name = folder_dropdown.value if folder_dropdown and folder_dropdown.value else None
                
                # If folder is specified, check if it's unlocked
                if folder_name and self.folder_manager:
                    if not self.folder_manager.is_folder_unlocked(folder_name):
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"⚠️ Folder '{folder_name}' is locked. Please unlock it first."),
                            bgcolor=LightTheme.ACCENT_WARNING,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                        return

                # Store in vault
                entry_id = self.vault.kv_store.put(
                    service=service_field.value,
                    secret_value=content_field.value,
                    entry_type=EntryType.SECRET if type_radio.value == "secret" else EntryType.OTHER,
                    tags=tags,
                    description=description_field.value or None,
                    folder=folder_name
                )

                # Sync to cloud in background (non-critical)
                if self.cloud_sync:
                    try:
                        self.cloud_sync.sync_entry_background(entry_id)
                    except Exception as sync_err:
                        logger.warning(f"Cloud sync failed (non-critical): {sync_err}")
                        # Don't fail the operation - local storage succeeded

                # Show success snackbar
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ Added {service_field.value}"),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                )
                self.page.snack_bar.open = True

                close_dialog()
                self.load_secrets()

            # Create dialog content column with all fields
            dialog_fields = [
                type_radio,
                service_field,
                content_field,
                tags_field,
            ]
            
            if folder_dropdown:
                dialog_fields.append(folder_dropdown)
            
            dialog_fields.append(description_field)
            
            dialog_content = ft.Column(
                dialog_fields,
                spacing=15,
                tight=True,
                width=500,
            )
            
            # Modern dialog styling
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Add Entry",
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                bgcolor=LightTheme.BG_ELEVATED,
                content=dialog_content,
                actions=[
                    ft.TextButton(
                        "Cancel",
                        on_click=lambda _: close_dialog(),
                        style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                    ),
                    ft.Container(
                        content=ft.ElevatedButton(
                            "Add",
                            icon=ft.Icons.ADD_ROUNDED,
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            on_click=add_entry
                        ),
                        gradient=LightTheme.get_gradient(LightTheme.GRADIENT_PRIMARY),
                        border_radius=8,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            
            # Add dialog to overlay (the correct way in Flet)
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()

        except Exception as ex:
            logger.error(f"Error opening add dialog: {ex}", exc_info=True)
            user_msg, _ = make_user_friendly(str(ex), context="upload")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def view_secret(self, entry):
        """Show secret details."""
        service = entry.get('service', 'Unknown')

        # Retrieve secret
        secret_value = self.vault.kv_store.get(service)
        result = {"result": secret_value} if secret_value else {"error": "Secret not found"}

        if result.get('error'):
            user_msg, _ = make_user_friendly(result['error'], context="vault")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
            return

        content = result.get('result', '')
        data_type = entry.get('data_type', 'secret')
        tags = entry.get('tags', [])
        description = entry.get('description', 'None')
        
        # Check if this is a PDF entry
        is_pdf = "pdf" in tags or "document" in tags
        
        # Extract file path from description if it's a PDF
        file_path = None
        if is_pdf and description:
            # Look for "Path: " in description
            if "Path: " in description:
                path_part = description.split("Path: ")[1].split(" | ")[0] if " | " in description else description.split("Path: ")[1]
                file_path = path_part.strip()
        
        # Check if file still exists
        file_exists = file_path and Path(file_path).exists() if file_path else False
        
        # Build content widget
        if is_pdf and file_exists:
            # PDF preview mode
            content_widgets = [
                ft.Text(
                    f"📄 PDF Document",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                ft.Text(
                    f"File Path: {file_path}",
                    size=12,
                    color=LightTheme.TEXT_MUTED,
                    selectable=True,
                ),
                ft.Container(height=12),
                ft.ElevatedButton(
                    "📖 Open PDF",
                    icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                    on_click=lambda _: self._open_pdf_file(file_path),
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                ),
                ft.Container(height=8),
                ft.Text(
                    "Content (Base64 encoded)",
                    size=12,
                    color=LightTheme.TEXT_MUTED,
                    weight=ft.FontWeight.W_500,
                ),
                ft.TextField(
                    value=content[:200] + "..." if len(content) > 200 else content,
                    multiline=True,
                    read_only=True,
                    min_lines=3,
                    max_lines=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_color=LightTheme.BORDER_COLOR,
                    color=LightTheme.TEXT_PRIMARY,
                    border_radius=8,
                ),
            ]
        else:
            # Regular content mode
            content_widgets = [
                ft.TextField(
                    value=content,
                    multiline=True,
                    read_only=True,
                    min_lines=3,
                    max_lines=10,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_color=LightTheme.BORDER_COLOR,
                    color=LightTheme.TEXT_PRIMARY,
                    border_radius=8,
                ),
            ]
            
            if is_pdf and file_path:
                # File path exists but file doesn't
                content_widgets.insert(0, ft.Text(
                    f"⚠️ File not found: {file_path}",
                    size=12,
                    color=LightTheme.ACCENT_WARNING,
                ))
                content_widgets.insert(1, ft.Container(height=8))

        content_field = ft.Column(content_widgets, spacing=8)

        def copy_to_clipboard(e):
            self.page.set_clipboard(content)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("📋 Copied to clipboard"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()

        def close_dialog():
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text(
                f"🔐 {service}",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(f"Type: {data_type.title()}", size=12, color=LightTheme.TEXT_MUTED),
                        ft.Text(f"Tags: {', '.join(tags) if tags else 'None'}", size=12, color=LightTheme.TEXT_MUTED),
                        ft.Text(f"Description: {description}", size=12, color=LightTheme.TEXT_MUTED),
                        ft.Divider(color=LightTheme.BORDER_COLOR),
                        content_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=600 if is_pdf else 500,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: close_dialog(),
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Copy",
                        icon=ft.Icons.COPY_ROUNDED,
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                        on_click=copy_to_clipboard
                    ),
                    gradient=LightTheme.get_gradient(LightTheme.GRADIENT_PRIMARY),
                    border_radius=8,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def delete_secret(self, entry):
        """Delete a secret."""
        service = entry.get('service', 'Unknown')

        def confirm_delete(e):
            self.vault.kv_store.delete(service)

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"🗑️ Deleted {service}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True

            dialog.open = False
            self.page.update()
            self.load_secrets()

        def close_dialog():
            dialog.open = False
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text(
                "Confirm Delete",
                color=LightTheme.TEXT_PRIMARY,
            ),
            content=ft.Text(
                f"Are you sure you want to delete '{service}'? This cannot be undone.",
                color=LightTheme.TEXT_SECONDARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: close_dialog(),
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "Delete",
                    bgcolor=LightTheme.ACCENT_ERROR,
                    color="white",
                    on_click=confirm_delete
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _open_pdf_file(self, file_path: str):
        """Open PDF file in default system viewer."""
        import subprocess
        import platform
        
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path], check=True)
            elif platform.system() == "Windows":
                os.startfile(file_path)
            else:  # Linux
                subprocess.run(["xdg-open", file_path], check=True)
        except Exception as e:
            logger.error(f"Failed to open PDF: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Failed to open PDF: {str(e)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def _create_folder_section(self, folder_info: dict, entries: list) -> ft.Container:
        """Create a collapsible folder section."""
        folder_name = folder_info["name"]
        is_unlocked = folder_info.get("is_unlocked", False)
        has_password = folder_info.get("has_password", False)
        
        # Track expanded state
        is_expanded_ref = {"value": is_unlocked}  # Start expanded if unlocked
        
        # Folder header
        def toggle_folder(e):
            if not is_unlocked and has_password:
                # Need to unlock folder first
                self._show_unlock_folder_dialog(folder_name)
                return
            
            is_expanded_ref["value"] = not is_expanded_ref["value"]
            
            # Update icon and visibility
            if is_expanded_ref["value"]:
                expand_icon.icon = ft.Icons.EXPAND_LESS_ROUNDED
                entries_container.visible = True
            else:
                expand_icon.icon = ft.Icons.EXPAND_MORE_ROUNDED
                entries_container.visible = False
            
            self.page.update()
        
        expand_icon = ft.Icon(
            ft.Icons.EXPAND_LESS_ROUNDED if is_expanded_ref["value"] else ft.Icons.EXPAND_MORE_ROUNDED,
            size=LightTheme.ICON_SIZE_SM,
            color=LightTheme.TEXT_SECONDARY,
        )
        
        lock_icon = None
        if has_password:
            if is_unlocked:
                lock_icon = ft.Icon(
                    ft.Icons.LOCK_OPEN_ROUNDED,
                    size=LightTheme.ICON_SIZE_XS,
                    color=LightTheme.ACCENT_SUCCESS,
                )
            else:
                lock_icon = ft.Icon(
                    ft.Icons.LOCK_ROUNDED,
                    size=LightTheme.ICON_SIZE_XS,
                    color=LightTheme.ACCENT_WARNING,
                )
        
        folder_header = ft.Container(
            content=ft.Row(
                [
                    expand_icon,
                    ft.Icon(
                        ft.Icons.FOLDER_ROUNDED,
                        size=LightTheme.ICON_SIZE_SM,
                        color=LightTheme.ACCENT_PRIMARY,
                    ),
                    ft.Text(
                        folder_name,
                        weight=ft.FontWeight.W_600,
                        size=LightTheme.FONT_SIZE_MD,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                    lock_icon,
                    ft.Container(width=LightTheme.SPACING_SM),
                    ft.Text(
                        f"({len(entries)} items)",
                        size=LightTheme.FONT_SIZE_XS,
                        color=LightTheme.TEXT_MUTED,
                    ),
                ],
                spacing=LightTheme.SPACING_SM,
            ),
            padding=LightTheme.PADDING_SM,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=LightTheme.CARD_BORDER_RADIUS,
            on_click=toggle_folder,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )
        
        # Entries container (initially visible if unlocked)
        entries_container = ft.Container(
            content=ft.Column(
                [self.create_secret_card(entry) for entry in entries],
                spacing=LightTheme.SPACING_XS,
            ),
            padding=ft.padding.only(left=LightTheme.PADDING_LG, top=LightTheme.PADDING_SM),
            visible=is_expanded_ref["value"],
        )
        
        return ft.Container(
            content=ft.Column(
                [folder_header, entries_container],
                spacing=0,
            ),
            margin=ft.margin.only(bottom=LightTheme.SPACING_MD),
        )
    
    def _show_unlock_folder_dialog(self, folder_name: str):
        """Show dialog to unlock password-protected folder."""
        password_field = ft.TextField(
            label="Folder Password",
            password=True,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            autofocus=True,
        )
        
        def unlock_folder(e):
            password = password_field.value
            if not password:
                password_field.error_text = "Password required"
                self.page.update()
                return
            
            if self.folder_manager.unlock_folder(folder_name, password):
                dialog.open = False
                self.page.update()
                
                # Refresh view
                self.load_secrets()
                
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ Folder '{folder_name}' unlocked"),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                )
                self.page.snack_bar.open = True
                self.page.update()
            else:
                password_field.error_text = "Invalid password"
                password_field.value = ""
                self.page.update()
        
        def close_dialog():
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text(
                f"🔒 Unlock Folder",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            f"Folder '{folder_name}' is password protected.",
                            size=14,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Container(height=12),
                        password_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=400,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: close_dialog(),
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "Unlock",
                    icon=ft.Icons.LOCK_OPEN_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    on_click=unlock_folder
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _show_create_folder_dialog(self):
        """Show dialog to create a new folder."""
        folder_name_field = ft.TextField(
            label="Folder Name",
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            autofocus=True,
        )
        
        password_field = ft.TextField(
            label="Password (optional)",
            password=True,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            hint_text="Leave empty for no password",
        )
        
        description_field = ft.TextField(
            label="Description (optional)",
            multiline=True,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
        )
        
        def create_folder(e):
            folder_name = folder_name_field.value.strip()
            if not folder_name:
                folder_name_field.error_text = "Folder name required"
                self.page.update()
                return
            
            password = password_field.value if password_field.value else None
            description = description_field.value if description_field.value else None
            
            try:
                self.folder_manager.create_folder(
                    folder_name=folder_name,
                    password=password,
                    description=description
                )
                
                dialog.open = False
                self.page.update()
                
                # Refresh view
                self.load_secrets()
                
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ Folder '{folder_name}' created"),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                )
                self.page.snack_bar.open = True
                self.page.update()
            except ValueError as ve:
                folder_name_field.error_text = str(ve)
                self.page.update()
            except Exception as ex:
                logger.error(f"Failed to create folder: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Failed to create folder: {str(ex)}"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        def close_dialog():
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text(
                "📁 Create Folder",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Container(
                content=ft.Column(
                    [
                        folder_name_field,
                        password_field,
                        description_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=400,
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: close_dialog(),
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "Create",
                    icon=ft.Icons.ADD_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    on_click=create_folder
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def on_search_change(self, e):
        """Handle search query change with debouncing."""
        self.search_query = e.control.value
        
        # Cancel existing timer
        if self._search_timer:
            self._search_timer.cancel()
        
        # Debounce search: wait 300ms before executing
        import threading
        self._search_timer = threading.Timer(0.3, self.load_secrets)
        self._search_timer.start()

    def on_filter_change(self, e):
        """Handle filter change."""
        self.selected_type = e.control.value
        self.load_secrets()

    def on_nav_change(self, index: int):
        """Handle navigation change."""
        # Update sidebar selection
        self.sidebar.selected_index = index
        sidebar_container = self.sidebar.build()
        
        # Update sidebar in layout
        layout = self.page.controls[0]  # Get the Row layout
        if layout and isinstance(layout, ft.Row) and len(layout.controls) > 0:
            layout.controls[0] = sidebar_container  # Update sidebar
        
        # Handle navigation
        if index == -1:  # Home
            self.show_landing_page()
        else:
            # For all other views, ensure main UI layout is built
            # Check if we're currently on landing page (which uses different layout)
            if self.current_view == "landing" or len(self.page.controls) == 0 or not hasattr(self, 'secrets_list'):
                self.build_ui()
            
            if index == 0:  # Secrets
                self.selected_type = "secret"
                self.type_filter.value = "secret"
                self.load_secrets()
            elif index == 1:  # Knowledge
                self.show_knowledge_view()
            elif index == 2:  # Training
                self.show_training_view()
            elif index == 3:  # Activity
                self.show_activity_view()
            elif index == 4:  # Statistics
                self.show_statistics()
            elif index == 5:  # Settings
                self.show_settings()
            elif index == 6:  # LangChain Policies
                self.show_langchain_policies()
            elif index == 7:  # Library (Training Queue)
                self.show_library_view()
        
        self.page.update()

    def show_activity_view(self):
        """Show MCP access activity log."""
        self.current_view = "activity"
        self.secrets_list.controls.clear()
        
        # Initialize activity logger
        activity_logger = ActivityLogger(vault_path=str(self.vault_path))
        
        # Get recent activity
        activities = activity_logger.get_recent_activity(limit=50)
        
        # Build activity view
        activity_items = [
            ft.Text(
                "📋 Access Activity",
                size=24,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                "Recent vault access from Claude Desktop and other MCP clients",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Container(height=16),
        ]
        
        if not activities:
            # Empty state
            activity_items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.HISTORY_ROUNDED,
                                    size=60,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                                padding=20,
                            ),
                            ft.Container(height=16),
                            ft.Text(
                                "No activity yet",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                "Activity from Claude Desktop will appear here",
                                size=14,
                                color=LightTheme.TEXT_SECONDARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    padding=40,
                    alignment=ft.alignment.center,
                )
            )
        else:
            # Show activity entries
            for activity in activities:
                timestamp = activity.get('timestamp', '')
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    time_str = timestamp
                
                tool_name = activity.get('tool_name', 'unknown')
                app_name = activity.get('app_name', 'Unknown App')
                granted = activity.get('granted', False)
                query_preview = activity.get('query_preview', '')
                result_summary = activity.get('result_summary', '')
                
                # Tool icon mapping
                tool_icons = {
                    'vault_store': ft.Icons.ADD_CIRCLE_ROUNDED,
                    'vault_recall': ft.Icons.SEARCH_ROUNDED,
                    'vault_list_entries': ft.Icons.LIST_ROUNDED,
                    'vault_delete': ft.Icons.DELETE_ROUNDED,
                    'vault_stats': ft.Icons.BAR_CHART_ROUNDED,
                }
                tool_icon = tool_icons.get(tool_name, ft.Icons.SETTINGS_ROUNDED)
                
                # Status color
                status_color = LightTheme.ACCENT_SUCCESS if granted else LightTheme.ACCENT_ERROR
                status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED if granted else ft.Icons.CANCEL_ROUNDED
                
                activity_items.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(
                                                tool_icon,
                                                size=20,
                                                color=LightTheme.ACCENT_PRIMARY,
                                            ),
                                            width=40,
                                            height=40,
                                            border_radius=8,
                                            bgcolor=LightTheme.BG_ELEVATED,
                                            alignment=ft.alignment.center,
                                        ),
                                        ft.Container(width=12),
                                        ft.Column(
                                            [
                                                ft.Row(
                                                    [
                                                        ft.Text(
                                                            tool_name.replace('vault_', '').replace('_', ' ').title(),
                                                            size=14,
                                                            weight=ft.FontWeight.BOLD,
                                                            color=LightTheme.TEXT_PRIMARY,
                                                        ),
                                                        ft.Container(width=8),
                                                        ft.Container(
                                                            content=ft.Row(
                                                                [
                                                                    ft.Icon(status_icon, size=14, color=status_color),
                                                                    ft.Text(
                                                                        "Granted" if granted else "Denied",
                                                                        size=12,
                                                                        color=status_color,
                                                                        weight=ft.FontWeight.W_500,
                                                                    ),
                                                                ],
                                                                spacing=4,
                                                                tight=True,
                                                            ),
                                                            bgcolor=status_color + "20",
                                                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                                            border_radius=8,
                                                        ),
                                                    ],
                                                    spacing=8,
                                                ),
                                                ft.Container(height=4),
                                                ft.Text(
                                                    f"From: {app_name} • {time_str}",
                                                    size=12,
                                                    color=LightTheme.TEXT_SECONDARY,
                                                ),
                                                ft.Container(height=4),
                                                ft.Text(
                                                    query_preview if query_preview else f"Operation: {tool_name}",
                                                    size=12,
                                                    color=LightTheme.TEXT_MUTED,
                                                ),
                                                ft.Text(
                                                    result_summary if result_summary else "",
                                                    size=12,
                                                    color=LightTheme.ACCENT_SUCCESS,
                                                    weight=ft.FontWeight.W_500,
                                                ) if result_summary else ft.Container(),
                                            ],
                                            spacing=0,
                                            expand=True,
                                        ),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=16,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=12,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
                activity_items.append(ft.Container(height=12))
        
        # Add refresh button
        activity_items.append(
            ft.Row(
                [
                    ft.ElevatedButton(
                        "🔄 Refresh",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=lambda _: self.show_activity_view(),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                    ),
                    ft.ElevatedButton(
                        "🗑️ Clear Log",
                        icon=ft.Icons.DELETE_ROUNDED,
                        on_click=lambda _: self._clear_activity_log(),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_ERROR,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                    ),
                ],
                spacing=12,
            )
        )
        
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(activity_items, spacing=0),
                padding=24,
            )
        )
        self.page.update()
    
    def _clear_activity_log(self):
        """Clear activity log."""
        try:
            activity_logger = ActivityLogger(vault_path=str(self.vault_path))
            activity_logger.clear_activity()
            
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("✅ Activity log cleared"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
            
            # Refresh view
            self.show_activity_view()
        except Exception as e:
            logger.error(f"Failed to clear activity log: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Failed to clear log: {str(e)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def show_statistics(self):
        """Show vault statistics."""
        self.current_view = "statistics"
        stats = self.vault.get_stats()
        layer1 = stats['layer_1']
        layer2 = stats['layer_2']

        self.secrets_list.controls.clear()
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "📊 Vault Statistics",
                            size=24,
                            weight=ft.FontWeight.BOLD,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Divider(color=LightTheme.BORDER_COLOR),
                        ft.Text(
                            f"Total Entries: {layer1['total_entries']}",
                            size=16,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"Services: {', '.join(layer1['services']) if layer1['services'] else 'None'}",
                            size=14,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Divider(color=LightTheme.BORDER_COLOR),
                        ft.Text(
                            "Layer 1: Encrypted KV",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"  Entries: {layer1['total_entries']}",
                            size=14,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Divider(color=LightTheme.BORDER_COLOR),
                        ft.Text(
                            "Layer 2: DoRA",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            f"  Status: {'Active' if layer2['initialized'] else 'Not configured'}",
                            size=14,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                    ],
                    spacing=12,
                ),
                padding=24,
            )
        )
        self.page.update()

    def show_langchain_policies(self):
        """Show LangChain policies management view."""
        self.current_view = "langchain_policies"
        self.secrets_list.controls.clear()
        
        # Check authentication
        if not self.session_data:
            self.secrets_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "🔒 Authentication Required",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                "Please log in to manage LangChain policies",
                                size=14,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=24,
                )
            )
            self.page.update()
            return
        
        # Get access token
        access_token = self.session_data.get("access_token")
        if not access_token:
            # Try to refresh token
            try:
                from cloud_sync import CloudSyncService
                if self.cloud_sync:
                    # CloudSyncService handles token refresh
                    access_token = self.cloud_sync._get_access_token()
            except Exception as e:
                logger.error(f"Failed to get access token: {e}")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Fetch policies from backend
        policies = []
        try:
            response = requests.get(
                f"{self.backend_url}/api/langchain/policies",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                # Token expired, try to refresh
                if self.cloud_sync:
                    self.cloud_sync._refresh_token_if_needed()
                    access_token = self.cloud_sync._get_access_token()
                    headers["Authorization"] = f"Bearer {access_token}"
                    response = requests.get(
                        f"{self.backend_url}/api/langchain/policies",
                        headers=headers,
                        timeout=10
                    )
            
            if response.status_code == 200:
                policies = response.json().get("policies", [])
        except Exception as e:
            logger.error(f"Failed to fetch policies: {e}")
        
        # Build UI
        policy_items = [
            ft.Row(
                [
                    ft.Text(
                        "🔐 LangChain Policies",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "➕ Create Policy",
                        icon=ft.Icons.ADD_ROUNDED,
                        on_click=lambda _: self._show_create_policy_dialog(headers),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                    ),
                ],
                spacing=12,
            ),
            ft.Text(
                "Manage access policies for LangChain agents and other automated systems",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Container(height=16),
        ]
        
        if not policies:
            # Empty state
            policy_items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.SECURITY_ROUNDED,
                                    size=60,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                                padding=20,
                            ),
                            ft.Container(height=16),
                            ft.Text(
                                "No policies yet",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                "Create your first policy to control LangChain agent access",
                                size=14,
                                color=LightTheme.TEXT_SECONDARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    padding=40,
                    alignment=ft.alignment.center,
                )
            )
        else:
            # Show policies
            for policy in policies:
                policy_id = policy.get("id")
                policy_name = policy.get("policy_name", "Unnamed")
                agent_identifier = policy.get("agent_identifier", "")
                enabled = policy.get("enabled", True)
                secret_rules = policy.get("secret_rules", [])
                knowledge_rules = policy.get("knowledge_rules", [])
                rate_limits = policy.get("rate_limits", {})
                
                # Count rules
                secret_rules_count = len(secret_rules)
                knowledge_rules_count = len(knowledge_rules)
                
                # Rate limit info
                max_hour = rate_limits.get("max_requests_per_hour", 100) if rate_limits else 100
                max_day = rate_limits.get("max_requests_per_day", 1000) if rate_limits else 1000
                
                policy_items.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Icon(
                                                ft.Icons.SECURITY_ROUNDED if enabled else ft.Icons.SECURITY_OUTLINED,
                                                size=24,
                                                color=LightTheme.ACCENT_PRIMARY if enabled else LightTheme.TEXT_MUTED,
                                            ),
                                            width=40,
                                            height=40,
                                            border_radius=8,
                                            bgcolor=LightTheme.ACCENT_BLUE_LIGHT if enabled else LightTheme.BG_ELEVATED,
                                            alignment=ft.alignment.center,
                                        ),
                                        ft.Container(width=12),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    policy_name,
                                                    size=16,
                                                    weight=ft.FontWeight.BOLD,
                                                    color=LightTheme.TEXT_PRIMARY,
                                                ),
                                                ft.Text(
                                                    f"Agent: {agent_identifier}",
                                                    size=12,
                                                    color=LightTheme.TEXT_SECONDARY,
                                                ),
                                            ],
                                            spacing=4,
                                            expand=True,
                                        ),
                                        ft.Container(
                                            content=ft.Row(
                                                [
                                                    ft.Text(
                                                        "Enabled" if enabled else "Disabled",
                                                        size=12,
                                                        color=LightTheme.ACCENT_SUCCESS if enabled else LightTheme.TEXT_MUTED,
                                                        weight=ft.FontWeight.W_500,
                                                    ),
                                                ],
                                                spacing=8,
                                            ),
                                            padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                            bgcolor=(LightTheme.ACCENT_SUCCESS + "20") if enabled else LightTheme.BG_ELEVATED,
                                            border_radius=8,
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT_ROUNDED,
                                            icon_size=20,
                                            tooltip="Edit",
                                            on_click=lambda e, pid=policy_id: self._show_edit_policy_dialog(pid, headers),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE_ROUNDED,
                                            icon_size=20,
                                            tooltip="Delete",
                                            icon_color=LightTheme.ACCENT_ERROR,
                                            on_click=lambda e, pid=policy_id: self._delete_policy(pid, headers),
                                        ),
                                    ],
                                    spacing=0,
                                ),
                                ft.Container(height=12),
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Column(
                                                [
                                                    ft.Text(
                                                        "Secrets",
                                                        size=12,
                                                        color=LightTheme.TEXT_SECONDARY,
                                                    ),
                                                    ft.Text(
                                                        f"{secret_rules_count} rule(s)",
                                                        size=14,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=LightTheme.TEXT_PRIMARY,
                                                    ),
                                                ],
                                                spacing=2,
                                            ),
                                            padding=12,
                                            bgcolor=LightTheme.BG_ELEVATED,
                                            border_radius=8,
                                        ),
                                        ft.Container(
                                            content=ft.Column(
                                                [
                                                    ft.Text(
                                                        "Knowledge",
                                                        size=12,
                                                        color=LightTheme.TEXT_SECONDARY,
                                                    ),
                                                    ft.Text(
                                                        f"{knowledge_rules_count} rule(s)",
                                                        size=14,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=LightTheme.TEXT_PRIMARY,
                                                    ),
                                                ],
                                                spacing=2,
                                            ),
                                            padding=12,
                                            bgcolor=LightTheme.BG_ELEVATED,
                                            border_radius=8,
                                        ),
                                        ft.Container(
                                            content=ft.Column(
                                                [
                                                    ft.Text(
                                                        "Rate Limits",
                                                        size=12,
                                                        color=LightTheme.TEXT_SECONDARY,
                                                    ),
                                                    ft.Text(
                                                        f"{max_hour}/hr, {max_day}/day",
                                                        size=14,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=LightTheme.TEXT_PRIMARY,
                                                    ),
                                                ],
                                                spacing=2,
                                            ),
                                            padding=12,
                                            bgcolor=LightTheme.BG_ELEVATED,
                                            border_radius=8,
                                        ),
                                    ],
                                    spacing=12,
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=16,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=12,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
                policy_items.append(ft.Container(height=12))
        
        # Add refresh button
        policy_items.append(
            ft.Row(
                [
                    ft.ElevatedButton(
                        "🔄 Refresh",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=lambda _: self.show_langchain_policies(),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                    ),
                ],
                spacing=12,
            )
        )
        
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(policy_items, spacing=0),
                padding=24,
            )
        )
        self.page.update()

    def _show_create_policy_dialog(self, headers: dict):
        """Show dialog to create a new policy."""
        policy_name_field = ft.TextField(
            label="Policy Name",
            hint_text="e.g., langchain-general",
            autofocus=True,
        )
        agent_identifier_field = ft.TextField(
            label="Agent Identifier Pattern",
            hint_text="e.g., langchain-* or my-bot-v1",
            helper_text="Use * for wildcards (e.g., langchain-* matches all agents starting with 'langchain-')",
        )
        
        # Secret rules (simplified - allow all or specific services)
        secret_rule_type = ft.Dropdown(
            label="Secret Access",
            options=[
                ft.dropdown.Option("allow_all", "Allow All Secrets"),
                ft.dropdown.Option("allow_services", "Allow Specific Services"),
            ],
            value="allow_services",
        )
        secret_services_field = ft.TextField(
            label="Services (comma-separated)",
            hint_text="e.g., openai, anthropic, github",
            visible=True,
        )
        
        def on_secret_rule_change(e):
            secret_services_field.visible = (secret_rule_type.value == "allow_services")
            dialog.content.update()
        
        secret_rule_type.on_change = on_secret_rule_change
        
        # Knowledge rules (simplified - allow all)
        knowledge_rule_type = ft.Dropdown(
            label="Knowledge Access",
            options=[
                ft.dropdown.Option("allow_all", "Allow All Adapters"),
            ],
            value="allow_all",
        )
        
        # Rate limits
        rate_limit_hour = ft.TextField(
            label="Max Requests/Hour",
            value="100",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        rate_limit_day = ft.TextField(
            label="Max Requests/Day",
            value="1000",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        
        def create_policy(e):
            try:
                policy_name = policy_name_field.value.strip()
                agent_identifier = agent_identifier_field.value.strip()
                
                if not policy_name or not agent_identifier:
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text("Policy name and agent identifier are required"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                
                # Build secret rules
                secret_rules = []
                if secret_rule_type.value == "allow_all":
                    secret_rules.append({
                        "rule_type": "allow_all",
                        "rule_value": {},
                        "priority": 0
                    })
                elif secret_rule_type.value == "allow_services":
                    services = [s.strip() for s in secret_services_field.value.split(",") if s.strip()]
                    if services:
                        secret_rules.append({
                            "rule_type": "allow_services",
                            "rule_value": {"services": services},
                            "priority": 0
                        })
                
                # Build knowledge rules
                knowledge_rules = []
                if knowledge_rule_type.value == "allow_all":
                    knowledge_rules.append({
                        "rule_type": "allow_all",
                        "rule_value": {},
                        "priority": 0
                    })
                
                # Build rate limits
                rate_limits = {
                    "max_requests_per_hour": int(rate_limit_hour.value or "100"),
                    "max_requests_per_day": int(rate_limit_day.value or "1000"),
                }
                
                # Create policy
                policy_data = {
                    "policy_name": policy_name,
                    "agent_identifier": agent_identifier,
                    "enabled": True,
                    "secret_rules": secret_rules,
                    "knowledge_rules": knowledge_rules,
                    "rate_limits": rate_limits,
                }
                
                response = requests.post(
                    f"{self.backend_url}/api/langchain/policies",
                    json=policy_data,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text("✅ Policy created successfully"),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    dialog.open = False
                    self.page.update()
                    self.show_langchain_policies()
                else:
                    error_msg = response.json().get("detail", "Failed to create policy")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {error_msg}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            except Exception as ex:
                logger.error(f"Failed to create policy: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Error: {str(ex)}"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Create LangChain Policy"),
            content=ft.Container(
                content=ft.Column(
                    [
                        policy_name_field,
                        agent_identifier_field,
                        ft.Container(height=12),
                        secret_rule_type,
                        secret_services_field,
                        ft.Container(height=12),
                        knowledge_rule_type,
                        ft.Container(height=12),
                        ft.Text("Rate Limits", size=14, weight=ft.FontWeight.BOLD),
                        rate_limit_hour,
                        rate_limit_day,
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    height=500,
                ),
                width=500,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: setattr(dialog, "open", False) or self.page.update()),
                ft.ElevatedButton(
                    "Create",
                    on_click=create_policy,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        color="white",
                    ),
                ),
            ],
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def _show_edit_policy_dialog(self, policy_id: str, headers: dict):
        """Show dialog to edit a policy."""
        # Fetch policy details
        try:
            response = requests.get(
                f"{self.backend_url}/api/langchain/policies",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Failed to load policy"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            policies = response.json().get("policies", [])
            policy = next((p for p in policies if p.get("id") == policy_id), None)
            
            if not policy:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Policy not found"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # For now, show a simple edit dialog (enable/disable, rate limits)
            enabled_switch = ft.Switch(
                label="Enabled",
                value=policy.get("enabled", True),
            )
            
            rate_limits = policy.get("rate_limits", {})
            rate_limit_hour = ft.TextField(
                label="Max Requests/Hour",
                value=str(rate_limits.get("max_requests_per_hour", 100)),
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            rate_limit_day = ft.TextField(
                label="Max Requests/Day",
                value=str(rate_limits.get("max_requests_per_day", 1000)),
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            
            def update_policy(e):
                try:
                    update_data = {
                        "enabled": enabled_switch.value,
                        "rate_limits": {
                            "max_requests_per_hour": int(rate_limit_hour.value or "100"),
                            "max_requests_per_day": int(rate_limit_day.value or "1000"),
                        }
                    }
                    
                    response = requests.patch(
                        f"{self.backend_url}/api/langchain/policies/{policy_id}",
                        json=update_data,
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text("✅ Policy updated successfully"),
                            bgcolor=LightTheme.ACCENT_SUCCESS,
                        )
                        self.page.snack_bar.open = True
                        dialog.open = False
                        self.page.update()
                        self.show_langchain_policies()
                    else:
                        error_msg = response.json().get("detail", "Failed to update policy")
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"❌ {error_msg}"),
                            bgcolor=LightTheme.ACCENT_ERROR,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                except Exception as ex:
                    logger.error(f"Failed to update policy: {ex}")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ Error: {str(ex)}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Edit Policy: {policy.get('policy_name', 'Unknown')}"),
                content=ft.Container(
                    content=ft.Column(
                        [
                            enabled_switch,
                            ft.Container(height=12),
                            ft.Text("Rate Limits", size=14, weight=ft.FontWeight.BOLD),
                            rate_limit_hour,
                            rate_limit_day,
                        ],
                        spacing=8,
                    ),
                    width=400,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: setattr(dialog, "open", False) or self.page.update()),
                    ft.ElevatedButton(
                        "Save",
                        on_click=update_policy,
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                        ),
                    ),
                ],
            )
            
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()
            
        except Exception as ex:
            logger.error(f"Failed to show edit dialog: {ex}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error: {str(ex)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def _delete_policy(self, policy_id: str, headers: dict):
        """Delete a policy."""
        def confirm_delete(e):
            try:
                response = requests.delete(
                    f"{self.backend_url}/api/langchain/policies/{policy_id}",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text("✅ Policy deleted successfully"),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    dialog.open = False
                    self.page.update()
                    self.show_langchain_policies()
                else:
                    error_msg = response.json().get("detail", "Failed to delete policy")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {error_msg}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            except Exception as ex:
                logger.error(f"Failed to delete policy: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Error: {str(ex)}"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Policy"),
            content=ft.Text("Are you sure you want to delete this policy? This action cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: setattr(dialog, "open", False) or self.page.update()),
                ft.ElevatedButton(
                    "Delete",
                    on_click=confirm_delete,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_ERROR,
                        color="white",
                    ),
                ),
            ],
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def show_knowledge_view(self):
        """Show knowledge view with PDF upload."""
        self.current_view = "knowledge"
        self.selected_type = "knowledge"
        self.type_filter.value = "knowledge"
        
        # Create file picker if not already exists
        if not hasattr(self, 'pdf_file_picker') or self.pdf_file_picker is None:
            self.pdf_file_picker = ft.FilePicker(
                on_result=self.on_pdf_selected
            )
            self.page.overlay.append(self.pdf_file_picker)
        
        # Upload button with modern styling
        upload_button = ft.Container(
            content=ft.ElevatedButton(
                "📄 Upload PDF",
                icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                on_click=self._on_upload_click,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=12),
                    padding=ft.padding.symmetric(horizontal=24, vertical=12),
                ),
            ),
            gradient=LightTheme.get_gradient(LightTheme.GRADIENT_PRIMARY),
            border_radius=12,
        )
        
        # Add Knowledge button
        add_knowledge_button = ft.Container(
            content=ft.ElevatedButton(
                "➕ Add Knowledge",
                icon=ft.Icons.ADD_ROUNDED,
                on_click=lambda e: self.show_add_dialog(e, default_type="knowledge"),
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=12),
                    padding=ft.padding.symmetric(horizontal=24, vertical=12),
                ),
            ),
            border_radius=12,
        )
        
        # Clear and rebuild knowledge view
        self.secrets_list.controls.clear()
        
        # Knowledge view header with upload and add buttons
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "📚 Knowledge Base",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Row(
                                    [
                                        add_knowledge_button,
                                        upload_button,
                                    ],
                                    spacing=12,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(height=8),
                        # Workflow steps
                        ft.Container(
                            content=ft.Row(
                                [
                                    self._create_workflow_step("1", "📄 Upload PDF", "Add your document"),
                                    ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, color=LightTheme.TEXT_MUTED, size=16),
                                    self._create_workflow_step("2", "🧠 Train", "Generate knowledge adapter"),
                                    ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, color=LightTheme.TEXT_MUTED, size=16),
                                    self._create_workflow_step("3", "💬 Ask", "Query your documents"),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=12,
                            ),
                            padding=ft.padding.symmetric(vertical=16),
                            bgcolor=LightTheme.BG_HOVER,
                            border_radius=12,
                        ),
                    ],
                    spacing=0,
                ),
                padding=20,
            )
        )
        
        # Always show Knowledge Adapters section (with empty state if none)
        trained_models_section = self._build_trained_models_section()
        self.secrets_list.controls.append(trained_models_section)
        
        # Divider before knowledge entries
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, color=LightTheme.TEXT_SECONDARY, size=18),
                        ft.Container(width=8),
                        ft.Text(
                            "Uploaded Documents",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                    ],
                ),
                padding=ft.padding.only(left=20, right=20, top=16, bottom=8),
            )
        )
        
        # Load existing knowledge entries (these will be added after the header)
        self.load_secrets()
        self.page.update()
    
    def _create_workflow_step(self, number: str, title: str, subtitle: str) -> ft.Container:
        """Create a workflow step indicator."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                    ft.Text(subtitle, size=11, color=LightTheme.TEXT_MUTED),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
    
    def _build_trained_models_section(self) -> ft.Container:
        """Build a section showing trained knowledge adapters ready for inference."""
        # Find all entries with completed training
        from advanced_vault.encrypted_kv import QueryFilter
        
        trained_adapters = []
        
        try:
            # Search all entries and filter for completed training
            result = self.vault.kv_store.search(QueryFilter())
            
            for entry in result:
                tags = entry.tags or []
                training_status = None
                training_job_id = None
                training_key = None
                
                for tag in tags:
                    if tag.startswith("training_status:"):
                        training_status = tag.split(":", 1)[1]
                    elif tag.startswith("training_job:"):
                        training_job_id = tag.split(":", 1)[1]
                    elif tag.startswith("training_key:"):
                        training_key = tag.split(":", 1)[1]
                
                if training_status == "completed" and training_job_id and training_key:
                    trained_adapters.append({
                        "name": entry.service,
                        "adapter_id": training_job_id,
                        "encryption_key": training_key,
                        "created": entry.created_at.strftime("%Y-%m-%d") if entry.created_at else "Unknown",
                    })
        except Exception as e:
            logger.warning(f"Error loading trained adapters: {e}")
        
        # Build adapter cards or empty state
        if not trained_adapters:
            # Empty state - no trained adapters yet
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=LightTheme.TEXT_MUTED, size=20),
                                ft.Container(width=8),
                                ft.Text(
                                    "🧠 Knowledge Adapters",
                                    size=16,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_SECONDARY,
                                ),
                            ],
                        ),
                        ft.Container(height=12),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.PSYCHOLOGY_OUTLINED, color=LightTheme.TEXT_MUTED, size=40),
                                    ft.Container(height=8),
                                    ft.Text(
                                        "No trained adapters yet",
                                        size=14,
                                        weight=ft.FontWeight.W_500,
                                        color=LightTheme.TEXT_SECONDARY,
                                    ),
                                    ft.Text(
                                        "Upload a PDF and click 'Train' to create your first knowledge adapter",
                                        size=12,
                                        color=LightTheme.TEXT_MUTED,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=0,
                            ),
                            padding=24,
                            bgcolor=LightTheme.BG_HOVER,
                            border_radius=12,
                            border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        ),
                    ],
                    spacing=0,
                ),
                padding=20,
                margin=ft.margin.only(left=20, right=20, bottom=10),
            )
        
        # Build adapter cards
        adapter_cards = []
        for adapter in trained_adapters:
            card = ft.Container(
                content=ft.Row(
                    [
                        # Icon
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.SMART_TOY_ROUNDED,
                                color="#FFFFFF",
                                size=20,
                            ),
                            width=40,
                            height=40,
                            border_radius=10,
                            bgcolor=LightTheme.ACCENT_SUCCESS,
                            alignment=ft.alignment.center,
                        ),
                        ft.Container(width=12),
                        # Info
                        ft.Column(
                            [
                                ft.Text(
                                    adapter["name"],
                                    size=14,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Text(
                                    f"Trained {adapter['created']}",
                                    size=11,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        # Ask button
                        ft.ElevatedButton(
                            "💬 Ask",
                            on_click=lambda e, a=adapter: self._open_ask_dialog(
                                a["adapter_id"], a["encryption_key"], a["name"]
                            ),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=12,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=12,
                border=ft.border.all(1, LightTheme.ACCENT_SUCCESS + "40"),
            )
            adapter_cards.append(card)
        
        # Build section
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SMART_TOY_ROUNDED, color=LightTheme.ACCENT_SUCCESS, size=20),
                            ft.Container(width=8),
                            ft.Text(
                                f"🧠 Knowledge Adapters ({len(trained_adapters)})",
                                size=16,
                                weight=ft.FontWeight.W_600,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                        ],
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        "Ask questions about your trained documents",
                        size=12,
                        color=LightTheme.TEXT_MUTED,
                    ),
                    ft.Container(height=12),
                    ft.Column(adapter_cards, spacing=8),
                ],
                spacing=0,
            ),
            padding=20,
            bgcolor=LightTheme.ACCENT_SUCCESS + "08",
            border_radius=12,
            border=ft.border.all(1, LightTheme.ACCENT_SUCCESS + "20"),
            margin=ft.margin.only(left=20, right=20, bottom=10),
        )

    def _on_upload_click(self, e):
        """Handle upload button click."""
        logger.info("Upload PDF button clicked")
        try:
            if not hasattr(self, 'pdf_file_picker') or self.pdf_file_picker is None:
                logger.error("PDF file picker not initialized")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("❌ File picker not initialized. Please restart the app."),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            logger.debug("Opening file picker...")
            
            # Try to open file picker - on macOS this might need special handling
            try:
                # Workaround for Flet 0.28.3 macOS FilePicker bug
                # Try native macOS dialog if Flet FilePicker fails
                import subprocess
                import json
                
                # Use macOS native file picker as fallback
                logger.debug("Attempting macOS native file picker...")
                result = subprocess.run(
                    [
                        'osascript', '-e',
                        '''
                        set theFile to choose file of type {"PDF"} with prompt "Select PDF File"
                        set theFilePosix to POSIX path of theFile
                        return theFilePosix
                        '''
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    file_path = result.stdout.strip()
                    logger.debug(f"macOS file picker returned: {file_path}")
                    
                    # Create a fake FilePickerResultEvent
                    class FakeFile:
                        def __init__(self, path):
                            self.path = path
                            self.name = Path(path).name
                    
                    class FakeEvent:
                        def __init__(self, file_path):
                            self.files = [FakeFile(file_path)]
                    
                    # Call the handler with fake event
                    fake_event = FakeEvent(file_path)
                    self.on_pdf_selected(fake_event)
                    return
                else:
                    logger.debug(f"macOS file picker cancelled or error: {result.stderr}")
                    
            except FileNotFoundError:
                logger.debug("osascript not found, trying Flet FilePicker")
                # Fall back to Flet FilePicker
                self.pdf_file_picker.pick_files(
                    allowed_extensions=["pdf"],
                    dialog_title="Select PDF File"
                )
            except subprocess.TimeoutExpired:
                logger.debug("File picker timeout")
            except Exception as picker_error:
                logger.debug(f"pick_files() error: {picker_error}")
                # Try Flet FilePicker as fallback
                try:
                    self.pdf_file_picker.pick_files(
                        allowed_extensions=["pdf"],
                        dialog_title="Select PDF File"
                    )
                except Exception as fallback_error:
                    logger.debug(f"Fallback also failed: {fallback_error}")
                    raise
                
            logger.debug("pick_files() called successfully")
            logger.info("File picker opened")
            
            # Force page update
            self.page.update()
        except Exception as ex:
            logger.error(f"Error opening file picker: {ex}", exc_info=True)
            user_msg, _ = make_user_friendly(str(ex), context="upload")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def on_pdf_selected(self, e: ft.FilePickerResultEvent):
        """Handle PDF file selection."""
        logger.info(f"File picker result: {e}")
        logger.info(f"Files: {e.files if e.files else 'None'}")
        if not e.files or len(e.files) == 0:
            logger.info("No file selected")
            return
        
        file_path = e.files[0].path
        filename = e.files[0].name
        logger.info(f"Selected file: {filename} at {file_path}")
        
        # Show processing indicator
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"📄 Processing {filename}..."),
            bgcolor=LightTheme.ACCENT_PRIMARY,
        )
        self.page.snack_bar.open = True
        self.page.update()
        
        # Process PDF in background thread
        def process_pdf():
            try:
                # Ensure PDF processor is initialized
                if self.pdf_processor is None:
                    self._initialize_pdf_processor()
                
                # Copy PDF to a safe location before processing (file picker temp files may be deleted)
                # Store in vault directory for persistence during training workflow
                vault_data_dir = Path(self.vault_path) / "temp_pdfs"
                vault_data_dir.mkdir(parents=True, exist_ok=True)
                
                # Create persistent copy with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_pdf_path = vault_data_dir / f"{timestamp}_{filename}"
                
                # Copy file to safe location
                shutil.copy2(file_path, safe_pdf_path)
                logger.info(f"Copied PDF to safe location: {safe_pdf_path}")
                
                # Process PDF from safe location
                result = self.pdf_processor.process_pdf(str(safe_pdf_path))
                
                # Store PDF binary encrypted
                with open(safe_pdf_path, 'rb') as f:
                    pdf_data = f.read()
                
                # Store as knowledge entry in Layer 1 (for now, until Layer 2 is fully implemented)
                # Use service name as filename, tag it as knowledge/pdf
                # Store file path in description for later retrieval
                description_parts = [
                    f"PDF: {result['metadata']['page_count']} pages, {len(result['text_chunks'])} chunks",
                    f"Path: {safe_pdf_path}"  # Store safe file path
                ]
                
                entry_id = self.vault.kv_store.put(
                    service=filename,
                    secret_value=base64.b64encode(pdf_data).decode('utf-8'),
                    entry_type=EntryType.OTHER,  # Use OTHER type for knowledge entries
                    tags=["pdf", "document", "knowledge"],
                    description=" | ".join(description_parts)
                )
                
                logger.info(f"Stored PDF as knowledge entry: {filename} (ID: {entry_id})")
                
                # Sync to cloud (non-critical - don't fail if auth expires)
                if self.cloud_sync:
                    try:
                        self.cloud_sync.sync_entry_background(entry_id)
                    except Exception as sync_err:
                        logger.warning(f"Cloud sync failed (non-critical): {sync_err}")
                        # Don't show error to user - local storage succeeded
                
                # Update UI from main thread (thread-safe)
                def update_ui():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Processed {filename}: {len(result['text_chunks'])} chunks"),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    self.load_secrets()
                    
                    # Offer to generate Q&A and train model
                    # Use safe_pdf_path instead of original file_path (which may be deleted)
                    if self.qa_generator and self.training_manager and len(result['text_chunks']) > 0:
                        self._offer_training(filename, result['text_chunks'], pdf_path=str(safe_pdf_path))
                
                # Schedule UI update on main thread
                # Note: Flet's page.update() is thread-safe when called from background threads
                # But we wrap it in a function to ensure proper execution
                try:
                    # Try run_task if available (some Flet versions)
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_ui)
                    else:
                        # Fallback: direct update (Flet handles thread safety)
                        update_ui()
                except Exception as ui_err:
                    logger.warning(f"UI update error: {ui_err}, trying direct update")
                    update_ui()
                
            except Exception as ex:
                logger.error(f"Error processing PDF: {ex}")
                user_msg, _ = make_user_friendly(str(ex), context="upload")
                
                # Thread-safe error update
                def show_error():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {user_msg}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(show_error)
                    else:
                        show_error()
                except Exception as ui_err:
                    logger.warning(f"UI update error: {ui_err}, trying direct update")
                    show_error()
        
        thread = threading.Thread(target=process_pdf, daemon=True)
        thread.start()

    def _offer_training(self, filename: str, text_chunks: List[str], pdf_path: Optional[str] = None):
        """Offer to generate Q&A and train model after PDF processing."""
        # Check if training manager is initialized
        if not self.training_manager:
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Training Service Not Available",
                    color=LightTheme.TEXT_PRIMARY,
                ),
                content=ft.Text(
                    f"Training service failed to initialize.\n\n"
                    f"Please check:\n"
                    f"• Backend API availability\n"
                    f"• Network connection\n"
                    f"• Your account status",
                    color=LightTheme.TEXT_SECONDARY,
                ),
                bgcolor=LightTheme.BG_ELEVATED,
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=lambda e: setattr(dialog, 'open', False) or self.page.update(),
                        style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                    ),
                ],
            )
            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()
            return
        
        # Q&A generator is optional (can train without it)
        if not self.qa_generator:
            logger.warning("Q&A generator not available - training will proceed without Q&A pairs")
        
        def on_yes(e):
            dialog.open = False
            self.page.update()
            self._start_training_workflow(filename, text_chunks, pdf_path=pdf_path)
        
        def on_no(e):
            dialog.open = False
            self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Generate Training Model?",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Text(
                f"Would you like to generate Q&A pairs from this PDF and train a personalized model?\n\n"
                f"This will:\n"
                f"• Generate Q&A pairs from {len(text_chunks)} chunks\n"
                f"• Train a DoRA adapter on your data\n"
                f"• Store encrypted adapter in your vault\n\n"
                f"Note: This may take several minutes.",
                color=LightTheme.TEXT_SECONDARY,
            ),
            actions=[
                ft.TextButton(
                    "No",
                    on_click=on_no,
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Yes, Generate Model",
                        icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=8),
                        ),
                        on_click=on_yes
                    ),
                    gradient=LightTheme.get_gradient(LightTheme.GRADIENT_PRIMARY),
                    border_radius=8,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # Close any existing dialogs
        for overlay_item in list(self.page.overlay):
            if isinstance(overlay_item, ft.AlertDialog) and overlay_item.open:
                overlay_item.open = False
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _offer_training_from_entry(self, entry):
        """Offer training from an existing PDF entry."""
        service = entry.get('service', 'Unknown')
        tags = entry.get('tags', [])
        
        # Extract PDF data from entry
        tmp_path = None
        try:
            secret_value = self.vault.kv_store.get(service)
            if not secret_value:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Could not retrieve PDF data"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # Decode base64 PDF data
            pdf_data = base64.b64decode(secret_value)
            
            # Write to persistent location (not tempfile) so it exists during training workflow
            vault_data_dir = Path(self.vault_path) / "temp_pdfs"
            vault_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Create persistent copy with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_pdf_path = vault_data_dir / f"{timestamp}_{service}"
            
            # Write PDF data to persistent location
            with open(safe_pdf_path, 'wb') as f:
                f.write(pdf_data)
            
            logger.info(f"Saved PDF to persistent location: {safe_pdf_path}")
            
            # Process PDF to get text chunks
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📄 Processing {service}..."),
                bgcolor=LightTheme.ACCENT_PRIMARY,
            )
            self.page.snack_bar.open = True
            self.page.update()
            
            # Ensure PDF processor is initialized
            if self.pdf_processor is None:
                self._initialize_pdf_processor()
            
            result = self.pdf_processor.process_pdf(str(safe_pdf_path))
            
            # Offer training with the extracted chunks and PDF path
            # Pass safe_pdf_path so synthetic generation can use it (persists during training)
            self._offer_training(service, result['text_chunks'], pdf_path=str(safe_pdf_path))
            
        except Exception as ex:
            logger.error(f"Error extracting PDF for training: {ex}")
            user_msg, _ = make_user_friendly(str(ex), context="training")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ {user_msg}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
        finally:
            # Always cleanup temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_err}")

    def _create_training_progress_dialog(self, filename: str) -> tuple:
        """
        Create professional training progress dialog with encryption-focused messaging.
        
        Returns:
            Tuple of (dialog, phase_text, progress_bar, phase_status, encryption_indicator)
        """
        window_width = self.page.window.width or 1200
        window_height = self.page.window.height or 800
        
        dialog_width = min(max(int(window_width * 0.7), 600), 900)
        dialog_height = min(max(int(window_height * 0.7), 400), 600)
        
        # Phase text (main message)
        phase_text = ft.Text(
            "Preparing your document...",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=LightTheme.TEXT_PRIMARY,
        )
        
        # Progress bar
        progress_bar = ft.ProgressBar(
            width=dialog_width - 80,
            value=0.0,
            color=LightTheme.ACCENT_PRIMARY,
            bgcolor=LightTheme.BG_ELEVATED,
            bar_height=10,
        )
        
        # Phase status (subtitle)
        phase_status = ft.Text(
            "",
            size=13,
            color=LightTheme.TEXT_SECONDARY,
        )
        
        # Encryption indicator (always visible, reassuring)
        encryption_indicator = ft.Row(
            [
                ft.Icon(
                    ft.Icons.LOCK_ROUNDED,
                    size=16,
                    color=LightTheme.ACCENT_SUCCESS,
                ),
                ft.Text(
                    "All data is encrypted end-to-end",
                    size=12,
                    color=LightTheme.ACCENT_SUCCESS,
                    weight=ft.FontWeight.W_500,
                ),
            ],
            spacing=6,
            tight=True,
        )
        
        # Phase steps indicator
        phase_steps = ft.Column(
            [
                self._create_phase_step("Preparing the document", 0, False),
                self._create_phase_step("Knowledge extraction", 1, False),
                self._create_phase_step("Uploading encrypted data", 2, False),
                self._create_phase_step("Generating Vault Data", 3, False),
            ],
            spacing=8,
        )
        
        content_container = ft.Container(
            content=ft.Column(
                [
                    # Title section
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"🔐 Training Your AI Model",
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Container(height=4),
                                ft.Text(
                                    f"Document: {filename}",
                                    size=13,
                                    color=LightTheme.TEXT_SECONDARY,
                                ),
                            ],
                            spacing=0,
                            tight=True,
                        ),
                        padding=ft.padding.only(bottom=20),
                    ),
                    # Phase steps (fixed height)
                    ft.Container(
                        content=phase_steps,
                        padding=ft.padding.only(bottom=20),
                    ),
                    # Current phase section (expands to fill space)
                    ft.Container(
                        content=ft.Column(
                            [
                                phase_text,
                                ft.Container(height=6),
                                phase_status,
                            ],
                            spacing=0,
                            tight=True,
                        ),
                        expand=True,
                        padding=ft.padding.only(bottom=16),
                    ),
                    # Progress bar (fixed)
                    ft.Container(
                        content=progress_bar,
                        padding=ft.padding.only(bottom=16),
                    ),
                    # Encryption indicator (fixed at bottom)
                    ft.Container(
                        content=encryption_indicator,
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        bgcolor=LightTheme.ACCENT_SUCCESS + "15",
                        border_radius=8,
                        border=ft.border.all(1, LightTheme.ACCENT_SUCCESS + "40"),
                    ),
                ],
                scroll=None,
                spacing=0,
                tight=True,
            ),
            width=dialog_width - 48,  # Account for dialog padding
            padding=24,
        )
        
        progress_dialog = ft.AlertDialog(
            modal=True,
            title=None,  # Custom title in content
            content=ft.Container(
                content=content_container,
                width=dialog_width,
                height=dialog_height,
                padding=0,
            ),
            actions=[],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=LightTheme.BG_ELEVATED,
            shape=ft.RoundedRectangleBorder(radius=16),
        )
        
        return progress_dialog, phase_text, progress_bar, phase_status, encryption_indicator, phase_steps
    
    def _create_phase_step(self, label: str, step_index: int, completed: bool) -> ft.Container:
        """Create a phase step indicator."""
        icon = ft.Icons.CHECK_CIRCLE_ROUNDED if completed else (
            ft.Icons.RADIO_BUTTON_UNCHECKED if step_index == 0 else ft.Icons.CIRCLE_OUTLINED
        )
        icon_color = LightTheme.ACCENT_SUCCESS if completed else LightTheme.TEXT_MUTED
        
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        size=18,
                        color=icon_color,
                    ),
                    ft.Text(
                        label,
                        size=13,
                        color=LightTheme.TEXT_PRIMARY if completed else LightTheme.TEXT_SECONDARY,
                        weight=ft.FontWeight.W_500 if completed else ft.FontWeight.NORMAL,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
            padding=ft.padding.symmetric(vertical=4),
        )
    
    def _update_training_phase(
        self,
        phase_text: ft.Text,
        progress_bar: ft.ProgressBar,
        phase_status: ft.Text,
        phase_steps: ft.Column,
        phase: int,
        message: str,
        submessage: str = "",
        progress: Optional[float] = None
    ):
        """
        Update training progress dialog for specific phase.
        
        Args:
            phase_text: Main phase text widget
            progress_bar: Progress bar widget
            phase_status: Status subtitle widget
            phase_steps: Phase steps column widget
            phase: Phase number (0-3)
            message: Main message
            submessage: Optional submessage
            progress: Optional progress (0.0-1.0)
        """
        phases = [
            ("Preparing the document", "📄 Splitting document into sections..."),
            ("Knowledge extraction", "💡 Extracting knowledge from your content..."),
            ("Uploading encrypted data", "☁️ Uploading encrypted data to secure cloud storage..."),
            ("Generating Vault Data", "🔐 Generating your encrypted vault data..."),
        ]
        
        phase_name, default_msg = phases[phase] if phase < len(phases) else ("", "")
        
        # Update phase text
        phase_text.value = message or default_msg
        
        # Update status
        if submessage:
            phase_status.value = submessage
        else:
            phase_status.value = "Your data remains encrypted throughout this process"
        
        # Update progress bar
        if progress is not None:
            progress_bar.value = progress
        else:
            # Auto-calculate progress based on phase
            progress_bar.value = (phase + 1) / len(phases)
        
        # Update phase steps (mark previous as completed)
        for i, step_widget in enumerate(phase_steps.controls):
            if i < phase:
                # Mark previous steps as completed
                step = self._create_phase_step(phases[i][0], i, True)
                phase_steps.controls[i] = step
            elif i == phase:
                # Current step (in progress)
                step = self._create_phase_step(phases[i][0], i, False)
                phase_steps.controls[i] = step
        
        self.page.update()
    
    def _start_training_workflow(self, filename: str, text_chunks: List[str], pdf_path: Optional[str] = None):
        """Start Q&A generation and training workflow with progress dialog."""
        # Create progress dialog
        progress_dialog, phase_text, progress_bar, phase_status, encryption_indicator, phase_steps = self._create_training_progress_dialog(filename)
        
        self.page.overlay.append(progress_dialog)
        progress_dialog.open = True
        self.page.update()
        
        def workflow():
            try:
                # Phase 1: Preparing the document (already done, but show briefly)
                def update_phase1():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=0,
                        message="📄 Preparing the document...",
                        submessage=f"Processed {len(text_chunks)} sections",
                        progress=0.25
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase1)
                    else:
                        update_phase1()
                except Exception:
                    update_phase1()
                
                import time
                time.sleep(0.5)  # Brief pause to show phase 1
                
                # Phase 2: Knowledge extraction (Q&A generation)
                # Try synthetic generation first (automatic, 1000 samples)
                use_synthetic = False
                if pdf_path:
                    pdf_file = Path(pdf_path)
                    use_synthetic = pdf_file.exists() and pdf_file.is_file()
                    logger.info(f"PDF path provided: {pdf_path}, exists: {use_synthetic}")
                else:
                    logger.warning("No PDF path provided - will use local Q&A generation")
                
                qa_pairs = []
                dataset_encryption_key_hex = None
                
                if use_synthetic:
                    # Use synthetic generation with cloud endpoint (1000 samples)
                    try:
                        # Check if qa_generator is available
                        if not self.qa_generator:
                            logger.warning("QA generator not initialized - falling back to local generation")
                            use_synthetic = False
                        # Check if endpoint is configured
                        elif not os.getenv("RUNPOD_QA_ENDPOINT_ID"):
                            logger.warning("RUNPOD_QA_ENDPOINT_ID not configured - falling back to local generation")
                            logger.info("To use cloud QA generation, set RUNPOD_QA_ENDPOINT_ID environment variable")
                            use_synthetic = False
                        else:
                            # Check if API key is available for QA generation endpoint
                            # Default behavior: RUNPOD_QA_API_KEY defaults to RUNPOD_API_KEY if not set
                            # This ensures QA endpoint works by default when RUNPOD_API_KEY is set
                            runpod_api_key = os.getenv("RUNPOD_API_KEY")
                            qa_api_key = os.getenv("RUNPOD_QA_API_KEY")
                            
                            # Set RUNPOD_QA_API_KEY to RUNPOD_API_KEY by default if not explicitly set
                            # This ensures the QA endpoint is used by default
                            if not qa_api_key and runpod_api_key:
                                os.environ["RUNPOD_QA_API_KEY"] = runpod_api_key
                                qa_api_key = runpod_api_key
                                logger.debug("Set RUNPOD_QA_API_KEY to RUNPOD_API_KEY by default")
                            
                            # Priority: RUNPOD_QA_API_KEY (now set by default) > constructor api_key > RUNPOD_API_KEY
                            api_key = qa_api_key or (self.qa_generator.api_key if self.qa_generator else None) or runpod_api_key
                            
                            if not api_key:
                                logger.warning("RunPod API key not configured - falling back to local generation")
                                logger.info("To use cloud QA generation, set RUNPOD_QA_API_KEY or RUNPOD_API_KEY environment variable")
                                use_synthetic = False
                            else:
                                # Log which API key source is being used
                                if qa_api_key == runpod_api_key and runpod_api_key:
                                    logger.debug("Using RUNPOD_API_KEY (default) for QA generation via RUNPOD_QA_API_KEY")
                                elif qa_api_key:
                                    logger.debug("Using RUNPOD_QA_API_KEY for QA generation")
                                elif runpod_api_key:
                                    logger.debug("Using RUNPOD_API_KEY for QA generation")
                                
                                def update_phase2_synthetic():
                                    self._update_training_phase(
                                        phase_text, progress_bar, phase_status, phase_steps,
                                        phase=1,
                                        message="🧠 Generating Q&A with Qwen3-30B...",
                                        submessage="Creating high-quality training pairs via cloud AI (~2-5 min, encrypted)",
                                        progress=0.35
                                    )
                                
                                try:
                                    if hasattr(self.page, 'run_task'):
                                        self.page.run_task(update_phase2_synthetic)
                                    else:
                                        update_phase2_synthetic()
                                except Exception:
                                    update_phase2_synthetic()
                                
                                logger.info("Using synthetic Q&A generation (cloud endpoint)")
                                logger.info(f"PDF path: {pdf_path}, exists: {Path(pdf_path).exists()}")
                                logger.info(f"QA Generation Endpoint: {os.getenv('RUNPOD_QA_ENDPOINT_ID', 'not configured')} (separate from inference endpoint)")
                                logger.info(f"API key configured: {bool(api_key)}")
                                
                                qa_pairs, dataset_encryption_key_hex = self.qa_generator.generate_synthetic_qa_via_runpod(
                                    pdf_path=pdf_path,
                                    target_samples=100,  # Quality > quantity for adapter training
                                    encryption_key_hex=None  # Generate new key
                                )
                                
                                logger.info(f"✓ Generated {len(qa_pairs)} synthetic Q&A pairs from cloud endpoint")
                    
                    except RuntimeError as e:
                        logger.error(f"Synthetic generation failed: {e}")
                        logger.warning("Falling back to local Q&A generation...")
                        use_synthetic = False
                    except Exception as e:
                        logger.error(f"Synthetic generation failed with unexpected error: {e}", exc_info=True)
                        logger.warning("Falling back to local Q&A generation...")
                        use_synthetic = False
                
                if not use_synthetic:
                    # Fallback: Use local generation (MLX/Ollama)
                    total_chunks = len(text_chunks)
                    processed_chunks = [0]  # Use list to allow modification in nested function
                    
                    def update_phase2_progress(current: int, total: int):
                        """Update progress during knowledge extraction."""
                        progress = 0.25 + (current / total) * 0.25  # 25% to 50%
                        submsg = f"Extracting knowledge from chunk {current}/{total}... (All data encrypted)"
                        self._update_training_phase(
                            phase_text, progress_bar, phase_status, phase_steps,
                            phase=1,
                            message="💡 Extracting knowledge from your content...",
                            submessage=submsg,
                            progress=progress
                        )
                    
                    # Generate Q&A pairs with progress tracking
                    for i, chunk in enumerate(text_chunks):
                        current = i + 1
                        processed_chunks[0] = current
                        
                        # Update progress
                        def update_progress():
                            update_phase2_progress(current, total_chunks)
                        
                        try:
                            if hasattr(self.page, 'run_task'):
                                self.page.run_task(update_progress)
                            else:
                                update_progress()
                        except Exception:
                            update_progress()
                        
                        # Generate Q&A for this chunk
                        chunk_pairs = self.qa_generator.generate_qa_pairs(chunk, num_pairs=3)
                        if chunk_pairs:
                            qa_pairs.extend(chunk_pairs)
                    
                    # Generate encryption key for dataset
                    import secrets
                    dataset_encryption_key_hex = secrets.token_bytes(32).hex()
                
                if not qa_pairs:
                    progress_dialog.open = False
                    self.page.update()
                    user_msg, _ = make_user_friendly("Failed to generate Q&A pairs from document", context="training")
                    def show_error():
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"❌ {user_msg}"),
                            bgcolor=LightTheme.ACCENT_ERROR,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                    try:
                        if hasattr(self.page, 'run_task'):
                            self.page.run_task(show_error)
                        else:
                            show_error()
                    except Exception:
                        show_error()
                    return
                
                # Phase 3: Uploading encrypted data (includes encryption)
                # Note: os is imported at module level - don't re-import here!
                # Use existing encryption key if synthetic generation provided one, otherwise generate new
                if dataset_encryption_key_hex:
                    encryption_key = bytes.fromhex(dataset_encryption_key_hex)
                    encryption_key_hex = dataset_encryption_key_hex
                else:
                    encryption_key = os.urandom(32)
                    encryption_key_hex = encryption_key.hex()
                
                def update_phase3_start():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=2,
                        message="🔒 Encrypting and uploading your data...",
                        submessage=f"Encrypting {len(qa_pairs)} knowledge items with XChaCha20-Poly1305",
                        progress=0.6
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase3_start)
                    else:
                        update_phase3_start()
                except Exception:
                    update_phase3_start()
                
                dataset_filename = f"{filename.replace('.pdf', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                dataset_path = self.training_manager.save_dataset(
                    qa_pairs=qa_pairs,
                    filename=dataset_filename,
                    encryption_key=encryption_key
                )
                
                logger.info(f"Dataset encrypted and saved: {dataset_path}")
                
                def update_phase3_upload():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=2,
                        message="☁️ Uploading encrypted data securely...",
                        submessage="Your encrypted data is being uploaded to secure cloud storage",
                        progress=0.75
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase3_upload)
                    else:
                        update_phase3_upload()
                except Exception:
                    update_phase3_upload()
                
                # Phase 4: Generating Vault Data (submit training job)
                def update_phase4():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=3,
                        message="🔐 Submitting Training Job...",
                        submessage="Sending encrypted data to secure cloud (Qwen3-30B MoE model, ~2-5 min)",
                        progress=0.85
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase4)
                    else:
                        update_phase4()
                except Exception:
                    update_phase4()
                
                result = self.training_manager.submit_training_job(
                    dataset_path=dataset_path,
                    encryption_key_hex=encryption_key_hex,
                    model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                    epochs=3,
                    batch_size=4
                )
                
                # After submission, update to show completion
                def update_phase4_complete():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=3,
                        message="🔐 Generating Vault Data...",
                        submessage="Your encrypted vault data is being generated on secure infrastructure (check Training Jobs for progress)",
                        progress=0.95
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase4_complete)
                    else:
                        update_phase4_complete()
                except Exception:
                    update_phase4_complete()
                
                # Store training job metadata in vault entry
                # Find the entry by filename and update with job_id
                try:
                    # Search for the entry using QueryFilter
                    from advanced_vault.encrypted_kv import QueryFilter
                    filter = QueryFilter(service=filename, limit=1)
                    entries = self.vault.kv_store.search(filter)
                    if entries:
                        entry = entries[0]
                        # Get decrypted value to re-encrypt with new tags
                        decrypted_value = self.vault.kv_store.get_by_id(entry.id)
                        if decrypted_value:
                            # Update tags to include training job info
                            tags = list(entry.tags) if entry.tags else []
                            # Remove old training tags
                            tags = [t for t in tags if not t.startswith("training_")]
                            # Add new training tags
                            tags.append(f"training_job:{result['adapter_id']}")
                            tags.append(f"training_status:pending")
                            tags.append(f"training_key:{encryption_key_hex}")
                            # Update entry with new tags
                            self.vault.kv_store.put(
                                service=entry.service,
                                secret_value=decrypted_value,
                                entry_type=entry.entry_type,
                                tags=tags,
                                description=entry.description,
                                entry_id=entry.id
                            )
                except Exception as update_err:
                    logger.warning(f"Failed to update entry with training metadata: {update_err}")
                
                # Phase 4 Complete: Show success and demo query
                def update_success():
                    # Mark all phases as completed
                    phases = [
                        "Preparing the document",
                        "Knowledge extraction",
                        "Uploading encrypted data",
                        "Generating Vault Data"
                    ]
                    for i in range(4):
                        step = self._create_phase_step(phases[i], i, True)
                        phase_steps.controls[i] = step
                    
                    phase_text.value = "✅ Vault Data Generated Successfully!"
                    phase_status.value = f"Your encrypted vault data is ready. Knowledge ID: {result['adapter_id'][:8]}...\n\n💡 Try 'Demo Query' to test your knowledge base!"
                    progress_bar.value = 1.0
                    
                    # Store encryption_key_hex for demo query (in closure)
                    knowledge_id = result['adapter_id']
                    
                    # Add buttons: Demo Query and Done
                    progress_dialog.actions = [
                        ft.TextButton(
                            "Demo Query",
                            on_click=lambda e: self._show_demo_query_dialog(knowledge_id, encryption_key_hex, filename, progress_dialog),
                            style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                        ),
                        ft.TextButton(
                            "Done",
                            on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update() or self.load_secrets(),
                            style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                        ),
                    ]
                    
                    self.page.update()
                    
                    # Show snackbar
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"✅ Training job submitted! Try Demo Query to test your knowledge."),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_success)
                    else:
                        update_success()
                except Exception:
                    update_success()
                
                logger.info(f"Training workflow completed for {filename}")
                
            except Exception as ex:
                logger.error(f"Error in training workflow: {ex}")
                user_msg, help_link = make_user_friendly(str(ex), context="training")
                is_session_error = help_link == "SESSION_EXPIRED"
                
                def show_error():
                    # Update dialog to show error
                    phase_text.value = f"❌ Error: {user_msg}"
                    phase_status.value = "Training workflow failed. Your data remains secure."
                    progress_bar.value = None  # Indeterminate
                    
                    # Build action buttons
                    actions = []
                    
                    # Add logout button if session expired
                    if is_session_error:
                        actions.append(
                            ft.ElevatedButton(
                                "Log Out & Re-Login",
                                icon=ft.Icons.LOGOUT_ROUNDED,
                                on_click=lambda e: self._force_logout_and_close_dialog(progress_dialog),
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    color="white",
                                ),
                            )
                        )
                    
                    actions.append(
                        ft.TextButton(
                            "Close",
                            on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update(),
                            style=ft.ButtonStyle(color=LightTheme.ACCENT_ERROR),
                        ),
                    )
                    
                    progress_dialog.actions = actions
                    self.page.update()
                    
                    # Also show snackbar
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ {user_msg}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(show_error)
                    else:
                        show_error()
                except Exception:
                    show_error()
        
        # Run workflow in background thread
        thread = threading.Thread(target=workflow, daemon=True)
        thread.start()
    
    def _open_ask_dialog(self, adapter_id: str, encryption_key_hex: str, filename: str):
        """
        Open the Ask dialog for a trained knowledge base.
        This is called from the Knowledge list when clicking the Ask button on a completed adapter.
        """
        # Create a dummy parent dialog that does nothing (reusing the demo dialog logic)
        class DummyDialog:
            def __init__(self):
                self.open = False
        
        dummy = DummyDialog()
        self._show_demo_query_dialog(adapter_id, encryption_key_hex, filename, dummy)
    
    def _show_demo_query_dialog(self, knowledge_id: str, encryption_key_hex: str, filename: str, parent_dialog: ft.AlertDialog):
        """Show dialog for demo query to test the trained knowledge base."""
        # Close parent dialog first
        parent_dialog.open = False
        self.page.update()
        
        # Query input field
        query_field = ft.TextField(
            label="Ask a question about your document",
            hint_text="e.g., Describe this document in a few sentences",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            expand=True,
        )
        
        # Response area
        response_text = ft.Text(
            "",
            size=14,
            color=LightTheme.TEXT_PRIMARY,
            selectable=True,
        )
        
        response_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Response:",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        color=LightTheme.TEXT_SECONDARY,
                    ),
                    ft.Container(height=8),
                    response_text,
                ],
                spacing=0,
            ),
            padding=16,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=8,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            visible=False,
        )
        
        # Loading indicator
        loading_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(width=20, height=20, stroke_width=2),
                    ft.Text("Asking your knowledge base...", size=12, color=LightTheme.TEXT_SECONDARY),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=16,
            visible=False,
        )
        
        def ask_query(e):
            """Send query to inference endpoint."""
            query = query_field.value.strip()
            if not query:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Please enter a question"),
                    bgcolor=LightTheme.ACCENT_WARNING,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # Show loading
            loading_indicator.visible = True
            response_container.visible = False
            query_field.disabled = True
            submit_button.disabled = True
            self.page.update()
            
            def run_inference():
                try:
                    # First check adapter status before inference
                    # Poll for status update (backend queries RunPod to get latest status)
                    try:
                        import time
                        max_polls = 5  # Check up to 5 times
                        poll_interval = 2  # Wait 2 seconds between polls
                        
                        adapter_status = "unknown"
                        for poll_count in range(max_polls):
                            status_result = self.training_manager.get_training_status(knowledge_id)
                            adapter_status = status_result.get("status", "unknown")
                            
                            if adapter_status == "completed":
                                break  # Ready for inference
                            elif adapter_status in ["pending", "training"]:
                                # Still processing - wait and check again
                                if poll_count < max_polls - 1:
                                    time.sleep(poll_interval)
                                    continue
                            
                            # If we get here, either failed or still not ready after polling
                            break
                        
                        if adapter_status != "completed":
                            # Adapter not ready yet
                            error_msg = f"Knowledge base is still training (status: {adapter_status}). Please wait for training to complete."
                            if adapter_status == "pending":
                                error_msg = "Knowledge base is queued for training. Please wait a few minutes and try again."
                            elif adapter_status == "training":
                                error_msg = "Knowledge base is currently training. This may take several minutes. Please wait and try again."
                            elif adapter_status == "failed":
                                error_msg = "Knowledge base training failed. Please check the training status."
                            
                            def show_not_ready():
                                loading_indicator.visible = False
                                query_field.disabled = False
                                submit_button.disabled = False
                                response_text.value = error_msg
                                response_container.visible = True
                                self.page.update()
                            
                            show_not_ready()
                            return
                    except Exception as status_err:
                        logger.warning(f"Could not check adapter status: {status_err}")
                        # Continue anyway - backend will handle the check
                    
                    # Call training manager's inference method
                    response = self.training_manager.inference_with_adapter(
                        adapter_id=knowledge_id,
                        query=query,
                        encryption_key_hex=encryption_key_hex
                    )
                    
                    # Update UI with response
                    def update_ui():
                        loading_indicator.visible = False
                        query_field.disabled = False
                        submit_button.disabled = False
                        
                        if response and "response" in response:
                            response_text.value = response["response"]
                            response_container.visible = True
                        else:
                            response_text.value = "No response received"
                            response_container.visible = True
                        
                        self.page.update()
                    
                    # Call directly (not async)
                    update_ui()
                    
                except Exception as ex:
                    logger.error(f"Demo query error: {ex}")
                    def show_error():
                        loading_indicator.visible = False
                        query_field.disabled = False
                        submit_button.disabled = False
                        response_text.value = f"Error: {str(ex)}"
                        response_container.visible = True
                        self.page.update()
                    
                    # Call directly (not async)
                    show_error()
            
            thread = threading.Thread(target=run_inference, daemon=True)
            thread.start()
        
        submit_button = ft.ElevatedButton(
            "Ask",
            icon=ft.Icons.SEND_ROUNDED,
            on_click=ask_query,
            style=ft.ButtonStyle(
                bgcolor=LightTheme.ACCENT_PRIMARY,
                color="white",
            ),
        )
        
        # Create dialog
        demo_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"Demo Query - {filename}",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Ask your trained knowledge base a question about the document:",
                            size=13,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Container(height=16),
                        query_field,
                        ft.Container(height=16),
                        loading_indicator,
                        response_container,
                    ],
                    spacing=0,
                    tight=True,
                ),
                width=600,
                padding=0,
            ),
            actions=[
                submit_button,
                ft.TextButton(
                    "Close",
                    on_click=lambda e: setattr(demo_dialog, 'open', False) or self.page.update(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(demo_dialog)
        demo_dialog.open = True
        self.page.update()

    def show_training_view(self):
        """Show training jobs view."""
        self.current_view = "training"
        self.secrets_list.controls.clear()
        
        # Fetch training jobs from backend
        jobs = []
        if self.training_manager:
            try:
                response = requests.get(
                    f"{self.backend_url}/api/adapters/adapters",
                    headers=self.training_manager.headers,
                    timeout=10
                )
                
                # Refresh token on 401 error
                if response.status_code == 401:
                    if self.training_manager._refresh_token_if_needed(response):
                        # Retry with new token
                        response = requests.get(
                            f"{self.backend_url}/api/adapters/adapters",
                            headers=self.training_manager.headers,
                            timeout=10
                        )
                
                logger.info(f"Training jobs API response: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    jobs = data.get("adapters", [])
                    logger.info(f"Fetched {len(jobs)} training jobs from backend")
                else:
                    logger.warning(f"Failed to fetch training jobs: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error fetching training jobs: {e}", exc_info=True)
        
        # Training view content
        content_items = [
            ft.Row(
                [
                    ft.Text(
                        "🤖 Training Jobs",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                    ft.IconButton(
                        ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh",
                        on_click=lambda _: self.show_training_view(),
                        icon_color=LightTheme.TEXT_SECONDARY,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
        ]
        
        if not jobs:
            content_items.append(
                ft.Text(
                    "No training jobs yet. Upload a PDF and train a model to get started!",
                    size=14,
                    color=LightTheme.TEXT_MUTED
                )
            )
        else:
            # Display jobs
            for job in jobs:
                status = job.get("status", "unknown")
                adapter_id = job.get("adapter_id", "Unknown")
                job_id = job.get("job_id", "N/A")
                created_at = job.get("created_at", "")
                
                status_colors = {
                    "pending": LightTheme.ACCENT_WARNING,
                    "training": LightTheme.ACCENT_PRIMARY,
                    "completed": LightTheme.ACCENT_SUCCESS,
                    "failed": LightTheme.ACCENT_ERROR
                }
                status_color = status_colors.get(status, LightTheme.TEXT_MUTED)
                
                job_card = ft.Container(
                    content=ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                f"Adapter: {adapter_id[:8]}...",
                                                weight=ft.FontWeight.BOLD,
                                                size=16,
                                                color=LightTheme.TEXT_PRIMARY
                                            ),
                                            ft.Container(
                                                content=ft.Row(
                                                    [
                                                        ft.Icon(
                                                            ft.Icons.TRAIN_ROUNDED if status == "training" else ft.Icons.CHECK_CIRCLE_ROUNDED,
                                                            size=16,
                                                            color=status_color
                                                        ),
                                                        ft.Text(
                                                            status.title(),
                                                            size=12,
                                                            weight=ft.FontWeight.W_500,
                                                            color=status_color
                                                        )
                                                    ],
                                                    spacing=4,
                                                    tight=True
                                                ),
                                                bgcolor=status_color + "20",
                                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                                border_radius=8,
                                                border=ft.border.all(1, status_color + "40"),
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    ft.Container(height=8),
                                    ft.Text(
                                        f"Job ID: {job_id}",
                                        size=12,
                                        color=LightTheme.TEXT_MUTED
                                    ),
                                    ft.Text(
                                        f"Created: {created_at[:10] if created_at else 'N/A'}",
                                        size=12,
                                        color=LightTheme.TEXT_MUTED
                                    ),
                                ],
                                spacing=4,
                            ),
                            padding=16,
                        ),
                        elevation=2,
                        color=LightTheme.BG_ELEVATED,
                    ),
                    margin=ft.margin.only(bottom=12),
                )
                content_items.append(job_card)
        
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(content_items, spacing=10),
                padding=20,
            )
        )
        
        self.page.update()
        
        # Start auto-refresh for pending/training jobs
        self._start_training_auto_refresh(jobs)
    
    def _start_training_auto_refresh(self, jobs: List[Dict[str, Any]]):
        """
        Start automatic refresh for pending/training jobs.
        
        Args:
            jobs: List of training jobs
        """
        # Stop existing timer if any
        if self._training_refresh_timer:
            self._training_refresh_timer.cancel()
            self._training_refresh_timer = None
        
        # Check if there are any pending or training jobs
        has_pending_or_training = any(
            job.get("status", "").lower() in ["pending", "training"]
            for job in jobs
        )
        
        if not has_pending_or_training:
            # No pending/training jobs, no need to refresh
            self._training_refresh_active = False
            return
        
        # Start auto-refresh
        self._training_refresh_active = True
        
        def refresh_training_status():
            """Refresh training jobs status periodically."""
            if not self._training_refresh_active:
                return
            
            # Only refresh if training view is currently visible
            if self.current_view != "training":
                self._training_refresh_active = False
                return
            
            try:
                # Fetch updated jobs
                if self.training_manager:
                    response = requests.get(
                        f"{self.backend_url}/api/adapters/adapters",
                        headers=self.training_manager.headers,
                        timeout=10
                    )
                    
                    # Refresh token on 401 error
                    if response.status_code == 401:
                        if self.training_manager._refresh_token_if_needed(response):
                            response = requests.get(
                                f"{self.backend_url}/api/adapters/adapters",
                                headers=self.training_manager.headers,
                                timeout=10
                            )
                    
                    if response.status_code == 200:
                        data = response.json()
                        updated_jobs = data.get("adapters", [])
                        
                        # Check if any jobs are still pending/training
                        has_pending_or_training = any(
                            job.get("status", "").lower() in ["pending", "training"]
                            for job in updated_jobs
                        )
                        
                        # Update vault entry tags if status changed
                        self._update_training_status_tags(updated_jobs)
                        
                        if has_pending_or_training:
                            # Still have pending/training jobs, refresh view and schedule next check
                            logger.info("Refreshing training view (pending/training jobs active)...")
                            self.show_training_view()
                            # Schedule next refresh in 5 seconds
                            self._training_refresh_timer = threading.Timer(5.0, refresh_training_status)
                            self._training_refresh_timer.daemon = True
                            self._training_refresh_timer.start()
                        else:
                            # All jobs completed/failed, refresh once more to show final status, then stop
                            logger.info("All training jobs completed, refreshing view one last time...")
                            self.show_training_view()
                            # Also refresh Knowledge view if visible to update status badges
                            if self.current_view == "knowledge":
                                self.load_secrets()
                            self._training_refresh_active = False
            except Exception as e:
                logger.debug(f"Error refreshing training status: {e}")
                # Schedule retry in 10 seconds on error
                self._training_refresh_timer = threading.Timer(10.0, refresh_training_status)
                self._training_refresh_timer.daemon = True
                self._training_refresh_timer.start()
        
        # Start first refresh after 5 seconds
        self._training_refresh_timer = threading.Timer(5.0, refresh_training_status)
        self._training_refresh_timer.daemon = True
        self._training_refresh_timer.start()
        logger.info("Started auto-refresh for training jobs (5s interval)")
    
    def _update_training_status_tags(self, jobs: List[Dict[str, Any]]):
        """
        Update training status tags in vault entries based on job status.
        
        Args:
            jobs: List of training jobs with adapter_id and status
        """
        if not self.vault:
            return
        
        try:
            from advanced_vault.encrypted_kv import QueryFilter
            
            # Build mapping of adapter_id -> status
            adapter_statuses = {job.get("adapter_id"): job.get("status", "unknown") for job in jobs}
            
            # Find all entries with training tags
            filter = QueryFilter()
            all_entries = self.vault.kv_store.search(filter)
            
            updated_count = 0
            for entry in all_entries:
                tags = list(entry.tags) if entry.tags else []
                training_job_tags = [t for t in tags if t.startswith("training_job:")]
                
                if not training_job_tags:
                    continue
                
                # Extract adapter_id from training_job tag
                for job_tag in training_job_tags:
                    adapter_id = job_tag.replace("training_job:", "")
                    if adapter_id in adapter_statuses:
                        # Remove old training_status tag
                        tags = [t for t in tags if not t.startswith("training_status:")]
                        
                        # Add new status tag
                        new_status = adapter_statuses[adapter_id].lower()
                        tags.append(f"training_status:{new_status}")
                        
                        # Update entry
                        try:
                            decrypted_value = self.vault.kv_store.get_by_id(entry.id)
                            if decrypted_value:
                                self.vault.kv_store.put(
                                    service=entry.service,
                                    secret_value=decrypted_value,
                                    entry_type=entry.entry_type,
                                    tags=tags,
                                    description=entry.description,
                                    entry_id=entry.id
                                )
                                updated_count += 1
                                logger.debug(f"Updated training status tag for {entry.service}: {new_status}")
                        except Exception as e:
                            logger.debug(f"Failed to update entry {entry.id}: {e}")
            
            if updated_count > 0:
                logger.info(f"Updated training status tags for {updated_count} entries")
                
        except Exception as e:
            logger.debug(f"Error updating training status tags: {e}")

    def show_settings(self):
        """Show settings with MCP setup."""
        # Prevent infinite loops
        if self._refreshing_settings:
            return
        
        self.current_view = "settings"
        self.secrets_list.controls.clear()
        
        # Get MCP setup status (uses cache to avoid repeated initialization)
        mcp_status = self.mcp_setup.get_setup_status()
        
        # Build settings content
        settings_items = [
            ft.Text(
                "⚙️ Settings",
                size=24,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Vault Info Section
            ft.Text(
                "Vault Information",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                f"Vault Path: {self.vault_path}",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                f"Master Key: {self.key_path}",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                f"Database: {self.db_path}",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Encryption Info
            ft.Text(
                "Encryption: XChaCha20-Poly1305",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                "Key Size: 32 bytes (256-bit)",
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Component Status Section
            ft.Text(
                "🔧 Component Status",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                "Status of Enclave components and services",
                size=12,
                color=LightTheme.TEXT_MUTED,
            ),
            ft.Container(height=8),
        ]
        
        # Add component status cards
        components = [
            {
                "name": "AI Knowledge Extraction",
                "description": "Extracts text from scanned documents",
                "status_key": "ocr",
                "icon": ft.Icons.DOCUMENT_SCANNER_ROUNDED,
            },
            {
                "name": "Q&A Generation",
                "description": "Generates Q&A pairs from documents using optimized AI models",
                "status_key": "qa",
                "icon": ft.Icons.QUESTION_ANSWER_ROUNDED,
            },
            {
                "name": "Secure Vault",
                "description": "Encrypted local storage",
                "status_key": "vault",
                "icon": ft.Icons.LOCK_ROUNDED,
            },
            {
                "name": "Cloud Sync",
                "description": "Secure cloud backup",
                "status_key": "cloud_sync",
                "icon": ft.Icons.CLOUD_DONE_ROUNDED,
            },
            {
                "name": "AI Training",
                "description": "Personal AI model training",
                "status_key": "training",
                "icon": ft.Icons.PSYCHOLOGY_ROUNDED,
            },
        ]
        
        for component in components:
            # For Q&A, check actual status dynamically (MLX may have initialized after startup)
            if component["status_key"] == "qa" and self.qa_generator:
                try:
                    qa_status = self.qa_generator.get_qa_status()
                    if qa_status.get("mlx_initialized"):
                        status_info = {"status": "ready", "message": "Ready (Optimized AI)"}
                    elif qa_status.get("qa_model_available"):
                        status_info = {"status": "ready", "message": "Ready (Local AI)"}
                    elif qa_status.get("mlx_available"):
                        status_info = {"status": "checking", "message": "Setup required (download AI model)"}
                    else:
                        status_info = {"status": "checking", "message": "Q&A model not downloaded"}
                    # Update cache
                    self._component_status["qa"] = status_info
                except Exception as e:
                    logger.debug(f"Could not get Q&A status: {e}")
                    status_info = self._component_status.get(component["status_key"], {"status": "unknown", "message": "Unknown"})
            else:
                status_info = self._component_status.get(component["status_key"], {"status": "unknown", "message": "Unknown"})
            
            # Determine status color and icon
            if status_info["status"] == "ready":
                status_color = LightTheme.ACCENT_SUCCESS
                status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED
                status_text = "Ready"
            elif status_info["status"] == "installing":
                status_color = LightTheme.ACCENT_PRIMARY
                status_icon = ft.Icons.DOWNLOADING_ROUNDED
                status_text = status_info["message"]
            elif status_info["status"] == "checking":
                status_color = LightTheme.ACCENT_WARNING if "Setup required" in status_info.get("message", "") else LightTheme.TEXT_MUTED
                status_icon = ft.Icons.DOWNLOAD_ROUNDED if "Setup required" in status_info.get("message", "") else ft.Icons.HOURGLASS_EMPTY_ROUNDED
                status_text = status_info["message"]
            elif status_info["status"] == "error":
                status_color = LightTheme.ACCENT_ERROR
                status_icon = ft.Icons.ERROR_ROUNDED
                status_text = "Error"
            else:
                status_color = LightTheme.TEXT_MUTED
                status_icon = ft.Icons.HELP_OUTLINE_ROUNDED
                status_text = "Unknown"
            
            # Create component card
            component_card = ft.Card(
                content=ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                component["icon"],
                                color=LightTheme.ACCENT_PRIMARY,
                                size=24,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        component["name"],
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                        color=LightTheme.TEXT_PRIMARY,
                                    ),
                                    ft.Text(
                                        component["description"],
                                        size=11,
                                        color=LightTheme.TEXT_MUTED,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Row(
                                [
                                    ft.Icon(
                                        status_icon,
                                        color=status_color,
                                        size=18,
                                    ),
                                    ft.Text(
                                        status_text,
                                        size=12,
                                        color=status_color,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    # Add setup button for Q&A if not ready
                                    ft.IconButton(
                                        ft.Icons.DOWNLOAD_ROUNDED,
                                        icon_size=18,
                                        tooltip=self._get_qa_setup_tooltip(),
                                        visible=(component["status_key"] == "qa" and status_info["status"] != "ready" and status_info["status"] != "installing"),
                                        on_click=lambda e, key=component["status_key"]: self._setup_qa_model_with_progress() if key == "qa" else None,
                                        icon_color=LightTheme.ACCENT_PRIMARY,
                                    ) if component["status_key"] == "qa" else ft.Container(width=0),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=12,
                ),
                elevation=1,
                color=LightTheme.BG_ELEVATED,
            )
            
            settings_items.append(component_card)
        
        settings_items.append(ft.Divider(color=LightTheme.BORDER_COLOR))
        
        # MCP Server Section
        settings_items.extend([
            ft.Text(
                "🔌 MCP Server Integration",
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                "Connect your vault to Claude Desktop or ChatGPT",
                size=12,
                color=LightTheme.TEXT_MUTED,
            ),
            ft.Container(height=8),
        ])
        
        # MCP Status
        if mcp_status["claude_installed"]:
            status_color = LightTheme.ACCENT_SUCCESS if mcp_status["mcp_configured"] else LightTheme.ACCENT_WARNING
            status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED if mcp_status["mcp_configured"] else ft.Icons.WARNING_ROUNDED
            status_text = "Configured" if mcp_status["mcp_configured"] else "Not Configured"
            
            settings_items.append(
                ft.Row(
                    [
                        ft.Icon(status_icon, color=status_color, size=20),
                        ft.Text(
                            f"Claude Desktop: {status_text}",
                            size=14,
                            color=status_color,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=8,
                )
            )
        else:
            settings_items.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_ROUNDED, color=LightTheme.TEXT_MUTED, size=20),
                        ft.Text(
                            "Claude Desktop: Not Detected",
                            size=14,
                            color=LightTheme.TEXT_MUTED,
                        ),
                    ],
                    spacing=8,
                )
            )
        
        # MCP Test Status
        if mcp_status["test_success"]:
            settings_items.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=LightTheme.ACCENT_SUCCESS, size=16),
                        ft.Text(
                            f"MCP Server: {mcp_status['test_message']}",
                            size=12,
                            color=LightTheme.ACCENT_SUCCESS,
                        ),
                    ],
                    spacing=8,
                )
            )
        else:
            settings_items.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_ROUNDED, color=LightTheme.ACCENT_ERROR, size=16),
                        ft.Text(
                            f"MCP Server: {mcp_status['test_message']}",
                            size=12,
                            color=LightTheme.ACCENT_ERROR,
                        ),
                    ],
                    spacing=8,
                )
            )
        
        settings_items.append(ft.Container(height=12))
        
        # MCP Setup Buttons
        mcp_buttons = []
        
        # Generate Config Button
        def copy_config(e):
            config_json = self.mcp_setup.get_merged_config_json()
            self.page.set_clipboard(config_json)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("📋 Config copied to clipboard! Paste into Claude Desktop config file."),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
        
        mcp_buttons.append(
            ft.ElevatedButton(
                "📋 Copy Config to Clipboard",
                icon=ft.Icons.COPY_ROUNDED,
                on_click=copy_config,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            )
        )
        
        # Auto-Configure Button (if Claude Desktop detected)
        if mcp_status["claude_installed"]:
            def auto_configure(e):
                try:
                    config = self.mcp_setup.generate_mcp_config()
                    merged = self.mcp_setup.merge_config(config)
                    
                    if self.mcp_setup.write_config(merged):
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text("✅ MCP server configured! Restart Claude Desktop to activate."),
                            bgcolor=LightTheme.ACCENT_SUCCESS,
                        )
                    else:
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text("❌ Failed to write config. Check permissions."),
                            bgcolor=LightTheme.ACCENT_ERROR,
                        )
                    
                    self.page.snack_bar.open = True
                    self.page.update()
                    # Refresh settings to show updated status (but use flag to prevent loops)
                    if not self._refreshing_settings:
                        self._refreshing_settings = True
                        try:
                            self.show_settings()
                        finally:
                            self._refreshing_settings = False
                except Exception as ex:
                    logger.error(f"Auto-configure failed: {ex}")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ Error: {str(ex)}"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            
            mcp_buttons.append(
                ft.ElevatedButton(
                    "🚀 Auto-Configure Claude Desktop",
                    icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                    on_click=auto_configure,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                        color="white",
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )
        
        # Test Connection Button
        def test_connection(e):
            success, message = self.mcp_setup.test_mcp_server()
            color = LightTheme.ACCENT_SUCCESS if success else LightTheme.ACCENT_ERROR
            icon = ft.Icons.CHECK_CIRCLE_ROUNDED if success else ft.Icons.ERROR_ROUNDED
            
            self.page.snack_bar = ft.SnackBar(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=color, size=20),
                        ft.Text(f"MCP Server: {message}"),
                    ],
                    spacing=8,
                ),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()
            # Don't refresh settings - just show snackbar result
        
        mcp_buttons.append(
            ft.ElevatedButton(
                "🧪 Test Connection",
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                on_click=test_connection,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            )
        )
        
        settings_items.append(
            ft.Row(
                mcp_buttons,
                spacing=12,
                wrap=True,
            )
        )
        
        # Instructions
        if mcp_status["config_path"]:
            settings_items.extend([
                ft.Container(height=12),
                ft.Divider(color=LightTheme.BORDER_COLOR),
                ft.Text(
                    "Setup Instructions",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                ft.Text(
                    f"1. Config file location:\n   {mcp_status['config_path']}",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    "2. Click 'Auto-Configure' to set it up (or 'Copy Config' to paste manually)",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    "3. ⚠️ IMPORTANT: Completely quit and restart Claude Desktop",
                    size=12,
                    color=LightTheme.ACCENT_WARNING,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "4. After restart, look for 'Enclave' in your Connectors/Extensions list",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    "5. Test by asking Claude: 'What tools do you have access to?'",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
            ])
        
        # Add all items to container
        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(
                    settings_items,
                    spacing=12,
                ),
                padding=24,
            )
        )
        self.page.update()

    # ==================== Training Queue Methods ====================
    
    def _on_queue_item_updated(self, item: QueueItem):
        """Handle queue item updates (progress, status changes)."""
        # Update UI if we're on the library view
        if hasattr(self, 'current_view') and self.current_view == "library":
            self.page.run_thread(self._refresh_library_view)
    
    def _on_queue_item_completed(self, item: QueueItem):
        """Handle successful queue item completion."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="#FFFFFF"),
                ft.Text(f"✓ Trained: {item.filename}"),
            ], spacing=8),
            bgcolor=LightTheme.ACCENT_SUCCESS,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def _on_queue_item_failed(self, item: QueueItem, error: str):
        """Handle queue item failure."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Row([
                ft.Icon(ft.Icons.ERROR_ROUNDED, color="#FFFFFF"),
                ft.Text(f"Failed: {item.filename} - {error[:50]}"),
            ], spacing=8),
            bgcolor=LightTheme.ACCENT_ERROR,
        )
        self.page.snack_bar.open = True
        self.page.update()
    
    def _train_document_for_queue(self, file_path: str, filename: str, progress_callback) -> tuple:
        """
        Train a document from the queue.
        
        Returns (adapter_id, encryption_key) on success.
        Raises exception on failure.
        """
        progress_callback(5.0, "Reading PDF...")
        
        # Process PDF
        if self.pdf_processor is None:
            self._initialize_pdf_processor()
        
        result = self.pdf_processor.process_pdf(file_path)
        text_chunks = result.get('text_chunks', [])
        
        if not text_chunks:
            raise ValueError("No text extracted from PDF")
        
        progress_callback(15.0, "Generating Q&A pairs...")
        
        # Check if we should use synthetic Q&A (cloud) or local
        runpod_api_key = os.getenv("RUNPOD_API_KEY")
        qa_api_key = os.getenv("RUNPOD_QA_API_KEY")
        qa_endpoint_id = os.getenv("RUNPOD_QA_ENDPOINT_ID")
        
        api_key = qa_api_key or runpod_api_key
        
        if api_key and qa_endpoint_id and self.qa_generator:
            # Use cloud endpoint
            progress_callback(20.0, "Generating Q&A (cloud)...")
            qa_pairs, encryption_key_hex = self.qa_generator.generate_synthetic_qa_via_runpod(
                pdf_path=file_path,
                target_samples=100,
                encryption_key_hex=None
            )
        else:
            # Use local generation
            progress_callback(20.0, "Generating Q&A (local)...")
            if not self.qa_generator:
                raise ValueError("QA generator not available")
            qa_pairs = self.qa_generator.generate_qa_pairs(text_chunks, max_pairs=100)
            encryption_key_hex = None
        
        if not qa_pairs or len(qa_pairs) == 0:
            raise ValueError("Failed to generate Q&A pairs")
        
        progress_callback(50.0, f"Generated {len(qa_pairs)} Q&A pairs")
        
        # Encrypt and save dataset
        progress_callback(55.0, "Encrypting dataset...")
        
        dataset_name = Path(filename).stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        encryption_key_hex = self.training_manager.encrypt_dataset(qa_pairs, dataset_name)
        
        progress_callback(60.0, "Uploading dataset...")
        
        # Upload dataset
        local_path = self.training_manager.datasets_dir / f"{dataset_name}.encrypted"
        signed_url = self.training_manager.upload_dataset(str(local_path))
        
        if not signed_url:
            raise ValueError("Failed to upload dataset")
        
        progress_callback(70.0, "Submitting training job...")
        
        # Submit training job
        adapter_id = self.training_manager.submit_training_job(
            dataset_url=signed_url,
            encryption_key_hex=encryption_key_hex,
            adapter_name=dataset_name,
        )
        
        if not adapter_id:
            raise ValueError("Failed to submit training job")
        
        progress_callback(80.0, "Training submitted...")
        
        # Store entry in vault
        entry_name = filename
        entry_tags = [
            "data_type:knowledge",
            "source:pdf",
            f"training_status:pending",
            f"training_job:{adapter_id}",
            f"training_key:{encryption_key_hex}",
        ]
        
        self.vault.kv_store.store(
            service=entry_name,
            username=f"Trained from: {filename}",
            password="[ENCRYPTED ADAPTER]",
            tags=entry_tags,
            description=f"Knowledge adapter trained from {filename}. Adapter ID: {adapter_id}",
        )
        
        progress_callback(100.0, "Complete!")
        
        return adapter_id, encryption_key_hex
    
    def _refresh_library_view(self):
        """Refresh the library view UI."""
        if self.current_view == "library":
            self.show_library_view()
    
    def show_library_view(self):
        """Show the Knowledge Library with training queue and folder watching."""
        self.current_view = "library"
        self.secrets_list.controls.clear()
        
        # Check if training queue is available
        if not hasattr(self, 'training_queue') or self.training_queue is None:
            self.secrets_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, size=48, color=LightTheme.ACCENT_ERROR),
                        ft.Text("Training queue not available", size=16, color=LightTheme.TEXT_PRIMARY),
                        ft.Text("Please sign in to use the Knowledge Library", size=12, color=LightTheme.TEXT_MUTED),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    padding=40,
                    alignment=ft.alignment.center,
                )
            )
            self.page.update()
            return
        
        # Get queue stats
        stats = self.training_queue.get_stats()
        queue_items = self.training_queue.get_all_items()
        watched_folders = self.training_queue.get_watched_folders()
        
        # Create multi-file picker
        if not hasattr(self, 'multi_file_picker') or self.multi_file_picker is None:
            self.multi_file_picker = ft.FilePicker(
                on_result=self._on_multi_files_selected
            )
            self.page.overlay.append(self.multi_file_picker)
        
        # Create folder picker
        if not hasattr(self, 'folder_picker') or self.folder_picker is None:
            self.folder_picker = ft.FilePicker(
                on_result=self._on_folder_selected
            )
            self.page.overlay.append(self.folder_picker)
        
        # Header with actions
        # Count trained adapters for unified query button
        trained_count = len(self._get_all_trained_adapters())
        
        header = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text(
                            "📚 Knowledge Library",
                            size=24,
                            weight=ft.FontWeight.BOLD,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "Train multiple documents to build your personal knowledge base",
                            size=14,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                    ], spacing=4),
                    ft.Row([
                        # Unified Ask button (if we have trained adapters)
                        ft.ElevatedButton(
                            f"🧠 Ask All ({trained_count})",
                            icon=ft.Icons.PSYCHOLOGY_ROUNDED,
                            on_click=self.show_unified_ask_dialog,
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_WARNING,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            visible=trained_count > 0,
                        ),
                        ft.ElevatedButton(
                            "📁 Add Files",
                            icon=ft.Icons.ADD_ROUNDED,
                            on_click=lambda e: self.multi_file_picker.pick_files(
                                allow_multiple=True,
                                allowed_extensions=["pdf"],
                            ),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                        ),
                        ft.ElevatedButton(
                            "📂 Watch Folder",
                            icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                            on_click=lambda e: self.folder_picker.get_directory_path(),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_SUCCESS,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                        ),
                    ], spacing=8),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=0),
            padding=20,
        )
        self.secrets_list.controls.append(header)
        
        # Stats bar
        stats_bar = ft.Container(
            content=ft.Row([
                self._create_stat_chip(f"📥 {stats['pending']}", "Pending", LightTheme.ACCENT_WARNING),
                self._create_stat_chip(f"⚙️ {stats['processing']}", "Processing", LightTheme.ACCENT_PRIMARY),
                self._create_stat_chip(f"✅ {stats['completed']}", "Completed", LightTheme.ACCENT_SUCCESS),
                self._create_stat_chip(f"❌ {stats['failed']}", "Failed", LightTheme.ACCENT_ERROR),
                ft.Container(expand=True),
                # Queue controls
                ft.IconButton(
                    ft.Icons.PLAY_ARROW_ROUNDED if not self.training_queue.is_processing else ft.Icons.PAUSE_ROUNDED,
                    tooltip="Start Processing" if not self.training_queue.is_processing else "Pause Processing",
                    on_click=self._toggle_queue_processing,
                    icon_color=LightTheme.ACCENT_PRIMARY,
                ),
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED,
                    tooltip="Refresh",
                    on_click=lambda e: self.show_library_view(),
                    icon_color=LightTheme.TEXT_SECONDARY,
                ),
            ], spacing=12),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            bgcolor=LightTheme.BG_HOVER,
        )
        self.secrets_list.controls.append(stats_bar)
        
        # Watched Folders Section
        if watched_folders:
            folders_section = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FOLDER_COPY_ROUNDED, color=LightTheme.ACCENT_SUCCESS, size=20),
                        ft.Text(
                            f"Watched Folders ({len(watched_folders)})",
                            size=16,
                            weight=ft.FontWeight.W_600,
                            color=LightTheme.TEXT_PRIMARY,
                        ),
                    ], spacing=8),
                    ft.Container(height=8),
                    ft.Column([
                        self._create_folder_card(folder) for folder in watched_folders
                    ], spacing=8),
                ], spacing=0),
                padding=20,
                margin=ft.margin.only(left=20, right=20, top=10),
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=12,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )
            self.secrets_list.controls.append(folders_section)
        
        # Queue Section
        queue_section_title = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.QUEUE_ROUNDED, color=LightTheme.ACCENT_PRIMARY, size=20),
                ft.Text(
                    f"Training Queue ({len(queue_items)})",
                    size=16,
                    weight=ft.FontWeight.W_600,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                ft.Container(expand=True),
                ft.TextButton(
                    "Clear Completed",
                    on_click=self._clear_completed_items,
                    style=ft.ButtonStyle(color=LightTheme.TEXT_MUTED),
                ) if stats['completed'] > 0 else ft.Container(),
            ], spacing=8),
            padding=ft.padding.only(left=20, right=20, top=20, bottom=10),
        )
        self.secrets_list.controls.append(queue_section_title)
        
        # Queue items
        if queue_items:
            for item in queue_items:
                self.secrets_list.controls.append(self._create_queue_item_card(item))
        else:
            # Empty state
            empty_state = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.INBOX_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                    ft.Container(height=8),
                    ft.Text("No documents in queue", size=16, color=LightTheme.TEXT_SECONDARY),
                    ft.Text(
                        "Add PDFs or watch a folder to start building your knowledge base",
                        size=12,
                        color=LightTheme.TEXT_MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                padding=40,
                margin=ft.margin.symmetric(horizontal=20),
                bgcolor=LightTheme.BG_HOVER,
                border_radius=12,
                alignment=ft.alignment.center,
            )
            self.secrets_list.controls.append(empty_state)
        
        self.page.update()
    
    def _create_stat_chip(self, value: str, label: str, color: str) -> ft.Container:
        """Create a statistics chip."""
        return ft.Container(
            content=ft.Column([
                ft.Text(value, size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                ft.Text(label, size=10, color=LightTheme.TEXT_MUTED),
            ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=color + "15",
            border_radius=8,
        )
    
    def _create_folder_card(self, folder: WatchedFolder) -> ft.Container:
        """Create a card for a watched folder."""
        file_count = len(folder.known_files)
        
        return ft.Container(
            content=ft.Row([
                ft.Icon(
                    ft.Icons.FOLDER_ROUNDED,
                    color=LightTheme.ACCENT_SUCCESS if folder.enabled else LightTheme.TEXT_MUTED,
                    size=24,
                ),
                ft.Column([
                    ft.Text(
                        Path(folder.path).name,
                        size=14,
                        weight=ft.FontWeight.W_500,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                    ft.Text(
                        f"{folder.path} • {file_count} files",
                        size=11,
                        color=LightTheme.TEXT_MUTED,
                    ),
                ], spacing=2, expand=True),
                ft.Switch(
                    value=folder.enabled,
                    on_change=lambda e, p=folder.path: self._toggle_folder_watch(p, e.control.value),
                    active_color=LightTheme.ACCENT_SUCCESS,
                ),
                ft.IconButton(
                    ft.Icons.SYNC_ROUNDED,
                    tooltip="Scan Now",
                    on_click=lambda e, p=folder.path: self._scan_folder_now(p),
                    icon_color=LightTheme.TEXT_SECONDARY,
                    icon_size=18,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                    tooltip="Remove",
                    on_click=lambda e, p=folder.path: self._remove_watched_folder(p),
                    icon_color=LightTheme.ACCENT_ERROR,
                    icon_size=18,
                ),
            ], spacing=12),
            padding=12,
            bgcolor=LightTheme.BG_PRIMARY,
            border_radius=8,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )
    
    def _create_queue_item_card(self, item: QueueItem) -> ft.Container:
        """Create a card for a queue item."""
        # Status-based styling
        status_config = {
            QueueItemStatus.PENDING: {"icon": ft.Icons.SCHEDULE_ROUNDED, "color": LightTheme.ACCENT_WARNING, "label": "Pending"},
            QueueItemStatus.PROCESSING: {"icon": ft.Icons.SYNC_ROUNDED, "color": LightTheme.ACCENT_PRIMARY, "label": "Processing"},
            QueueItemStatus.COMPLETED: {"icon": ft.Icons.CHECK_CIRCLE_ROUNDED, "color": LightTheme.ACCENT_SUCCESS, "label": "Completed"},
            QueueItemStatus.FAILED: {"icon": ft.Icons.ERROR_ROUNDED, "color": LightTheme.ACCENT_ERROR, "label": "Failed"},
            QueueItemStatus.CANCELLED: {"icon": ft.Icons.CANCEL_ROUNDED, "color": LightTheme.TEXT_MUTED, "label": "Cancelled"},
        }
        
        config = status_config.get(item.status, status_config[QueueItemStatus.PENDING])
        
        # Progress bar for processing items
        progress_bar = None
        if item.status == QueueItemStatus.PROCESSING:
            progress_bar = ft.ProgressBar(
                value=item.progress / 100.0,
                color=LightTheme.ACCENT_PRIMARY,
                bgcolor=LightTheme.BG_HOVER,
                height=4,
            )
        
        # Action buttons
        actions = []
        if item.status == QueueItemStatus.PENDING:
            actions.append(
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                    tooltip="Remove",
                    on_click=lambda e, i=item.id: self._remove_queue_item(i),
                    icon_color=LightTheme.ACCENT_ERROR,
                    icon_size=18,
                )
            )
        elif item.status == QueueItemStatus.FAILED:
            actions.extend([
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED,
                    tooltip="Retry",
                    on_click=lambda e, i=item.id: self._retry_queue_item(i),
                    icon_color=LightTheme.ACCENT_PRIMARY,
                    icon_size=18,
                ),
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                    tooltip="Remove",
                    on_click=lambda e, i=item.id: self._remove_queue_item(i),
                    icon_color=LightTheme.ACCENT_ERROR,
                    icon_size=18,
                ),
            ])
        elif item.status == QueueItemStatus.COMPLETED and item.adapter_id:
            actions.append(
                ft.IconButton(
                    ft.Icons.CHAT_ROUNDED,
                    tooltip="Ask",
                    on_click=lambda e, a=item.adapter_id, k=item.encryption_key, f=item.filename: self._open_ask_dialog(a, k, f),
                    icon_color=LightTheme.ACCENT_SUCCESS,
                    icon_size=18,
                )
            )
        
        card_content = ft.Column([
            ft.Row([
                ft.Icon(config["icon"], color=config["color"], size=20),
                ft.Column([
                    ft.Text(
                        item.filename,
                        size=14,
                        weight=ft.FontWeight.W_500,
                        color=LightTheme.TEXT_PRIMARY,
                    ),
                    ft.Text(
                        item.progress_message if item.status == QueueItemStatus.PROCESSING else 
                        (item.error[:50] + "..." if item.error and len(item.error) > 50 else item.error) if item.status == QueueItemStatus.FAILED else
                        f"Added: {item.added_at.strftime('%H:%M')}" if item.status == QueueItemStatus.PENDING else
                        f"Completed: {item.completed_at.strftime('%H:%M') if item.completed_at else 'N/A'}",
                        size=11,
                        color=LightTheme.ACCENT_ERROR if item.status == QueueItemStatus.FAILED else LightTheme.TEXT_MUTED,
                    ),
                ], spacing=2, expand=True),
                ft.Container(
                    content=ft.Text(config["label"], size=10, color=config["color"]),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=config["color"] + "15",
                    border_radius=4,
                ),
                *actions,
            ], spacing=12),
        ], spacing=4)
        
        if progress_bar:
            card_content.controls.append(progress_bar)
        
        return ft.Container(
            content=card_content,
            padding=12,
            margin=ft.margin.only(left=20, right=20, bottom=8),
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=8,
            border=ft.border.all(1, config["color"] + "30" if item.status in [QueueItemStatus.PROCESSING, QueueItemStatus.FAILED] else LightTheme.BORDER_COLOR),
        )
    
    def _on_multi_files_selected(self, e: ft.FilePickerResultEvent):
        """Handle multiple file selection."""
        if not e.files:
            return
        
        added_count = 0
        for file in e.files:
            if file.path:
                item = self.training_queue.add_file(file.path)
                if item:
                    added_count += 1
        
        if added_count > 0:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📥 Added {added_count} file(s) to queue"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
        
        self.show_library_view()
    
    def _on_folder_selected(self, e: ft.FilePickerResultEvent):
        """Handle folder selection for watching."""
        if not e.path:
            return
        
        try:
            folder = self.training_queue.add_watched_folder(e.path)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📂 Watching: {Path(e.path).name} ({len(folder.known_files)} files)"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            
            # Start folder watcher if not running
            self.training_queue.start_folder_watcher()
        except Exception as ex:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error: {str(ex)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
        
        self.show_library_view()
    
    def _toggle_queue_processing(self, e):
        """Toggle queue processing on/off."""
        if self.training_queue.is_processing:
            self.training_queue.pause_processing()
        else:
            if self.training_queue.is_paused:
                self.training_queue.resume_processing()
            else:
                self.training_queue.start_processing()
        
        self.show_library_view()
    
    def _toggle_folder_watch(self, folder_path: str, enabled: bool):
        """Toggle folder watching."""
        self.training_queue.toggle_folder(folder_path, enabled)
    
    def _scan_folder_now(self, folder_path: str):
        """Manually scan a folder for new files."""
        new_files = self.training_queue.scan_folder_now(folder_path)
        
        if new_files:
            # Add new files to queue
            for file_path in new_files:
                self.training_queue.add_file(file_path)
            
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📥 Found {len(new_files)} new file(s)"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
        else:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("No new files found"),
                bgcolor=LightTheme.BG_ELEVATED,
            )
        
        self.page.snack_bar.open = True
        self.show_library_view()
    
    def _remove_watched_folder(self, folder_path: str):
        """Remove a watched folder."""
        self.training_queue.remove_watched_folder(folder_path)
        self.show_library_view()
    
    def _remove_queue_item(self, item_id: str):
        """Remove an item from the queue."""
        self.training_queue.remove_item(item_id)
        self.show_library_view()
    
    def _retry_queue_item(self, item_id: str):
        """Retry a failed queue item."""
        self.training_queue.retry_failed(item_id)
        self.show_library_view()
    
    def _clear_completed_items(self, e):
        """Clear all completed items."""
        self.training_queue.clear_completed()
        self.show_library_view()

    # ==================== Unified Knowledge Pool ====================
    
    def _get_all_trained_adapters(self) -> List[Dict]:
        """Get all completed knowledge adapters for unified queries."""
        from advanced_vault.encrypted_kv import QueryFilter
        
        adapters = []
        try:
            result = self.vault.kv_store.search(QueryFilter())
            
            for entry in result:
                tags = entry.tags or []
                training_status = None
                training_job_id = None
                training_key = None
                
                for tag in tags:
                    if tag.startswith("training_status:"):
                        training_status = tag.split(":", 1)[1]
                    elif tag.startswith("training_job:"):
                        training_job_id = tag.split(":", 1)[1]
                    elif tag.startswith("training_key:"):
                        training_key = tag.split(":", 1)[1]
                
                if training_status == "completed" and training_job_id and training_key:
                    adapters.append({
                        "name": entry.service,
                        "adapter_id": training_job_id,
                        "encryption_key": training_key,
                    })
        except Exception as e:
            logger.warning(f"Error loading trained adapters: {e}")
        
        return adapters
    
    def show_unified_ask_dialog(self, e=None):
        """Show dialog for asking questions across ALL trained knowledge bases."""
        adapters = self._get_all_trained_adapters()
        
        if not adapters:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("No trained knowledge bases available. Train some documents first!"),
                bgcolor=LightTheme.ACCENT_WARNING,
            )
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        # Query input field
        query_field = ft.TextField(
            label="Ask across all your documents",
            hint_text="e.g., What are the key points from my documents?",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            expand=True,
        )
        
        # Adapter selection checkboxes
        adapter_checks = []
        for adapter in adapters:
            cb = ft.Checkbox(
                label=adapter["name"],
                value=True,
                data=adapter,
            )
            adapter_checks.append(cb)
        
        # Response area - now shows multiple responses
        responses_column = ft.Column([], spacing=12, scroll=ft.ScrollMode.AUTO)
        
        responses_container = ft.Container(
            content=responses_column,
            height=300,
            visible=False,
        )
        
        # Loading indicator
        loading_indicator = ft.Container(
            content=ft.Column([
                ft.ProgressRing(width=40, height=40, stroke_width=3),
                ft.Container(height=8),
                ft.Text("Asking your knowledge bases...", size=12, color=LightTheme.TEXT_SECONDARY),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=24,
            visible=False,
            alignment=ft.alignment.center,
        )
        
        def ask_unified_query(e):
            """Query all selected adapters."""
            query = query_field.value.strip()
            if not query:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Please enter a question"),
                    bgcolor=LightTheme.ACCENT_WARNING,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # Get selected adapters
            selected_adapters = [cb.data for cb in adapter_checks if cb.value]
            
            if not selected_adapters:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Please select at least one knowledge base"),
                    bgcolor=LightTheme.ACCENT_WARNING,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
            
            # Show loading
            loading_indicator.visible = True
            responses_container.visible = False
            query_field.disabled = True
            submit_button.disabled = True
            self.page.update()
            
            def run_unified_inference():
                results = []
                
                for adapter in selected_adapters:
                    try:
                        response = self.training_manager.inference_with_adapter(
                            adapter_id=adapter["adapter_id"],
                            query=query,
                            encryption_key_hex=adapter["encryption_key"]
                        )
                        
                        if response and "response" in response:
                            results.append({
                                "name": adapter["name"],
                                "response": response["response"],
                                "success": True,
                            })
                        else:
                            results.append({
                                "name": adapter["name"],
                                "response": "No response received",
                                "success": False,
                            })
                    except Exception as ex:
                        results.append({
                            "name": adapter["name"],
                            "response": f"Error: {str(ex)}",
                            "success": False,
                        })
                
                def update_ui():
                    loading_indicator.visible = False
                    query_field.disabled = False
                    submit_button.disabled = False
                    
                    # Build response cards
                    responses_column.controls.clear()
                    
                    for result in results:
                        card = ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE_ROUNDED if result["success"] else ft.Icons.ERROR_ROUNDED,
                                        color=LightTheme.ACCENT_SUCCESS if result["success"] else LightTheme.ACCENT_ERROR,
                                        size=16,
                                    ),
                                    ft.Text(
                                        result["name"],
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                        color=LightTheme.TEXT_PRIMARY,
                                    ),
                                ], spacing=8),
                                ft.Container(height=4),
                                ft.Text(
                                    result["response"],
                                    size=13,
                                    color=LightTheme.TEXT_SECONDARY,
                                    selectable=True,
                                ),
                            ], spacing=0),
                            padding=12,
                            bgcolor=LightTheme.BG_ELEVATED,
                            border_radius=8,
                            border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        )
                        responses_column.controls.append(card)
                    
                    responses_container.visible = True
                    self.page.update()
                
                update_ui()
            
            thread = threading.Thread(target=run_unified_inference, daemon=True)
            thread.start()
        
        submit_button = ft.ElevatedButton(
            "Ask All",
            icon=ft.Icons.SEND_ROUNDED,
            on_click=ask_unified_query,
            style=ft.ButtonStyle(
                bgcolor=LightTheme.ACCENT_PRIMARY,
                color="white",
            ),
        )
        
        # Create dialog
        unified_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, color=LightTheme.ACCENT_PRIMARY, size=24),
                ft.Container(width=8),
                ft.Text(
                    "Ask Your Knowledge",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
            ], spacing=0),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"Query {len(adapters)} trained knowledge base(s) at once:",
                        size=13,
                        color=LightTheme.TEXT_SECONDARY,
                    ),
                    ft.Container(height=12),
                    # Adapter selection
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Select knowledge bases:", size=12, color=LightTheme.TEXT_MUTED),
                            ft.Container(height=4),
                            ft.Column(adapter_checks, spacing=4),
                        ], spacing=0),
                        padding=12,
                        bgcolor=LightTheme.BG_HOVER,
                        border_radius=8,
                    ),
                    ft.Container(height=16),
                    ft.Row([
                        query_field,
                        submit_button,
                    ], spacing=12),
                    ft.Container(height=12),
                    loading_indicator,
                    responses_container,
                ], spacing=0, scroll=ft.ScrollMode.AUTO),
                width=600,
                height=500,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda e: self._close_dialog(unified_dialog),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(unified_dialog)
        unified_dialog.open = True
        self.page.update()
    
    def _close_dialog(self, dialog):
        """Close a dialog safely."""
        dialog.open = False
        self.page.update()


def main(page: ft.Page):
    """Main entry point."""
    VaultApp(page)


if __name__ == "__main__":
    ft.app(target=main)
