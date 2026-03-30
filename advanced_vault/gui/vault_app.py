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
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import time

# Check if MLX module is available
try:
    from qa_generator_mlx import MLXQAGenerator
    MLX_MODULE_AVAILABLE = True
except ImportError:
    MLX_MODULE_AVAILABLE = False

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from advanced_vault.core import HybridVault
from advanced_vault.enclave_control import EnclaveRuntime
from advanced_vault.encrypted_kv import QueryFilter, EntryType
from advanced_vault.mcp_server.activity_logger import ActivityLogger
from advanced_vault.private_models import PrivateModelManager, PrivateModelProfile
from advanced_vault.private_models.manager import SUPPORTED_EXTENSIONS
from advanced_vault.sheriff.core import SheriffCore
from advanced_vault.wallet import WalletService
from auth_screen import AuthScreen
from cloud_sync import CloudSyncService
from pdf_processor import PDFProcessor, probe_liteparse_backend
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
from localization import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_text

logger = logging.getLogger(__name__)

DEFAULT_PRIVATE_MODEL_NAME = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
PRIVATE_MODEL_IMPORT_EXTENSIONS = sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS)

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
        
        self.backend_url = os.getenv("ENCLAVE_BACKEND_URL", "")

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
        self.onboarding_state_path = self.vault_path / ".onboarding_v1_complete"
        self.language_pref_path = self.vault_path / ".language_pref"
        self.language = self._load_language_preference()
        
        # Question history file
        self.question_history_path = self.vault_path / "question_history.json"
        self.local_first_mode = os.getenv("ENCLAVE_LOCAL_FIRST", "1").strip().lower() not in {"0", "false", "no"}
        self.require_authentication = os.getenv("ENCLAVE_REQUIRE_AUTH", "0").strip().lower() in {"1", "true", "yes"}
        self.private_profile_state_path = self.vault_path / ".active_private_profile"
        self.private_model_manager = PrivateModelManager(root_path=str(self.vault_path / "private_models"))
        self.enclave_runtime = EnclaveRuntime(vault_path=str(self.vault_path))
        self.activity_logger = ActivityLogger(vault_path=str(self.vault_path), runtime=self.enclave_runtime)
        self.wallet_service = WalletService(vault_path=str(self.vault_path))
        self.active_private_profile_name = self._load_active_private_profile_name()
        self._private_model_session = None
        self._private_model_session_name = None
        self._private_model_note = "Create a local profile to start chatting with your private files."
        self.private_files_picker = None
        self.private_folder_picker = None
        self.training_queue = None
        self._chat_history_profile = None

        # Data Sheriff core and UI state
        self.sheriff_core = SheriffCore(vault_path=str(self.vault_path), runtime=self.enclave_runtime)
        self._sheriff_last_summary: Optional[Dict[str, Any]] = None
        self._sheriff_last_error: Optional[str] = None
        self._sheriff_scan_in_progress = False
        self._sheriff_scan_paths_text = str(Path.home() / "Documents")
        self._sheriff_max_files = 2000
        self._sheriff_summary_path = self.vault_path / "sheriff" / "last_scan_summary.json"
        self._sheriff_workflow_in_progress = False
        self._sheriff_workflow_step = ""
        self._sheriff_workflow_error: Optional[str] = None
        self._sheriff_last_action_note: str = "No Sheriff actions run yet."
        self._sheriff_show_advanced = False
        self._load_sheriff_scan_summary()
        
        # Initialize MCP setup helper (after vault_path is set)
        self.mcp_setup = MCPSetupHelper(vault_path=str(self.vault_path))

        # UI state
        self.current_view = "secrets"
        self.search_query = ""
        self.selected_type = "all"
        # Track component status for UI
        self._component_status = {
            "ocr": {"status": "checking", "message": self.tr("settings.status.checking")},  # checking, ready, installing, error
            "vault": {"status": "ready", "message": self.tr("settings.status.ready")},
            "cloud_sync": {"status": "ready", "message": self.tr("settings.status.ready")},
            "training": {"status": "ready", "message": self.tr("settings.status.ready")},
            "qa": {"status": "checking", "message": self.tr("settings.status.checking")},  # checking, ready, installing, error
        }
        # Flag to prevent infinite refresh loops
        self._refreshing_settings = False
        
        # Training view auto-refresh timer (for pending/training jobs)
        self._training_refresh_timer = None
        self._training_refresh_active = False
        
        # Landing page status polling timer (for pending/training documents)
        self._landing_status_timer = None
        self._landing_status_polling_active = False
        
        # Non-blocking document processing state
        # Tracks documents being processed in background
        # Key: filename, Value: {status, step, progress, message, error}
        self.processing_documents: Dict[str, Dict[str, Any]] = {}
        
        # Inference mode: local-only for now (cloud disabled in current deployment)
        self.inference_mode = "local"
        
        # Selected adapter for focused querying (None = all adapters)
        self.selected_adapter_id = None

        # Check for existing session
        self.check_authentication()

    def _load_language_preference(self) -> str:
        """Load persisted UI language (defaults to English)."""
        try:
            if self.language_pref_path.exists():
                value = self.language_pref_path.read_text().strip().lower()
                if value in SUPPORTED_LANGUAGES:
                    return value
        except Exception as e:
            logger.debug(f"Failed to load language preference: {e}")
        return DEFAULT_LANGUAGE

    def _save_language_preference(self) -> None:
        """Persist UI language preference."""
        try:
            self.language_pref_path.write_text(self.language)
        except Exception as e:
            logger.debug(f"Failed to save language preference: {e}")

    def tr(self, key: str, **kwargs) -> str:
        """Translate key based on active language."""
        return get_text(self.language, key, **kwargs)

    def _get_current_user_id(self) -> str:
        """Return current user ID if available, otherwise 'unknown'."""
        if not self.session_data:
            return "unknown"

        user_info = self.session_data.get("user", {})
        return (
            self.session_data.get("user_id")
            or user_info.get("id")
            or user_info.get("user_id")
            or "unknown"
        )

    def set_language(self, language: str, refresh: bool = True) -> None:
        """Set UI language and optionally refresh current settings page."""
        lang = (language or DEFAULT_LANGUAGE).lower()
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        if lang == self.language:
            return

        self.language = lang
        self._save_language_preference()

        for status_info in self._component_status.values():
            if status_info.get("status") == "ready":
                status_info["message"] = self.tr("settings.status.ready")
            elif status_info.get("status") == "checking" and status_info.get("message") in {"Checking...", "Sprawdzanie..."}:
                status_info["message"] = self.tr("settings.status.checking")

        self._show_user_message(
            self.tr("language.changed", language=SUPPORTED_LANGUAGES.get(lang, lang)),
            level="info",
        )
        if hasattr(self, "sidebar") and self.sidebar is not None:
            self.sidebar.translate = self.tr
            self._refresh_sidebar_language()

        if not refresh:
            return

        if self.current_view == "settings":
            self.show_settings()
        elif self.current_view == "landing":
            self.show_landing_page()
        else:
            self._refresh_sidebar_language()

    def _refresh_sidebar_language(self) -> None:
        """Refresh sidebar labels without changing current content view."""
        if not hasattr(self, "sidebar") or self.sidebar is None:
            return

        try:
            sidebar_container = self.sidebar.build()
            if not self.page.controls:
                return
            layout = self.page.controls[0]
            if layout and isinstance(layout, ft.Row) and len(layout.controls) > 0:
                layout.controls[0] = sidebar_container
                self.page.update()
        except Exception as e:
            logger.debug(f"Failed to refresh sidebar language: {e}")

    def _load_active_private_profile_name(self) -> str:
        """Load the last active local profile name."""
        try:
            if self.private_profile_state_path.exists():
                value = self.private_profile_state_path.read_text().strip()
                if value:
                    return value
        except Exception as e:
            logger.debug(f"Failed to load active private profile: {e}")
        return "workspace"

    def _save_active_private_profile_name(self) -> None:
        """Persist the currently active local profile name."""
        try:
            self.private_profile_state_path.write_text(self.active_private_profile_name)
        except Exception as e:
            logger.debug(f"Failed to save active private profile: {e}")

    def _get_identity_label(self) -> str:
        """Return the label shown in the GUI header."""
        if self.session_data:
            return self.session_data.get("user", {}).get("email", "User")
        if self.local_first_mode:
            return "Local Device"
        return "Guest"

    def _chat_history_file_path(self) -> Path:
        """Store chat histories per local profile for cleaner demos."""
        profile_name = self.active_private_profile_name or "workspace"
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "_"
            for char in profile_name
        )
        return self.vault_path / f"chat_history_{safe_name}.json"

    def _ensure_chat_messages_loaded(self) -> None:
        """Load chat history for the current profile if needed."""
        profile_name = self.active_private_profile_name or "workspace"
        if getattr(self, "_chat_history_profile", None) == profile_name and hasattr(self, "chat_messages"):
            return
        self.chat_messages = self._load_chat_history()
        self._chat_history_profile = profile_name

    def _reset_private_model_session(self) -> None:
        """Reset the cached local Private Model session."""
        if self._private_model_session is not None:
            try:
                self._private_model_session.close()
            except Exception as e:
                logger.debug(f"Failed to close private model session: {e}")
        self._private_model_session = None
        self._private_model_session_name = None

    def _get_private_model_profiles(self) -> List[PrivateModelProfile]:
        """Return the list of configured local Private Model profiles."""
        profiles = self.private_model_manager.list_profiles()
        if not profiles:
            return [self._ensure_private_model_profile()]
        return profiles

    def _ensure_private_model_profile(self) -> PrivateModelProfile:
        """Ensure there is always an active local Private Model profile."""
        profiles = self.private_model_manager.list_profiles()
        if not profiles:
            profile = self.private_model_manager.create_profile(
                name="workspace",
                description="Default local Private Language Model for your private files.",
                keywords=["private", "local", "workspace"],
                model_name=DEFAULT_PRIVATE_MODEL_NAME,
            )
            self.active_private_profile_name = profile.name
            self._save_active_private_profile_name()
            self._private_model_note = "Workspace profile is ready. Add files or folders to begin."
            return profile

        active_name = self.active_private_profile_name
        if active_name:
            for profile in profiles:
                if profile.name == active_name:
                    return profile

        profile = profiles[0]
        self.active_private_profile_name = profile.name
        self._save_active_private_profile_name()
        return profile

    def _get_private_model_session(self):
        """Open or reuse the active local Private Model session."""
        profile = self._ensure_private_model_profile()
        if (
            self._private_model_session is not None
            and self._private_model_session_name == profile.name
        ):
            return self._private_model_session

        self._reset_private_model_session()
        self._private_model_session = self.private_model_manager.open_session(profile.name)
        self._private_model_session_name = profile.name
        return self._private_model_session

    def _get_private_model_status(self) -> Dict[str, Any]:
        """Return lightweight local Private Model profile status."""
        profile = self._ensure_private_model_profile()
        session = self.private_model_manager.open_session(profile.name)
        try:
            status = session.get_status()
        finally:
            session.close()

        status["model_name"] = profile.model_name or DEFAULT_PRIVATE_MODEL_NAME
        status["adapter_count"] = len(profile.wdva_adapters)
        return status

    def _get_private_model_documents(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List documents indexed under the active local Private Model profile."""
        import json

        profile = self._ensure_private_model_profile()
        db_path = self.private_model_manager._profile_vault_path(profile.name) / "rag.db"
        if not db_path.exists():
            return []

        query = """
            SELECT d.id, d.name, d.source_path, d.content_hash,
                   d.created_at, d.updated_at, d.metadata,
                   COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.updated_at DESC
        """
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(query).fetchall()

        documents: List[Dict[str, Any]] = []
        for row in rows:
            doc_id, name, source, hash_, created, updated, meta_str, chunk_count = row
            documents.append(
                {
                    "id": doc_id,
                    "name": name,
                    "source_path": source,
                    "content_hash": hash_,
                    "created_at": created,
                    "updated_at": updated,
                    "metadata": json.loads(meta_str or "{}"),
                    "chunk_count": chunk_count,
                }
            )

        return documents

    def _current_parser_backend(self) -> str:
        """Return the active parser backend label for demo surfaces."""
        try:
            return "liteparse" if probe_liteparse_backend() else "builtin"
        except Exception:
            return "builtin"

    def _update_module_status_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Refresh shared module-status snapshots for Vault and Wallet."""
        profiles = self._get_private_model_profiles()
        profile_status = self._get_private_model_status()
        vault_status = self.enclave_runtime.update_module_status(
            "vault",
            status="ready",
            headline="Private context ready",
            details={
                "profile_count": len(profiles),
                "document_count": profile_status.get("document_count", 0),
                "chunk_count": profile_status.get("chunk_count", 0),
                "adapter_count": profile_status.get("adapter_count", 0),
                "model_name": profile_status.get("model_name") or DEFAULT_PRIVATE_MODEL_NAME,
                "parser_backend": self._current_parser_backend(),
                "recent_access_events": len(self.enclave_runtime.list_events(limit=25, module="vault")),
            },
        )

        envelopes = self.wallet_service.list_envelopes()
        pending_requests = self.wallet_service.list_pending_requests()
        transactions = self.wallet_service.get_transactions()
        kill_switch = self.enclave_runtime.get_kill_switch()
        wallet_status = self.enclave_runtime.update_module_status(
            "wallet",
            status="warning" if (kill_switch.enabled or self.wallet_service.store.is_frozen()) else "ready",
            headline="Wallet frozen" if (kill_switch.enabled or self.wallet_service.store.is_frozen()) else "Wallet ready",
            details={
                "envelope_count": len(envelopes),
                "pending_count": len(pending_requests),
                "transaction_count": len(transactions),
                "frozen": bool(kill_switch.enabled or self.wallet_service.store.is_frozen()),
            },
        )
        return {
            "vault": vault_status,
            "wallet": wallet_status,
        }

    def _ensure_demo_wallet_envelope(self) -> Any:
        """Ensure there is at least one wallet envelope available for the demo."""
        envelopes = self.wallet_service.list_envelopes()
        if envelopes:
            return envelopes[0]

        envelope = self.wallet_service.create_envelope(
            "demo-ops",
            budget=500.0,
            requires_approval_above=75.0,
            max_per_transaction=150.0,
            daily_limit=300.0,
        )
        self.enclave_runtime.log_event(
            subject="local-ui",
            module="wallet",
            tool="create_envelope",
            decision="ALLOW",
            resource=envelope.name,
            summary="Created demo wallet envelope from GUI",
            metadata=envelope.to_dict(),
            source="gui",
        )
        self._update_module_status_snapshots()
        return envelope

    def _request_demo_wallet_purchase(self, amount: float, merchant: str, memo: str) -> None:
        """Submit a demo purchase request from the Security view."""
        try:
            envelope = self._ensure_demo_wallet_envelope()
            outcome = self.wallet_service.request_purchase(
                envelope.name,
                amount=amount,
                merchant=merchant,
                agent_id="local-ui",
                memo=memo,
            )
            self.enclave_runtime.log_event(
                subject="local-ui",
                module="wallet",
                tool="request_purchase",
                decision=outcome.decision.value.upper(),
                resource=f"{envelope.name}:{merchant}",
                summary=outcome.reason,
                metadata=outcome.to_dict(),
                source="gui",
            )
            self._update_module_status_snapshots()
            self._show_user_message(
                "Wallet request queued for approval." if outcome.requires_human_approval else "Wallet request approved.",
                level="success" if not outcome.requires_human_approval else "info",
            )
            if self.current_view == "settings_hub":
                self.show_settings_hub(active_tab="sheriff")
        except Exception as e:
            self._show_user_message(f"Wallet request failed: {e}", level="error")

    def _approve_wallet_request(self, request_id: str) -> None:
        """Approve a pending demo wallet request."""
        try:
            outcome = self.wallet_service.approve_purchase(request_id, approver="user")
            self.enclave_runtime.log_event(
                subject="user",
                module="wallet",
                tool="approve_purchase",
                decision=outcome.decision.value.upper(),
                resource=request_id,
                summary=outcome.reason,
                metadata=outcome.to_dict(),
                source="gui",
            )
            self._update_module_status_snapshots()
            self._show_user_message("Wallet request approved.", level="success")
            if self.current_view == "settings_hub":
                self.show_settings_hub(active_tab="sheriff")
        except Exception as e:
            self._show_user_message(f"Could not approve wallet request: {e}", level="error")

    def _set_global_kill_switch(self, enabled: bool) -> None:
        """Toggle the shared kill switch and keep wallet state aligned."""
        try:
            reason = "Investor demo manual override"
            self.enclave_runtime.set_kill_switch(enabled, reason=reason, actor="local-ui")
            if enabled:
                self.wallet_service.freeze_all(reason=reason)
            else:
                self.wallet_service.unfreeze_all(reason=reason)
            self._update_module_status_snapshots()
            self._show_user_message(
                "Global kill switch enabled." if enabled else "Global kill switch disabled.",
                level="warning" if enabled else "success",
            )
            if self.current_view == "settings_hub":
                self.show_settings_hub(active_tab="sheriff")
        except Exception as e:
            self._show_user_message(f"Could not update kill switch: {e}", level="error")

    def _set_active_private_profile(self, profile_name: str, refresh: bool = True) -> None:
        """Switch the active local Private Model profile."""
        if not profile_name:
            return

        if self.active_private_profile_name == profile_name:
            return

        self.active_private_profile_name = profile_name
        self._save_active_private_profile_name()
        self._reset_private_model_session()
        self._chat_history_profile = None
        self._ensure_chat_messages_loaded()
        self._private_model_note = f"{profile_name} is active and ready for local chat."

        if refresh:
            if self.current_view == "landing":
                self.show_landing_page()
            elif self.current_view == "agent":
                self.show_agent_view(active_tab="chat")
            elif self.current_view == "agent_chat":
                self._open_test_agent_chat()
            elif self.current_view == "my_data":
                self.show_my_data_view(active_tab="knowledge")

        self._show_user_message(f"Switched to profile: {profile_name}", level="success")

    def _count_ingestable_items(self, paths: List[str]) -> int:
        """Estimate how many supported files will be ingested."""
        count = 0
        for raw_path in paths:
            path = Path(raw_path).expanduser()
            if not path.exists():
                continue
            if path.is_dir():
                for file_path in path.rglob("*"):
                    if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                        count += 1
            elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                count += 1
        return count

    def _ingest_private_model_paths(self, paths: List[str], source_label: str = "files") -> None:
        """Index files or folders into the active local Private Model profile."""
        clean_paths = [str(Path(path).expanduser()) for path in paths if path]
        if not clean_paths:
            self._show_user_message("No files selected for ingest.", level="info")
            return

        profile = self._ensure_private_model_profile()
        ingestable_count = self._count_ingestable_items(clean_paths)
        self._private_model_note = (
            f"Indexing {max(ingestable_count, 1)} item(s) into {profile.name}. "
            "Your files remain local and encrypted."
        )
        self._show_user_message(
            f"Indexing {max(ingestable_count, 1)} {source_label} into {profile.name}...",
            level="info",
        )

        def run_ingest():
            try:
                session = self.private_model_manager.open_session(profile.name)
                try:
                    result = session.ingest_paths(clean_paths)
                finally:
                    session.close()

                self._reset_private_model_session()
                self._private_model_note = (
                    f"{profile.name} now has {result.added} new document(s). "
                    f"Skipped {result.skipped} unsupported or empty item(s)."
                )

                def on_success():
                    self._show_user_message(
                        f"Indexed {result.added} document(s) into {profile.name}.",
                        level="success",
                    )
                    if self.current_view == "landing":
                        self.show_landing_page()
                    elif self.current_view == "my_data":
                        self.show_my_data_view(active_tab="knowledge")
                    elif self.current_view == "agent_chat":
                        self._open_test_agent_chat()
                    elif self.current_view == "agent":
                        self.show_agent_view(active_tab="chat")

                self._run_on_ui_thread(on_success)
            except Exception as exc:
                self._private_model_note = f"Ingest failed for {profile.name}: {exc}"
                self._run_on_ui_thread(
                    lambda: self._show_user_message(
                        f"Could not index files into {profile.name}: {exc}",
                        level="error",
                    )
                )

        threading.Thread(target=run_ingest, daemon=True).start()

    def _ensure_private_model_pickers(self) -> None:
        """Create reusable file and folder pickers for Private Model ingest."""
        if self.private_files_picker is None:
            self.private_files_picker = ft.FilePicker(on_result=self._on_private_files_selected)
        if self.private_folder_picker is None:
            self.private_folder_picker = ft.FilePicker(on_result=self._on_private_folder_selected)

        if self.private_files_picker not in self.page.overlay:
            self.page.overlay.append(self.private_files_picker)
        if self.private_folder_picker not in self.page.overlay:
            self.page.overlay.append(self.private_folder_picker)

    def _open_private_files_picker(self, e=None) -> None:
        """Open a multi-file picker for local Private Model ingest."""
        self._ensure_private_model_pickers()

        if platform.system() == "Darwin":
            try:
                import subprocess

                script = '''
                tell application "System Events"
                    activate
                end tell
                set selectedFiles to choose file with prompt "Select files to add to your Private Language Model" with multiple selections allowed
                set filePaths to {}
                repeat with aFile in selectedFiles
                    set end of filePaths to POSIX path of aFile
                end repeat
                return filePaths as text
                '''

                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0 and result.stdout.strip():
                    class FakeFile:
                        def __init__(self, path: str):
                            self.path = path.strip()
                            self.name = Path(path.strip()).name

                    class FakeEvent:
                        def __init__(self, files):
                            self.files = files

                    files = [FakeFile(path) for path in result.stdout.strip().split(", ") if path.strip()]
                    if files:
                        self._on_private_files_selected(FakeEvent(files))
                        return
            except Exception as ex:
                logger.debug(f"macOS private file picker fallback failed: {ex}")

        self.private_files_picker.pick_files(
            allow_multiple=True,
            allowed_extensions=PRIVATE_MODEL_IMPORT_EXTENSIONS,
        )

    def _open_private_folder_picker(self, e=None) -> None:
        """Open a folder picker for bulk Private Model ingest."""
        self._ensure_private_model_pickers()

        if platform.system() == "Darwin":
            try:
                import subprocess

                script = '''
                tell application "System Events"
                    activate
                end tell
                set selectedFolder to choose folder with prompt "Select a folder to add to your Private Language Model"
                return POSIX path of selectedFolder
                '''

                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0 and result.stdout.strip():
                    class FakeEvent:
                        def __init__(self, path: str):
                            self.path = path

                    self._on_private_folder_selected(FakeEvent(result.stdout.strip()))
                    return
            except Exception as ex:
                logger.debug(f"macOS private folder picker fallback failed: {ex}")

        self.private_folder_picker.get_directory_path()

    def _on_private_files_selected(self, e: ft.FilePickerResultEvent) -> None:
        """Handle local file selection for Private Model ingest."""
        if not e.files:
            return
        self._ingest_private_model_paths([file.path for file in e.files if file.path], source_label="files")

    def _on_private_folder_selected(self, e: ft.FilePickerResultEvent) -> None:
        """Handle local folder selection for Private Model ingest."""
        if not e.path:
            return
        self._ingest_private_model_paths([e.path], source_label="folder")

    def _open_create_profile_dialog(self, e=None) -> None:
        """Create a new local Private Model profile from the GUI."""
        existing_names = {profile.name for profile in self._get_private_model_profiles()}
        suggested_name = f"profile-{len(existing_names) + 1}"
        while suggested_name in existing_names:
            suggested_name = f"profile-{len(existing_names) + 2}"

        name_field = ft.TextField(
            label="Profile name",
            value=suggested_name,
            autofocus=True,
            border_radius=10,
        )
        description_field = ft.TextField(
            label="What is this profile for?",
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=10,
            value="A local workspace for private company and project context.",
        )
        keywords_field = ft.TextField(
            label="Keywords (comma separated)",
            border_radius=10,
            value="private, local, secure",
        )
        model_dropdown = ft.Dropdown(
            label="Base model",
            value=DEFAULT_PRIVATE_MODEL_NAME,
            border_radius=10,
            options=[
                ft.dropdown.Option("mlx-community/Qwen2.5-1.5B-Instruct-4bit", "Qwen 2.5 1.5B Instruct"),
                ft.dropdown.Option("mlx-community/Qwen3-0.6B-4bit", "Qwen 3 0.6B"),
                ft.dropdown.Option("mlx-community/Phi-4-mini-instruct-4bit", "Phi-4 Mini"),
                ft.dropdown.Option("mlx-community/Llama-3.2-1B-Instruct-4bit", "Llama 3.2 1B"),
            ],
        )

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=LightTheme.BG_ELEVATED,
            title=ft.Text("Create Private Model Profile", size=18, weight=ft.FontWeight.W_600),
            content=ft.Container(
                width=460,
                content=ft.Column(
                    [
                        ft.Text(
                            "Profiles let you separate private workspaces, models, and WDVA layers on the same device.",
                            size=13,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        name_field,
                        description_field,
                        keywords_field,
                        model_dropdown,
                    ],
                    spacing=16,
                    tight=True,
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda evt: self._close_dialog(dialog)),
                ft.ElevatedButton(
                    "Create Profile",
                    icon=ft.Icons.ADD_ROUNDED,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        color="white",
                    ),
                    on_click=lambda evt: self._create_private_profile_from_dialog(
                        dialog,
                        name_field,
                        description_field,
                        keywords_field,
                        model_dropdown,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _create_private_profile_from_dialog(
        self,
        dialog: ft.AlertDialog,
        name_field: ft.TextField,
        description_field: ft.TextField,
        keywords_field: ft.TextField,
        model_dropdown: ft.Dropdown,
    ) -> None:
        """Persist a profile created from the GUI dialog."""
        name = (name_field.value or "").strip()
        if not name:
            self._show_user_message("Profile name is required.", level="warning")
            return

        existing_names = {profile.name for profile in self._get_private_model_profiles()}
        if name in existing_names:
            self._show_user_message(f"Profile '{name}' already exists.", level="warning")
            return

        keywords = [
            item.strip()
            for item in (keywords_field.value or "").split(",")
            if item.strip()
        ]
        profile = self.private_model_manager.create_profile(
            name=name,
            description=(description_field.value or "").strip(),
            keywords=keywords,
            model_name=model_dropdown.value or DEFAULT_PRIVATE_MODEL_NAME,
        )
        self._close_dialog(dialog)
        self._set_active_private_profile(profile.name, refresh=False)
        self._private_model_note = f"{profile.name} is ready. Add files to start chatting locally."

        if self.current_view == "agent_chat":
            self._open_test_agent_chat()
        elif self.current_view == "my_data":
            self.show_my_data_view(active_tab="library")
        else:
            self.show_landing_page()

    def _enter_local_first_mode(self) -> None:
        """Boot the app directly into a local-only investor demo mode."""
        logger.info("Starting Enclave in local-first mode")
        self.initialize_vault()
        self._show_initial_authenticated_view()
        self._show_user_message(
            "Running in local-first mode. Your files and model context stay on this Mac.",
            level="info",
        )

    def check_authentication(self):
        """Check if user is authenticated."""
        # Try to load existing session
        self.session_data = AuthScreen.load_session()

        if self.session_data:
            # User is authenticated, initialize vault
            self.initialize_vault()

            # Show onboarding for first-time users, otherwise open dashboard.
            self._show_initial_authenticated_view()
        else:
            if self.local_first_mode and not self.require_authentication:
                self._enter_local_first_mode()
                return
            # Show authentication screen
            self.show_auth_screen()

    def show_auth_screen(self):
        """Show authentication screen."""
        auth_screen = AuthScreen(
            page=self.page,
            backend_url=self.backend_url,
            on_auth_success=self.on_auth_success,
            language=self.language,
            translate=self.tr,
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

        # Show onboarding for first-time users, otherwise open dashboard.
        self._show_initial_authenticated_view()
        
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
        
        # Defer heavier OCR setup until first use.
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
            self.tr("settings.qa_setup.dialog_title"),
            self.tr("settings.qa_setup.preparing"),
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
                            time_remaining_text.value = self.tr("settings.setup.time_remaining", time=time_remaining)
                    
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
                                self._component_status["qa"]["message"] = self.tr("settings.status.downloading.optimized_ai")
                        else:
                            if percent is not None:
                                self._component_status["qa"]["message"] = f"Downloading TinyLlama... {percent:.1f}%"
                            else:
                                self._component_status["qa"]["message"] = self.tr("settings.status.downloading.tinyllama")
                    elif "gotowe" in message.lower() or "ready" in message.lower() or "available" in message.lower():
                        self._component_status["qa"]["status"] = "ready"
                        if is_mlx:
                            self._component_status["qa"]["message"] = self.tr("settings.status.ready.optimized_ai")
                        else:
                            self._component_status["qa"]["message"] = self.tr("settings.status.ready.local_ai")
                    
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
                    self._component_status["qa"]["message"] = self.tr("settings.status.ready.mlx")
                else:
                    self._component_status["qa"]["status"] = "ready"
                    self._component_status["qa"]["message"] = self.tr("settings.status.ready.ollama")
                progress_text.value = self.tr("settings.qa_setup.ready")
                progress_bar.value = 1.0
                progress_percent.value = "100%"
                time_remaining_text.value = ""
                progress_dialog.actions = [
                    ft.TextButton(self.tr("common.ok"), on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
                ]
            else:
                progress_text.value = f"❌ {message}"
                progress_bar.value = None
                progress_percent.value = ""
                time_remaining_text.value = ""
                self._component_status["qa"]["status"] = "error"
                self._component_status["qa"]["message"] = message
                progress_dialog.actions = [
                    ft.TextButton(self.tr("common.ok"), on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
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
                ft.TextButton(self.tr("common.ok"), on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update()),
            ]
        
        self.page.update()
    
    def _get_qa_setup_tooltip(self) -> str:
        """Get tooltip text for Q&A setup button based on available method."""
        if not self.qa_generator:
            return self.tr("settings.qa_setup.tooltip.setup")
        
        qa_status = self.qa_generator.get_qa_status()
        if qa_status.get("mlx_available") and not qa_status.get("mlx_initialized"):
            return self.tr("settings.qa_setup.tooltip.download_optimized")
        elif qa_status.get("preferred_method") == "MLX":
            return self.tr("settings.qa_setup.tooltip.optimized_ready")
        else:
            return self.tr("settings.qa_setup.tooltip.download_tinyllama")

    def _setup_ollama_with_progress(self):
        """
        Setup Ollama OCR with visible progress dialog showing percentage and time remaining.
        """
        progress_dialog, progress_text, progress_bar, progress_percent, time_remaining_text = self._create_progress_dialog(
            self.tr("settings.ocr_setup.dialog_title"),
            self.tr("settings.ocr_setup.preparing"),
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
                        time_remaining_text.value = self.tr("settings.setup.time_remaining", time=time_remaining)
                    
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

    def _setup_ocr_with_progress(self):
        """Setup OCR stack (SmolDocling preferred, Ollama fallback)."""
        try:
            if self.pdf_processor is None:
                self._initialize_pdf_processor()

            if self.pdf_processor and self.pdf_processor.has_document_extraction_backend():
                self._component_status["ocr"]["status"] = "ready"
                backend_label = self.pdf_processor.get_backend_status_label()
                self._component_status["ocr"]["message"] = f"Ready ({backend_label})"
                self._show_user_message(
                    f"Document extraction is ready ({backend_label}).",
                    level="info",
                )
                return

            # Fallback path when SmolDocling is unavailable.
            self._setup_ollama_with_progress()

            if self.pdf_processor and self.pdf_processor.has_document_extraction_backend():
                self._component_status["ocr"]["status"] = "ready"
                self._component_status["ocr"]["message"] = (
                    f"Ready ({self.pdf_processor.get_backend_status_label()})"
                )
        except Exception as e:
            logger.error(f"OCR setup failed: {e}")
            self._component_status["ocr"]["status"] = "error"
            self._component_status["ocr"]["message"] = f"Error: {str(e)}"
            self._show_user_message(f"OCR setup failed: {str(e)}", level="error")

    def _run_local_setup(self):
        """One-click local setup for first value (OCR + local QA)."""
        try:
            ran_any_step = False

            # Ensure processors exist.
            if self.pdf_processor is None:
                self._initialize_pdf_processor()

            if self.qa_generator is None:
                self.qa_generator = QAGenerator()

            # OCR readiness.
            ocr_ready = bool(
                self.pdf_processor and
                self.pdf_processor.has_document_extraction_backend()
            )
            if not ocr_ready:
                ran_any_step = True
                self._setup_ocr_with_progress()

            # QA readiness (MLX preferred if available).
            qa_ready = False
            if self.qa_generator:
                qa_status = self.qa_generator.get_qa_status()
                if qa_status.get("mlx_available"):
                    qa_ready = bool(qa_status.get("mlx_initialized"))
                else:
                    qa_ready = bool(qa_status.get("qa_model_available"))

            if not qa_ready:
                ran_any_step = True
                self._setup_qa_model_with_progress()

            if ran_any_step:
                self._show_user_message("Local setup completed. You can now index and ask immediately.", level="success")
            else:
                self._show_user_message("Local setup already ready.", level="info")
        except Exception as e:
            logger.error(f"Local setup failed: {e}")
            self._show_actionable_error(
                e,
                title="Local setup failed",
                context="setup",
                fix_label="Open Settings",
                fix_action=lambda: self.show_settings(),
            )
    
    def _auto_setup_components(self):
        """Automatically setup components that need configuration."""
        try:
            # Check what needs setup
            needs_ocr = False
            needs_qa = False
            
            if hasattr(self, 'pdf_processor') and self.pdf_processor:
                if not self.pdf_processor.has_document_extraction_backend():
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
            # Prefer LiteParse if present, otherwise fall back to the legacy OCR stack.
            needs_setup = True
            smoldocling_available = False
            liteparse_available = False
            
            try:
                liteparse_available = probe_liteparse_backend()
                if liteparse_available:
                    needs_setup = False
                    logger.debug("Document extraction ready (LiteParse) - skipping setup dialog")

                # Check if SmolDocling is already available and working
                import platform
                if needs_setup and platform.machine() == "arm64":
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
                elif not liteparse_available:
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
                            self._component_status["ocr"]["message"] = (
                                f"Ready ({self.pdf_processor.get_backend_status_label()})"
                            )
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
            if self.pdf_processor.has_document_extraction_backend():
                self._component_status["ocr"]["status"] = "ready"
                self._component_status["ocr"]["message"] = (
                    f"Ready ({self.pdf_processor.get_backend_status_label()})"
                )
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
                if self.pdf_processor.has_document_extraction_backend():
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
            if not self.pdf_processor.has_document_extraction_backend():
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

    def _is_onboarding_completed(self) -> bool:
        """Check if onboarding was already completed."""
        return self.onboarding_state_path.exists()

    def _mark_onboarding_completed(self) -> None:
        """Persist onboarding completion marker."""
        try:
            self.onboarding_state_path.write_text(datetime.now().isoformat())
        except Exception as e:
            logger.warning(f"Failed to persist onboarding marker: {e}")

    def _should_show_onboarding(self) -> bool:
        """Decide if onboarding should be shown."""
        if self._is_onboarding_completed():
            return False
        return self._is_first_time_user()

    def _show_initial_authenticated_view(self):
        """Show onboarding or landing view after successful authentication."""
        if self._should_show_onboarding():
            self.current_view = "welcome"
            self.show_welcome_screen()
            return
        self.show_landing_page()

    def _handle_onboarding_step_action(self, step_id: str) -> None:
        """Route onboarding step CTAs to high-value product actions."""
        try:
            self._mark_onboarding_completed()
            self.show_landing_page()

            if step_id == "connect":
                self._run_local_setup()
                self.on_nav_change(5)
                self._show_user_message(
                    self.tr("onboarding.info.connect"),
                    level="info",
                )
                return

            if step_id == "encrypt":
                self.on_nav_change(0)
                self.show_add_dialog(None, default_type="secret")
                return

            if step_id == "train":
                self.on_nav_change(7)
                return

            if step_id == "ask":
                self._open_test_agent_chat()
                return

            self.show_landing_page()
        except Exception as e:
            self._show_actionable_error(
                e,
                title=self.tr("onboarding.error.open_step"),
                context="auth",
                fix_label="Open dashboard",
                fix_action=self.show_landing_page,
            )

    def show_welcome_screen(self):
        """Show welcome screen for first-time users."""
        welcome = WelcomeScreen(
            page=self.page,
            on_start=self._on_welcome_complete,
            on_add_sample=self._add_sample_data,
            on_step_action=self._handle_onboarding_step_action,
            translate=self.tr,
        )
        
        self.page.clean()
        self.page.add(welcome.get_view())
        self.page.update()
    
    def _on_welcome_complete(self):
        """Called when welcome screen is dismissed."""
        self._mark_onboarding_completed()
        # Always go to landing page after welcome screen
        self.show_landing_page()
    
    def _add_sample_data(self):
        """Add sample data for first-time users."""
        try:
            if not self.vault:
                raise RuntimeError("Vault not initialized")
            
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
            self._show_user_message(
                self.tr("onboarding.success.sample", count=added_count),
                level="success",
            )
            
        except Exception as e:
            self._show_actionable_error(
                e,
                title=self.tr("onboarding.error.add_sample"),
                context="vault",
                fix_label=self.tr("onboarding.fix.add_secret"),
                fix_action=lambda: self.show_add_dialog(None, default_type="secret"),
            )

    def _show_user_message(self, message: str, level: str = "info") -> None:
        """Show a short status message with consistent styling."""
        colors = {
            "info": LightTheme.ACCENT_PRIMARY,
            "success": LightTheme.ACCENT_SUCCESS,
            "warning": LightTheme.ACCENT_WARNING,
            "error": LightTheme.ACCENT_ERROR,
        }
        color = colors.get(level, LightTheme.ACCENT_PRIMARY)

        def _apply():
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color="white"),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()

        try:
            _apply()
        except Exception as e:
            # Fallback for background-thread calls.
            logger.debug(f"Deferred UI message update: {e}")

            async def _deferred():
                try:
                    _apply()
                except Exception as inner:
                    logger.debug(f"Could not render deferred user message: {inner}")

            try:
                self.page.run_task(_deferred)
            except Exception as inner:
                logger.debug(f"Failed to queue deferred message update: {inner}")

    def _run_on_ui_thread(self, callback: Callable[[], None]) -> None:
        """Run UI callback safely from any thread."""
        async def _deferred():
            try:
                callback()
            except Exception as e:
                logger.debug(f"Deferred UI callback failed: {e}")

        try:
            self.page.run_task(_deferred)
        except Exception as e:
            logger.debug(f"Failed to schedule UI callback: {e}")

    def _refresh_sheriff_views(self) -> None:
        """Refresh Sheriff-related views without assuming current thread."""

        def _refresh():
            if self.current_view == "landing":
                self.show_landing_page()
            elif self.current_view == "settings_hub":
                self.show_settings_hub(active_tab="sheriff")

        try:
            _refresh()
        except Exception:
            self._run_on_ui_thread(_refresh)

    def _show_actionable_error(
        self,
        error: Exception,
        title: str = "Something went wrong",
        context: Optional[str] = None,
        fix_label: Optional[str] = None,
        fix_action: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Show user-friendly error with optional repair action.

        Uses error_helper to translate technical failures into clear next steps.
        """
        technical_error = str(error)
        user_msg, help_link = make_user_friendly(technical_error, context=context)
        logger.error(f"{title}: {technical_error}")

        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=LightTheme.BG_ELEVATED,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=LightTheme.ACCENT_ERROR, size=22),
                    ft.Text(title, size=17, weight=ft.FontWeight.W_600),
                ],
                spacing=10,
            ),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    [
                        ft.Text(user_msg, size=14, color=LightTheme.TEXT_PRIMARY),
                        ft.Container(height=8),
                        ft.Text(
                            "Technical details are logged locally for troubleshooting.",
                            size=12,
                            color=LightTheme.TEXT_MUTED,
                        ),
                        ft.Container(height=8, visible=bool(help_link and help_link != "SESSION_EXPIRED")),
                        ft.Text(
                            f"Help: {help_link}",
                            size=12,
                            color=LightTheme.ACCENT_PRIMARY,
                            visible=bool(help_link and help_link != "SESSION_EXPIRED"),
                        ),
                    ],
                    spacing=0,
                    tight=True,
                ),
            ),
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def close_dialog(_):
            dialog.open = False
            self.page.update()

        actions = [ft.TextButton("Close", on_click=close_dialog)]

        if help_link == "SESSION_EXPIRED":
            def relogin(_):
                close_dialog(None)
                self.logout()

            actions.append(
                ft.ElevatedButton(
                    "Log in again",
                    icon=ft.Icons.LOGOUT_ROUNDED,
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    on_click=relogin,
                )
            )
        elif fix_action:
            def run_fix(_):
                close_dialog(None)
                try:
                    fix_action()
                except Exception as fix_error:
                    self._show_user_message(
                        format_error_snackbar(str(fix_error)),
                        level="error",
                    )

            actions.append(
                ft.ElevatedButton(
                    fix_label or "Fix now",
                    icon=ft.Icons.BUILD_ROUNDED,
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    on_click=run_fix,
                )
            )

        dialog.actions = actions
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _collect_readiness_steps(
        self,
        rag_document_count: int,
        adapter_count: int,
        backend_connected: bool,
    ) -> List[Dict[str, Any]]:
        """Evaluate top-level app readiness states for first-value tasks."""
        qa_ready = self._component_status.get("qa", {}).get("status") == "ready"
        inference_ready = backend_connected if self.inference_mode == "cloud" else qa_ready
        sync_ready = bool(self.backend_url) and self.cloud_sync is not None and backend_connected

        return [
            {
                "id": "key",
                "label": self.tr("readiness.step.key.label"),
                "ready": self.key_path.exists(),
                "hint": self.tr("readiness.step.key.hint"),
                "fix_label": self.tr("readiness.step.key.fix"),
            },
            {
                "id": "dataset",
                "label": self.tr("readiness.step.dataset.label"),
                "ready": rag_document_count > 0,
                "hint": self.tr("readiness.step.dataset.hint"),
                "fix_label": self.tr("readiness.step.dataset.fix"),
            },
            {
                "id": "adapter",
                "label": self.tr("readiness.step.adapter.label"),
                "ready": adapter_count > 0,
                "hint": self.tr("readiness.step.adapter.hint"),
                "fix_label": self.tr("readiness.step.adapter.fix"),
            },
            {
                "id": "inference",
                "label": self.tr("readiness.step.inference.label"),
                "ready": inference_ready,
                "hint": self.tr("readiness.step.inference.hint"),
                "fix_label": self.tr("readiness.step.inference.fix"),
            },
            {
                "id": "sync",
                "label": self.tr("readiness.step.sync.label"),
                "ready": sync_ready,
                "hint": self.tr("readiness.step.sync.hint"),
                "fix_label": self.tr("readiness.step.sync.fix"),
            },
        ]

    def _run_readiness_fix(self, step_id: str) -> None:
        """Execute contextual fix action for the first incomplete readiness step."""
        try:
            if step_id == "key":
                self.on_nav_change(0)
                self.show_add_dialog(None, default_type="secret")
                return

            if step_id == "dataset":
                self._on_upload_click(None)
                return

            if step_id == "adapter":
                self.on_nav_change(7)
                return

            if step_id == "inference":
                if self.inference_mode == "local":
                    self._run_local_setup()
                else:
                    self.check_backend_connectivity()
                    self.on_nav_change(5)
                return

            if step_id == "sync":
                self.on_nav_change(5)
                return
        except Exception as e:
            self._show_actionable_error(
                e,
                title=self.tr("readiness.error.fix"),
                context="sync",
                fix_label=self.tr("readiness.fix.open_setup"),
                fix_action=lambda: self.on_nav_change(5),
            )

    def _build_readiness_strip(
        self,
        rag_document_count: int,
        adapter_count: int,
        backend_connected: bool,
    ) -> ft.Container:
        """Build landing-page readiness strip with one-click recovery action."""
        steps = self._collect_readiness_steps(
            rag_document_count=rag_document_count,
            adapter_count=adapter_count,
            backend_connected=backend_connected,
        )
        next_incomplete = next((step for step in steps if not step["ready"]), None)

        chips = []
        for step in steps:
            ready = step["ready"]
            chips.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    border_radius=20,
                    bgcolor=(LightTheme.ACCENT_SUCCESS + "18") if ready else (LightTheme.ACCENT_WARNING + "12"),
                    border=ft.border.all(
                        1,
                        (LightTheme.ACCENT_SUCCESS + "50") if ready else (LightTheme.ACCENT_WARNING + "40"),
                    ),
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED if ready else ft.Icons.PENDING_ROUNDED,
                                size=14,
                                color=LightTheme.ACCENT_SUCCESS if ready else LightTheme.ACCENT_WARNING,
                            ),
                            ft.Text(
                                step["label"],
                                size=11,
                                weight=ft.FontWeight.W_500,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                        ],
                        spacing=5,
                        tight=True,
                    ),
                )
            )

        return ft.Container(
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            border_radius=10,
            bgcolor=LightTheme.BG_ELEVATED,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                self.tr("readiness.title"),
                                size=13,
                                weight=ft.FontWeight.W_600,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                self.tr("readiness.all_ready")
                                if next_incomplete is None
                                else self.tr("readiness.next", hint=next_incomplete["hint"]),
                                size=12,
                                color=LightTheme.TEXT_MUTED,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.Row(
                                chips,
                                spacing=8,
                                scroll=ft.ScrollMode.AUTO,
                                expand=True,
                            ),
                            ft.ElevatedButton(
                                self.tr("readiness.action.ready")
                                if next_incomplete is None
                                else next_incomplete["fix_label"],
                                icon=ft.Icons.CHECK_ROUNDED
                                if next_incomplete is None
                                else ft.Icons.BUILD_ROUNDED,
                                disabled=next_incomplete is None,
                                on_click=(
                                    (lambda e, sid=next_incomplete["id"]: self._run_readiness_fix(sid))
                                    if next_incomplete
                                    else None
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    color="white",
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=0,
            ),
        )

    def _collect_sheriff_wizard_steps(self) -> List[Dict[str, Any]]:
        """Collect progress for 3-step landing wizard (setup -> scan -> protect)."""
        mcp_status = {
            "claude_installed": False,
            "cursor_installed": False,
            "chatgpt_installed": False,
            "mcp_configured": False,
        }
        try:
            mcp_status = self.mcp_setup.get_setup_status()
        except Exception as e:
            logger.debug(f"Could not read MCP setup status for sheriff wizard: {e}")

        claude_installed = bool(mcp_status.get("claude_installed"))
        cursor_installed = bool(mcp_status.get("cursor_installed"))
        chatgpt_installed = bool(mcp_status.get("chatgpt_installed"))
        mcp_configured = bool(mcp_status.get("mcp_configured"))
        setup_ready = mcp_configured or not (claude_installed or cursor_installed)
        if mcp_configured:
            setup_hint = "MCP broker configured."
        elif claude_installed or cursor_installed:
            setup_hint = "Auto-configure MCP broker for installed AI clients."
        elif chatgpt_installed:
            setup_hint = "ChatGPT desktop detected, but local MCP is currently unsupported."
        else:
            setup_hint = "No local client detected. You can still use Sheriff locally."

        summary = self._sheriff_last_summary or {}
        total_files = int(summary.get("total_files", 0) or 0)
        scanned_at = summary.get("scanned_at")
        scan_ready = total_files > 0
        if scan_ready and scanned_at:
            scan_hint = f"Last scan processed {total_files} files ({str(scanned_at)[:19]})."
        elif scan_ready:
            scan_hint = f"Last scan processed {total_files} files."
        else:
            scan_hint = "Run one-click risk scan to detect critical and sensitive files."

        try:
            rules_count = len(self.sheriff_core.policy.list_rules())
        except Exception:
            rules_count = 0
        try:
            enforcement = self.sheriff_core.enforcement_status()
        except Exception:
            enforcement = {"enabled": False, "message": "Enforcement status unavailable."}
        enforcement_enabled = bool(enforcement.get("enabled"))

        protect_ready = rules_count > 0 and enforcement_enabled
        if protect_ready:
            protect_hint = f"{rules_count} rule(s) active with OS-level enforcement."
        elif rules_count > 0:
            protect_hint = "Rules are active, but OS-level enforcement is not installed yet."
        else:
            protect_hint = "Enable deny-by-default consent barrier for risky paths."

        return [
            {
                "id": "setup",
                "title": "1. Install + Permissions",
                "hint": setup_hint,
                "ready": setup_ready,
                "action_label": "Auto Configure MCP",
            },
            {
                "id": "scan",
                "title": "2. One-click Scan",
                "hint": scan_hint,
                "ready": scan_ready,
                "action_label": "Run Risk Scan",
            },
            {
                "id": "protect",
                "title": "3. Protect Now",
                "hint": protect_hint,
                "ready": protect_ready,
                "action_label": "Enable Protection",
            },
        ]

    def _get_sheriff_posture(self) -> Dict[str, Any]:
        """Return high-level protection posture for simple UX messaging."""
        summary = self._sheriff_last_summary or {}
        scanned_files = int(summary.get("total_files", 0) or 0)
        critical = int(summary.get("critical_count", 0) or 0)
        sensitive = int(summary.get("sensitive_count", 0) or 0)

        try:
            rules_count = len(self.sheriff_core.policy.list_rules())
        except Exception:
            rules_count = 0

        try:
            enforcement = self.sheriff_core.enforcement_status()
        except Exception:
            enforcement = {"enabled": False, "message": "Enforcement status unavailable."}
        enforcement_enabled = bool(enforcement.get("enabled"))

        if rules_count <= 0:
            status = "NOT_PROTECTED"
            headline = "Protection not active"
            detail = "Consent barrier rules are not active yet."
            color = LightTheme.ACCENT_ERROR
            security_answer = "No. Critical data is not protected yet."
        elif not enforcement_enabled:
            status = "PARTIAL"
            headline = "Partially protected"
            detail = "Consent rules are active, but OS-level blocking is not installed."
            color = LightTheme.ACCENT_WARNING
            security_answer = "Partly. Brokered access is controlled, but direct filesystem reads may still bypass Sheriff."
        elif scanned_files <= 0:
            status = "PARTIAL"
            headline = "Protection partially active"
            detail = "OS enforcement is ready, but no scan results yet."
            color = LightTheme.ACCENT_WARNING
            security_answer = "Not fully yet. Run a scan so Sheriff can protect discovered critical files."
        else:
            status = "PROTECTED"
            headline = "Protection active"
            detail = f"{rules_count} rule(s) active. Last scan: {critical} critical, {sensitive} sensitive."
            color = LightTheme.ACCENT_SUCCESS
            security_answer = "Yes. Access to protected critical files requires consent or a valid lease."

        return {
            "status": status,
            "headline": headline,
            "detail": detail,
            "color": color,
            "rules_count": rules_count,
            "scanned_files": scanned_files,
            "enforcement_enabled": enforcement_enabled,
            "enforcement_message": str(enforcement.get("message", "")),
            "security_answer": security_answer,
        }

    def _get_sheriff_recommended_paths(self, max_paths: int = 25) -> List[str]:
        """Compute top-risk paths from latest scan, fallback to scan roots."""
        summary = self._sheriff_last_summary or {}
        findings = summary.get("findings", [])
        candidate_paths: List[str] = []

        for finding in findings:
            label = finding.get("label")
            if label in {"CRITICAL", "SENSITIVE"} and finding.get("path"):
                candidate_paths.append(str(finding["path"]))
            if len(candidate_paths) >= max_paths:
                break

        if not candidate_paths:
            candidate_paths = self._parse_sheriff_scan_paths()

        unique_paths: List[str] = []
        seen = set()
        for path in candidate_paths:
            if path and path not in seen:
                unique_paths.append(path)
                seen.add(path)
        return unique_paths

    def _run_sheriff_secure_now(self) -> None:
        """One-click value flow: configure MCP -> scan -> protect."""
        if self._sheriff_workflow_in_progress or self._sheriff_scan_in_progress:
            return

        self._sheriff_workflow_in_progress = True
        self._sheriff_workflow_step = "Configuring AI apps..."
        self._sheriff_workflow_error = None
        self._sheriff_last_action_note = "Secure flow started. Step 1/3: configuring AI apps."
        self._refresh_sheriff_views()
        self._show_user_message("Starting one-click protection workflow...", level="info")

        def worker():
            try:
                # Step 1: App MCP config (best effort)
                try:
                    result = self.mcp_setup.auto_configure_all_clients()
                    configured_count = int(result.get("configured_count", 0))
                    if configured_count > 0:
                        self._show_user_message(f"MCP ready for {configured_count} app(s).", level="success")
                except Exception as ex:
                    logger.debug(f"MCP auto-config step failed: {ex}")

                # Step 2: Scan
                self._sheriff_workflow_step = "Scanning local files..."
                self._sheriff_last_action_note = "Secure flow running. Step 2/3: scanning files."
                self._refresh_sheriff_views()
                paths = self._parse_sheriff_scan_paths()
                max_files = max(1, int(self._sheriff_max_files or 2000))
                summary = self.sheriff_core.scan_risk(paths=paths, max_files=max_files)
                self._sheriff_last_summary = summary.model_dump(mode="json")
                self._save_sheriff_scan_summary()

                # Step 3: Protect
                self._sheriff_workflow_step = "Applying consent barrier..."
                self._sheriff_last_action_note = "Secure flow running. Step 3/3: applying protection rules."
                self._refresh_sheriff_views()
                paths_to_protect = self._get_sheriff_recommended_paths(max_paths=25)
                rules = self.sheriff_core.protect_now(paths=paths_to_protect)
                self._sheriff_last_action_note = (
                    f"Secure flow complete. Added {len(rules)} rule(s); "
                    f"scan found {summary.critical_count} critical files."
                )
                self._show_user_message(
                    f"Protection active: {len(rules)} rule(s), scan found {summary.critical_count} critical file(s).",
                    level="success",
                )
            except Exception as ex:
                logger.error(f"Secure now workflow failed: {ex}")
                self._sheriff_workflow_error = str(ex)
                self._sheriff_last_action_note = f"Secure flow failed: {ex}"
                self._show_user_message(f"Secure now failed: {ex}", level="error")
            finally:
                self._sheriff_workflow_in_progress = False
                self._sheriff_workflow_step = ""
                self._refresh_sheriff_views()

        threading.Thread(target=worker, daemon=True).start()

    def _run_sheriff_wizard_action(self, step_id: str) -> None:
        """Execute action for selected sheriff wizard step."""
        if step_id == "setup":
            try:
                result = self.mcp_setup.auto_configure_all_clients()
                configured_count = int(result.get("configured_count", 0))
                if configured_count > 0:
                    self._show_user_message(
                        f"MCP ready for {configured_count} app(s). Restart them now.",
                        level="success",
                    )
                else:
                    self._show_user_message(
                        "No supported app detected for auto-setup. Use manual setup.",
                        level="info",
                    )
            except Exception as e:
                logger.error(f"Auto-configure MCP clients failed: {e}")
                self._show_user_message(f"MCP auto-configure failed: {e}", level="error")

            if self.current_view == "landing":
                self.show_landing_page()
            return
        if step_id == "scan":
            self._start_sheriff_scan()
            return
        if step_id == "protect":
            self._protect_sheriff_recommended()
            return

    def _build_sheriff_quickstart_wizard(self) -> ft.Container:
        """Build landing quick-start wizard for Data Sheriff."""
        steps = self._collect_sheriff_wizard_steps()
        next_incomplete = next((step for step in steps if not step["ready"]), None)
        posture = self._get_sheriff_posture()

        cards: List[ft.Control] = []
        for step in steps:
            ready = bool(step["ready"])
            cards.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.CHECK_CIRCLE_ROUNDED if ready else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED,
                                        size=16,
                                        color=LightTheme.ACCENT_SUCCESS if ready else LightTheme.ACCENT_WARNING,
                                    ),
                                    ft.Text(
                                        step["title"],
                                        size=13,
                                        weight=ft.FontWeight.W_600,
                                        color=LightTheme.TEXT_PRIMARY,
                                        expand=True,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Text(
                                step["hint"],
                                size=12,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.all(12),
                    border_radius=10,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border=ft.border.all(
                        1,
                        (LightTheme.ACCENT_SUCCESS + "50") if ready else LightTheme.BORDER_COLOR,
                    ),
                    width=300,
                )
            )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.GPP_GOOD_ROUNDED, size=20, color=LightTheme.ACCENT_SUCCESS),
                            ft.Text(
                                "Data Sheriff Quick Start",
                                size=16,
                                weight=ft.FontWeight.W_700,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Container(expand=True),
                            ft.Text(
                                "Protection enabled" if next_incomplete is None else "3 steps to enable protection",
                                size=12,
                                color=LightTheme.TEXT_MUTED,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.SECURITY_ROUNDED, size=16, color=posture["color"]),
                                ft.Column(
                                    [
                                        ft.Text(posture["headline"], size=13, weight=ft.FontWeight.W_600, color=posture["color"]),
                                        ft.Text(posture["detail"], size=12, color=LightTheme.TEXT_SECONDARY),
                                    ],
                                    spacing=2,
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=ft.padding.all(10),
                        border_radius=8,
                        bgcolor=LightTheme.BG_HOVER,
                        border=ft.border.all(1, posture["color"] + "40"),
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        f"Is my data secure right now? {posture['security_answer']}",
                        size=12,
                        color=posture["color"],
                    ),
                    ft.Text(
                        posture.get("enforcement_message", ""),
                        size=11,
                        color=LightTheme.TEXT_MUTED,
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        cards,
                        spacing=12,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Secure My Data Now",
                                icon=ft.Icons.SHIELD_ROUNDED,
                                disabled=self._sheriff_workflow_in_progress or self._sheriff_scan_in_progress,
                                on_click=lambda e: self._run_sheriff_secure_now(),
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.ACCENT_SUCCESS,
                                    color="white",
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                            ft.Text(
                                self._sheriff_workflow_step if self._sheriff_workflow_in_progress else "",
                                size=12,
                                color=LightTheme.TEXT_MUTED,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "All Set" if next_incomplete is None else next_incomplete["action_label"],
                                icon=ft.Icons.CHECK_ROUNDED if next_incomplete is None else ft.Icons.PLAY_ARROW_ROUNDED,
                                disabled=next_incomplete is None or self._sheriff_scan_in_progress or self._sheriff_workflow_in_progress,
                                on_click=(
                                    (lambda e, sid=next_incomplete["id"]: self._run_sheriff_wizard_action(sid))
                                    if next_incomplete
                                    else None
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor=LightTheme.ACCENT_SUCCESS if next_incomplete is None else LightTheme.ACCENT_PRIMARY,
                                    color="white",
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                            ft.OutlinedButton(
                                "Open Sheriff Panel",
                                icon=ft.Icons.SHIELD_ROUNDED,
                                on_click=lambda e: self.show_settings_hub(active_tab="sheriff"),
                                style=ft.ButtonStyle(
                                    color=LightTheme.TEXT_PRIMARY,
                                    side=ft.BorderSide(1, LightTheme.BORDER_COLOR),
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                            ft.ProgressRing(width=14, height=14, stroke_width=2, color=LightTheme.ACCENT_PRIMARY) if self._sheriff_workflow_in_progress else ft.Container(),
                        ],
                        spacing=10,
                    ),
                    ft.Text(f"Workflow error: {self._sheriff_workflow_error}", size=12, color=LightTheme.ACCENT_ERROR)
                    if self._sheriff_workflow_error
                    else ft.Container(),
                ],
                spacing=0,
            ),
            padding=18,
            border_radius=12,
            bgcolor=LightTheme.BG_ELEVATED,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

    def _set_inference_mode(self, mode: str):
        """Set inference mode (cloud or local)."""
        if mode not in ["cloud", "local"]:
            return

        # Cloud mode is intentionally disabled in current deployment.
        if mode == "cloud":
            self.inference_mode = "local"
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("Cloud inference is disabled. Using local inference only.", color="white"),
                bgcolor=LightTheme.ACCENT_WARNING,
                duration=2500,
            )
            self.page.snack_bar.open = True
            self.page.update()
            return

        old_mode = self.inference_mode
        self.inference_mode = "local"
        logger.info(f"Inference mode changed: {old_mode} -> local")

        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"💻 {self.tr('inference.local')}", color="white"),
            bgcolor=LightTheme.ACCENT_SUCCESS,
            duration=1500,
        )
        self.page.snack_bar.open = True

        # Refresh landing page to update state
        self.show_landing_page()
    
    def _show_adapter_selector(self, adapters: List[Dict]):
        """Show popup to select which adapter to query."""
        if not adapters:
            return
        
        def select_adapter(adapter_id, name):
            self.selected_adapter_id = adapter_id
            dialog.open = False
            self.page.update()
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📄 Now asking: {name}", color="white"),
                bgcolor=LightTheme.ACCENT_PRIMARY,
                duration=2000,
            )
            self.page.snack_bar.open = True
            self.show_landing_page()
        
        def select_all():
            self.selected_adapter_id = None
            dialog.open = False
            self.page.update()
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"📚 Now asking all {len(adapters)} documents", color="white"),
                bgcolor=LightTheme.ACCENT_PRIMARY,
                duration=2000,
            )
            self.page.snack_bar.open = True
            self.show_landing_page()
        
        # Build adapter list
        adapter_items = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SELECT_ALL_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                    ft.Text(f"All documents ({len(adapters)})", size=13, color=LightTheme.TEXT_PRIMARY, expand=True),
                    ft.Icon(ft.Icons.CHECK_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS) if self.selected_adapter_id is None else ft.Container(),
                ], spacing=12),
                padding=ft.padding.all(12),
                border_radius=8,
                on_click=lambda e: select_all(),
                on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                ink=True,
            ),
            ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
        ]
        
        for adapter in adapters:
            adapter_id = adapter.get("adapter_id")
            name = adapter.get("name", "Unknown")
            is_selected = self.selected_adapter_id == adapter_id
            
            adapter_items.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS),
                        ft.Text(name[:30] + ("..." if len(name) > 30 else ""), size=13, color=LightTheme.TEXT_PRIMARY, expand=True),
                        ft.Icon(ft.Icons.CHECK_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS) if is_selected else ft.Container(),
                    ], spacing=12),
                    padding=ft.padding.all(12),
                    border_radius=8,
                    on_click=lambda e, aid=adapter_id, n=name: select_adapter(aid, n),
                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                    ink=True,
                )
            )
        
        dialog = ft.AlertDialog(
            title=ft.Text("Select Document", size=16, weight=ft.FontWeight.W_600),
            content=ft.Container(
                content=ft.Column(adapter_items, spacing=4, scroll=ft.ScrollMode.AUTO),
                width=350,
                height=min(400, 80 + len(adapters) * 50),
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(dialog)),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _close_dialog(self, dialog):
        """Close a dialog."""
        dialog.open = False
        self.page.update()
    
    def _select_and_ask(self, adapter: Dict):
        """Select an adapter and focus the chat input."""
        self.selected_adapter_id = adapter.get("adapter_id")
        logger.info(f"Selected adapter for chat: {adapter.get('name')}")
        
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"📄 Ready to chat with: {adapter.get('name')}", color="white"),
            bgcolor=LightTheme.ACCENT_PRIMARY,
            duration=2000,
        )
        self.page.snack_bar.open = True
        
        # Refresh UI and focus chat input
        self.show_landing_page()
        
        # Focus the chat input after a brief delay
        if hasattr(self, 'chat_input'):
            self.chat_input.focus()
            self.page.update()
    
    def _get_loaded_adapter_display(self, adapters: list) -> str:
        """Get display text for the loaded adapter indicator."""
        if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter:
            # Find adapter name
            for a in adapters:
                if a.get("adapter_id") == self._loaded_local_adapter:
                    name = a.get("name", "Document")
                    # Truncate if too long
                    if len(name) > 20:
                        name = name[:17] + "..."
                    return f"🧠 {name}"
            return "🧠 Adapter Loaded"
        elif len(adapters) == 0:
            return "💬 Base AI"
        elif len(adapters) == 1:
            return f"📄 {adapters[0].get('name', 'Document')[:15]}..."
        else:
            return f"📚 {len(adapters)} documents"
    
    def _get_loaded_adapter_tooltip(self, adapters: list) -> str:
        """Get tooltip for the loaded adapter indicator."""
        if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter:
            for a in adapters:
                if a.get("adapter_id") == self._loaded_local_adapter:
                    return f"✓ '{a.get('name')}' loaded for local inference - AI knows this document!"
            return "Adapter loaded for local inference"
        elif len(adapters) == 0:
            return "Using base AI model (no documents trained). Upload a PDF to enhance AI knowledge!"
        elif len(adapters) == 1:
            return f"Click 'Load for Local Inference' from the ⋮ menu to chat about this document"
        else:
            return f"Click to select which document to ask about"
    
    def _select_adapter(self, adapter: Dict):
        """Select an adapter for subsequent queries."""
        self.selected_adapter_id = adapter.get("adapter_id")
        
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(f"✓ Selected: {adapter.get('name')}", color="white"),
            bgcolor=LightTheme.ACCENT_SUCCESS,
            duration=2000,
        )
        self.page.snack_bar.open = True
        self.show_landing_page()
    
    def _retrain_document(self, adapter: Dict):
        """Offer to retrain a document."""
        doc_name = adapter.get("name", "Unknown")
        
        def confirm_retrain(e):
            dialog.open = False
            self.page.update()
            
            # Find the entry and trigger retraining
            try:
                query_filter = QueryFilter()
                all_entries = self.vault.kv_store.search(query_filter)
                
                for entry in all_entries:
                    if entry.service == doc_name:
                        # Convert entry to dict format expected by _offer_training_from_entry
                        entry_dict = {
                            "service": entry.service,
                            "tags": entry.tags or [],
                            "description": entry.description,
                        }
                        self._offer_training_from_entry(entry_dict)
                        return
                
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Could not find document: {doc_name}", color="white"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                
            except Exception as ex:
                logger.error(f"Error retraining document: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Error: {str(ex)}", color="white"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text("Retrain Document?", size=16, weight=ft.FontWeight.W_600),
            content=ft.Text(
                f"This will regenerate Q&A pairs and retrain the adapter for '{doc_name}'.\n\n"
                "This may improve response quality but takes a few minutes.",
                size=14,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(dialog)),
                ft.ElevatedButton(
                    "Retrain",
                    icon=ft.Icons.REFRESH_ROUNDED,
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    on_click=confirm_retrain,
                ),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _show_document_details(self, adapter: Dict):
        """Show detailed status of a document/adapter."""
        doc_name = adapter.get("name", "Unknown")
        adapter_id = adapter.get("adapter_id", "N/A")
        encryption_key = adapter.get("encryption_key", "")
        
        # Check if adapter is loaded locally
        local_status = "Not loaded"
        local_color = LightTheme.TEXT_MUTED
        if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter == adapter_id:
            local_status = "✓ Loaded & Ready"
            local_color = LightTheme.ACCENT_SUCCESS
        
        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, color=LightTheme.ACCENT_SUCCESS, size=24),
                ft.Text("Document Details", size=18, weight=ft.FontWeight.W_600),
            ], spacing=12),
            content=ft.Container(
                content=ft.Column([
                    # Document name
                    ft.Row([
                        ft.Text("Document:", size=12, color=LightTheme.TEXT_MUTED, width=100),
                        ft.Text(doc_name, size=12, weight=ft.FontWeight.W_500),
                    ]),
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    
                    # Training status
                    ft.Row([
                        ft.Text("Training:", size=12, color=LightTheme.TEXT_MUTED, width=100),
                        ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS),
                            ft.Text("Completed", size=12, color=LightTheme.ACCENT_SUCCESS),
                        ], spacing=4),
                    ]),
                    
                    # Adapter ID
                    ft.Row([
                        ft.Text("Adapter ID:", size=12, color=LightTheme.TEXT_MUTED, width=100),
                        ft.Text(adapter_id[:20] + "..." if len(adapter_id) > 20 else adapter_id, size=11, color=LightTheme.TEXT_SECONDARY),
                    ]),
                    
                    # Local inference status
                    ft.Row([
                        ft.Text("Local Mode:", size=12, color=LightTheme.TEXT_MUTED, width=100),
                        ft.Text(local_status, size=12, color=local_color),
                    ]),
                    
                    ft.Container(height=16),
                    
                    # Actions
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Actions:", size=12, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500),
                            ft.Container(height=8),
                            ft.Row([
                                ft.ElevatedButton(
                                    "Chat Now",
                                    icon=ft.Icons.CHAT_ROUNDED,
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    color="white",
                                    on_click=lambda e: self._close_and_chat(dialog, adapter),
                                ),
                                ft.OutlinedButton(
                                    "Load Locally",
                                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                                    on_click=lambda e: self._close_and_load_locally(dialog, adapter),
                                ),
                            ], spacing=12),
                        ]),
                        padding=12,
                        bgcolor=LightTheme.BG_HOVER,
                        border_radius=8,
                    ),
                ], spacing=8),
                width=400,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Close", on_click=lambda e: self._close_dialog(dialog)),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _close_and_chat(self, dialog, adapter: Dict):
        """Close dialog and start chatting."""
        dialog.open = False
        self.page.update()
        self._select_and_ask(adapter)
    
    def _close_and_load_locally(self, dialog, adapter: Dict):
        """Close dialog and load adapter locally."""
        dialog.open = False
        self.page.update()
        self._load_adapter_locally(adapter)
    
    def _load_adapter_locally(self, adapter: Dict):
        """Load an adapter for local inference - downloads and applies adapter weights."""
        doc_name = adapter.get("name", "Unknown")
        adapter_id = adapter.get("adapter_id")
        encryption_key_hex = adapter.get("encryption_key")
        
        if not adapter_id:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("❌ No adapter ID found", color="white"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        if not encryption_key_hex:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("❌ No encryption key found - cannot decrypt adapter", color="white"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        # Show loading indicator
        self.page.snack_bar = ft.SnackBar(
            content=ft.Row([
                ft.ProgressRing(width=16, height=16, stroke_width=2, color="white"),
                ft.Text(f"Loading adapter for '{doc_name}'...", color="white"),
            ], spacing=12),
            bgcolor=LightTheme.ACCENT_PRIMARY,
            duration=30000,  # Longer timeout for download
        )
        self.page.snack_bar.open = True
        self.page.update()
        
        def load_in_background():
            try:
                from local_inference import get_local_engine
                engine = get_local_engine()
                
                # Step 1: Load base model if needed
                logger.info(f"Step 1: Loading base model...")
                if not engine.model:
                    engine.load_model(progress_callback=lambda msg: logger.info(f"Model: {msg}"))
                
                # Step 2: Download encrypted adapter from backend
                logger.info(f"Step 2: Downloading adapter {adapter_id}...")
                adapter_path = self._download_adapter_for_local(adapter_id)
                
                if not adapter_path:
                    raise RuntimeError("⏳ Adapter not ready yet - training is still in progress on the cloud. Check back in 2-5 minutes.")
                
                logger.info(f"Step 3: Decrypting adapter...")
                # Step 3: Decrypt the adapter
                adapter_weights = engine.decrypt_adapter(adapter_path, encryption_key_hex)
                
                # Step 4: Apply adapter weights to the model
                logger.info(f"Step 4: Applying adapter weights...")
                engine.apply_adapter_weights(adapter_weights)
                
                # Mark this adapter as loaded
                self._loaded_local_adapter = adapter_id
                self.selected_adapter_id = adapter_id
                
                # Switch to local mode
                self.inference_mode = "local"
                
                logger.info(f"✓ Adapter {adapter_id} loaded successfully!")
                
                # Update UI
                def show_success():
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="white", size=20),
                            ft.Text(f"✓ Ready! '{doc_name}' loaded - AI now knows this document!", color="white"),
                        ], spacing=12),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                        duration=4000,
                    )
                    self.page.snack_bar.open = True
                    self.show_landing_page()
                
                show_success()
                
            except Exception as ex:
                logger.error(f"Error loading adapter locally: {ex}")
                error_str = str(ex)
                
                # Check if it's a "training in progress" error
                if "not ready" in error_str.lower() or "still in progress" in error_str.lower():
                    def show_training_in_progress():
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Row([
                                ft.Icon(ft.Icons.HOURGLASS_EMPTY_ROUNDED, color="white", size=20),
                                ft.Column([
                                    ft.Text("Training still in progress", color="white", weight=ft.FontWeight.W_600),
                                    ft.Text("Check back in 2-5 minutes", color="white", size=12),
                                ], spacing=2, tight=True),
                            ], spacing=12),
                            bgcolor=LightTheme.ACCENT_WARNING,
                            duration=5000,
                            action="Check Status",
                            action_color="white",
                            on_action=lambda e: self._check_training_status(doc_name),
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                    show_training_in_progress()
                else:
                    def show_error():
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"❌ Error: {error_str}", color="white"),
                            bgcolor=LightTheme.ACCENT_ERROR,
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                    show_error()
        
        # Run in background
        import threading
        threading.Thread(target=load_in_background, daemon=True).start()
    
    def _delete_document(self, adapter: Dict):
        """Delete a document and its adapter."""
        doc_name = adapter.get("name", "Unknown")
        adapter_id = adapter.get("adapter_id")
        
        def confirm_delete(e):
            dialog.open = False
            self.page.update()
            
            try:
                # Delete from vault
                query_filter = QueryFilter()
                all_entries = self.vault.kv_store.search(query_filter)
                
                for entry in all_entries:
                    if entry.service == doc_name:
                        self.vault.kv_store.delete(entry.id)
                        logger.info(f"Deleted document: {doc_name}")
                        break
                
                # Clear selection if this was selected
                if self.selected_adapter_id == adapter_id:
                    self.selected_adapter_id = None
                
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"🗑️ Deleted: {doc_name}", color="white"),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                    duration=2000,
                )
                self.page.snack_bar.open = True
                
                # Refresh UI
                self.show_landing_page()
                
            except Exception as ex:
                logger.error(f"Error deleting document: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Error: {str(ex)}", color="white"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Text("Delete Document?", size=16, weight=ft.FontWeight.W_600),
            content=ft.Text(
                f"This will permanently delete '{doc_name}' and its trained adapter.\n\n"
                "This action cannot be undone.",
                size=14,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self._close_dialog(dialog)),
                ft.ElevatedButton(
                    "Delete",
                    icon=ft.Icons.DELETE_ROUNDED,
                    bgcolor=LightTheme.ACCENT_ERROR,
                    color="white",
                    on_click=confirm_delete,
                ),
            ],
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _check_training_status(self, doc_name: str):
        """Check and refresh training status for a document."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Row([
                ft.ProgressRing(width=16, height=16, stroke_width=2, color="white"),
                ft.Text("Checking training status...", color="white"),
            ], spacing=12),
            bgcolor=LightTheme.ACCENT_PRIMARY,
        )
        self.page.snack_bar.open = True
        self.page.update()
        
        def check_in_background():
            try:
                # First, get the adapter ID from vault entry tags
                adapter_id_from_vault = None
                try:
                    query_filter = QueryFilter()
                    all_entries = self.vault.kv_store.search(query_filter)
                    for entry in all_entries:
                        if entry.service == doc_name and entry.tags:
                            for tag in entry.tags:
                                if tag.startswith("training_job:"):
                                    adapter_id_from_vault = tag.split(":", 1)[1]
                                    logger.info(f"Found adapter ID in vault for {doc_name}: {adapter_id_from_vault}")
                                    break
                            if adapter_id_from_vault:
                                break
                except Exception as vault_err:
                    logger.warning(f"Could not get adapter ID from vault: {vault_err}")
                
                # If we have a specific adapter ID, check its status directly
                if adapter_id_from_vault and self.training_manager:
                    try:
                        status_result = self.training_manager.get_job_status(adapter_id_from_vault)
                        status = status_result.get("status", "unknown").lower()
                        logger.info(f"Direct adapter status for {adapter_id_from_vault}: {status}")
                        
                        if status == "completed":
                            # Training completed! Update the vault entry
                            self._update_document_status(doc_name, "completed", adapter_id_from_vault)
                            
                            # Show success and refresh UI
                            self.page.snack_bar = ft.SnackBar(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="white", size=20),
                                    ft.Text(f"🎉 '{doc_name}' training completed! Ready to chat.", color="white"),
                                ], spacing=12),
                                bgcolor=LightTheme.ACCENT_SUCCESS,
                                duration=5000,
                            )
                            self.page.snack_bar.open = True
                            self.page.update()
                            self.show_landing_page()  # Refresh to show updated status
                            return
                        elif status == "failed":
                            self._update_document_status(doc_name, "failed", adapter_id_from_vault)
                            self.page.snack_bar = ft.SnackBar(
                                content=ft.Text(f"❌ Training failed for '{doc_name}'", color="white"),
                                bgcolor=LightTheme.ACCENT_ERROR,
                            )
                            self.page.snack_bar.open = True
                            self.page.update()
                            self.show_landing_page()  # Refresh to show updated status
                            return
                        elif status in ["pending", "training", "in_progress", "in_queue"]:
                            # Still training
                            self.page.snack_bar = ft.SnackBar(
                                content=ft.Text(f"⏳ '{doc_name}' is still training. Check back in a few minutes.", color="white"),
                                bgcolor=LightTheme.ACCENT_WARNING,
                                duration=4000,
                            )
                            self.page.snack_bar.open = True
                            self.page.update()
                            return
                        
                    except Exception as status_err:
                        error_str = str(status_err)
                        logger.warning(f"Could not check adapter status directly: {status_err}")
                        
                        # Check for auth errors
                        if "401" in error_str or "expired" in error_str.lower():
                            def prompt_relogin():
                                self._prompt_relogin("Your session has expired while checking training status.")
                            prompt_relogin()
                            return
                
                # Fallback: Try fetching from the general adapters API
                if self.training_manager:
                    jobs = []
                    try:
                        import requests
                        response = requests.get(
                            f"{self.backend_url}/api/adapters/adapters",
                            headers={"Authorization": f"Bearer {self.session_data.get('access_token', '')}"},
                            timeout=10
                        )
                        if response.status_code == 200:
                            data = response.json()
                            # Handle both list and dict responses
                            if isinstance(data, list):
                                jobs = data
                            elif isinstance(data, dict):
                                jobs = data.get("adapters", data.get("jobs", [data]))
                            logger.info(f"Fetched {len(jobs)} training jobs from adapters API")
                        elif response.status_code == 401:
                            # Session expired - prompt re-login
                            logger.warning("Session expired (401), prompting re-login")
                            def prompt_relogin():
                                self._prompt_relogin("Your session has expired while checking training status.")
                            prompt_relogin()
                            return
                    except Exception as req_err:
                        logger.warning(f"Could not fetch training jobs: {req_err}")
                    
                    # Find this document's job
                    doc_job = None
                    for job in jobs:
                        if not isinstance(job, dict):
                            continue
                        job_name = str(job.get("model_name", "") or job.get("name", ""))
                        job_id = str(job.get("adapter_id", "") or job.get("id", ""))
                        if doc_name in job_name or doc_name in job_id or (adapter_id_from_vault and adapter_id_from_vault in job_id):
                            doc_job = job
                            break
                    
                    if doc_job:
                        status = doc_job.get("status", "unknown").lower()
                        if status == "completed":
                            # Training completed! Update the vault entry
                            self._update_document_status(doc_name, "completed", doc_job.get("adapter_id"))
                            
                            self.page.snack_bar = ft.SnackBar(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="white", size=20),
                                    ft.Text(f"🎉 '{doc_name}' training completed! Ready to chat.", color="white"),
                                ], spacing=12),
                                bgcolor=LightTheme.ACCENT_SUCCESS,
                                duration=5000,
                            )
                            self.page.snack_bar.open = True
                            self.page.update()
                            self.show_landing_page()  # Refresh to show updated status
                            return
                        elif status == "failed":
                            self.page.snack_bar = ft.SnackBar(
                                content=ft.Text(f"❌ Training failed for '{doc_name}'", color="white"),
                                bgcolor=LightTheme.ACCENT_ERROR,
                            )
                            self.page.snack_bar.open = True
                            self.page.update()
                            return
                
                # Still pending/training or status unknown
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"⏳ '{doc_name}' is still training. Check back in a few minutes.", color="white"),
                    bgcolor=LightTheme.ACCENT_WARNING,
                    duration=4000,
                )
                self.page.snack_bar.open = True
                self.page.update()
                
            except Exception as ex:
                logger.error(f"Error checking training status: {ex}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ Error checking status: {str(ex)}", color="white"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
        
        import threading
        threading.Thread(target=check_in_background, daemon=True).start()
    
    def _update_document_status(self, doc_name: str, status: str, adapter_id: str = None):
        """Update a document's training status in the vault (updates ALL matching entries)."""
        try:
            import sqlite3
            import json
            
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            
            updated_count = 0
            for entry in all_entries:
                if entry.service == doc_name:
                    # Update tags
                    new_tags = [t for t in (entry.tags or []) if not t.startswith("training_status:")]
                    new_tags.append(f"training_status:{status}")
                    if adapter_id:
                        new_tags = [t for t in new_tags if not t.startswith("training_job:")]
                        new_tags.append(f"training_job:{adapter_id}")
                    
                    # Preserve other important tags
                    for tag in (entry.tags or []):
                        if tag.startswith("training_key:") and tag not in new_tags:
                            new_tags.append(tag)
                        elif tag.startswith("data_type:") and tag not in new_tags:
                            new_tags.append(tag)
                        elif tag.startswith("source:") and tag not in new_tags:
                            new_tags.append(tag)
                    
                    # Update tags directly in the database (without re-encrypting)
                    # Use comma-separated format to match to_dict() format
                    db_path = self.vault.kv_store.db_path
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("""
                            UPDATE encrypted_entries
                            SET tags = ?, updated_at = datetime('now')
                            WHERE id = ?
                        """, (",".join(new_tags), entry.id))
                        conn.commit()
                    
                    updated_count += 1
                    logger.info(f"Updated entry {entry.id} for {doc_name} to status: {status}")
            
            if updated_count > 0:
                logger.info(f"Updated {updated_count} entries for {doc_name} to status: {status}")
            else:
                logger.warning(f"No entries found to update for {doc_name}")
                
        except Exception as e:
            logger.error(f"Error updating document status: {e}", exc_info=True)
    
    def _on_queued_doc_click(self, doc_name: str):
        """Handle click on a queued/training document."""
        logger.info(f"Queued document clicked: {doc_name}")
        
        # Show a helpful dialog explaining the status and options
        def check_status(e):
            dialog.open = False
            self.page.update()
            # Refresh and check if training completed
            self._check_training_status(doc_name)
        
        def chat_without_adapter(e):
            dialog.open = False
            self.page.update()
            # Set chat input with a question about the doc
            if hasattr(self, 'chat_input') and self.chat_input:
                self.chat_input.value = f"Tell me about {doc_name}"
                self.chat_input.focus()
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text("💡 Tip: Switch to Local mode to chat while training completes!", color="white"),
                bgcolor=LightTheme.ACCENT_PRIMARY,
                duration=4000,
            )
            self.page.snack_bar.open = True
            self.page.update()
        
        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.HOURGLASS_EMPTY_ROUNDED, color=LightTheme.ACCENT_WARNING, size=24),
                ft.Text("Training in Progress", size=18, weight=ft.FontWeight.W_600),
            ], spacing=12),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"'{doc_name}' is being trained on the secure cloud.",
                        size=14,
                    ),
                    ft.Container(height=12),
                    ft.Text(
                        "This typically takes 2-5 minutes. Once complete, you'll see a ✓ next to the document.",
                        size=13,
                        color=LightTheme.TEXT_MUTED,
                    ),
                    ft.Container(height=16),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("While you wait, you can:", size=12, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500),
                            ft.Container(height=8),
                            ft.Row([
                                ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                                ft.Text("Chat with the base AI (switch to Local mode)", size=12),
                            ], spacing=8),
                            ft.Row([
                                ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                                ft.Text("Upload more documents", size=12),
                            ], spacing=8),
                            ft.Row([
                                ft.Icon(ft.Icons.VISIBILITY_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                                ft.Text("Check training progress", size=12),
                            ], spacing=8),
                        ], spacing=4),
                        padding=12,
                        bgcolor=LightTheme.BG_HOVER,
                        border_radius=8,
                    ),
                ], spacing=0),
                width=350,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Check Status", icon=ft.Icons.VISIBILITY_ROUNDED, on_click=check_status),
                ft.ElevatedButton(
                    "Chat Now (Base AI)",
                    icon=ft.Icons.CHAT_ROUNDED,
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    on_click=chat_without_adapter,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
    def _configure_mcp_target(self, target: str, label: str) -> None:
        """Configure MCP target (claude/cursor/chatgpt) with feedback."""
        try:
            if not hasattr(self, "mcp_setup") or not self.mcp_setup:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("❌ MCP setup not available"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return

            self.page.snack_bar = ft.SnackBar(
                content=ft.Row(
                    [
                        ft.ProgressRing(width=16, height=16, stroke_width=2, color="white"),
                        ft.Text(f"Configuring {label}...", color="white"),
                    ],
                    spacing=12,
                ),
                bgcolor=LightTheme.ACCENT_PRIMARY,
            )
            self.page.snack_bar.open = True
            self.page.update()

            result = self.mcp_setup.auto_configure(target=target)
            if result.get("success"):
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"✅ {label} ready. Restart {label}."),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                    duration=5000,
                )
            else:
                error = result.get("error", "Unknown error")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ {label}: {error}"),
                    bgcolor=LightTheme.ACCENT_ERROR if target != "chatgpt" else LightTheme.ACCENT_WARNING,
                    duration=6000,
                )

            self.page.snack_bar.open = True
            self.page.update()

            if self.current_view == "landing":
                self.show_landing_page()
            elif self.current_view == "agent":
                self.show_agent_view(active_tab="connections")
            elif self.current_view == "settings_hub":
                self.show_settings_hub(active_tab="sheriff")
        except Exception as e:
            logger.error(f"Error configuring {label} MCP: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Error: {str(e)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def _configure_claude_mcp(self):
        """Configure Claude Desktop MCP integration with one click."""
        self._configure_mcp_target("claude", "Claude Desktop")
    
    def show_landing_page(self):
        """Show the simplified default workspace."""
        self._show_workspace_view()
        return

        self.current_view = "landing"
        self._ensure_chat_messages_loaded()

        self.page.clean()

        items_to_remove = [
            item
            for item in self.page.overlay
            if isinstance(item, ft.Container)
            and hasattr(item, "content")
            and isinstance(getattr(item, "content", None), ft.FloatingActionButton)
        ]
        for item in items_to_remove:
            self.page.overlay.remove(item)

        if not hasattr(self, "pdf_file_picker") or self.pdf_file_picker is None:
            self.pdf_file_picker = ft.FilePicker(on_result=self.on_pdf_selected)
        if self.pdf_file_picker not in self.page.overlay:
            self.page.overlay.append(self.pdf_file_picker)
        self._ensure_private_model_pickers()
        self.page.update()

        profile = self._ensure_private_model_profile()
        profiles = self._get_private_model_profiles()
        profile_status = self._get_private_model_status()
        documents = self._get_private_model_documents(limit=6)
        model_display = (profile_status.get("model_name") or DEFAULT_PRIVATE_MODEL_NAME).split("/")[-1]
        local_mode_active = self.session_data is None and self.local_first_mode

        total_secured_items = profile_status.get("document_count", 0)
        recent_items = []
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            total_secured_items += len(all_entries)
            sorted_entries = sorted(
                all_entries,
                key=lambda entry: entry.created_at if entry.created_at else datetime.min,
                reverse=True,
            )
            for entry in sorted_entries[:8]:
                time_ago = ""
                if entry.created_at:
                    delta = datetime.now() - entry.created_at
                    if delta.days > 0:
                        time_ago = f"{delta.days}d ago"
                    elif delta.seconds >= 3600:
                        time_ago = f"{delta.seconds // 3600}h ago"
                    elif delta.seconds >= 60:
                        time_ago = f"{delta.seconds // 60}m ago"
                    else:
                        time_ago = "just now"

                recent_items.append(
                    {
                        "name": entry.service,
                        "type": entry.entry_type.value if hasattr(entry.entry_type, "value") else str(entry.entry_type),
                        "time_ago": time_ago,
                    }
                )
        except Exception as e:
            logger.warning(f"Error getting vault stats: {e}")

        def metric_chip(title: str, value: str, icon: str, color: str) -> ft.Container:
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=18, color=color),
                            padding=10,
                            border_radius=10,
                            bgcolor=color + "12",
                        ),
                        ft.Column(
                            [
                                ft.Text(value, size=16, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                                ft.Text(title, size=11, color=LightTheme.TEXT_MUTED),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                    ],
                    spacing=12,
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=12),
                bgcolor=LightTheme.BG_PRIMARY,
                border_radius=14,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )

        def document_card(doc: Dict[str, Any]) -> ft.Container:
            source_name = Path(doc.get("source_path") or doc.get("name", "")).parent.name or "Local import"
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                            padding=10,
                            border_radius=10,
                            bgcolor=LightTheme.ACCENT_PRIMARY + "12",
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    doc.get("name", "Untitled"),
                                    size=14,
                                    color=LightTheme.TEXT_PRIMARY,
                                    weight=ft.FontWeight.W_600,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    f"{doc.get('chunk_count', 0)} chunks • {source_name}",
                                    size=11,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.LOCK_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS),
                    ],
                    spacing=12,
                ),
                padding=12,
                bgcolor=LightTheme.BG_PRIMARY,
                border_radius=12,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )

        def adapter_card(adapter) -> ft.Container:
            weight = f"{int(adapter.weight * 100)}%"
            description = adapter.description or "Private WDVA layer"
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=18, color=LightTheme.ACCENT_WARNING),
                            padding=10,
                            border_radius=10,
                            bgcolor=LightTheme.ACCENT_WARNING + "12",
                        ),
                        ft.Column(
                            [
                                ft.Text(adapter.name, size=14, color=LightTheme.TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ft.Text(description, size=11, color=LightTheme.TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Container(
                            content=ft.Text(weight, size=11, color=LightTheme.ACCENT_WARNING),
                            padding=ft.padding.symmetric(horizontal=10, vertical=6),
                            bgcolor=LightTheme.ACCENT_WARNING + "10",
                            border_radius=999,
                        ),
                    ],
                    spacing=12,
                ),
                padding=12,
                bgcolor=LightTheme.BG_PRIMARY,
                border_radius=12,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )

        overview_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Active Profile", size=13, color=LightTheme.TEXT_MUTED),
                    ft.Container(height=8),
                    ft.Dropdown(
                        value=profile.name,
                        options=[ft.dropdown.Option(item.name, item.name) for item in profiles],
                        border_radius=12,
                        filled=True,
                        bgcolor=LightTheme.BG_PRIMARY,
                        on_change=lambda e: self._set_active_private_profile(e.control.value),
                    ),
                    ft.Container(height=16),
                    ft.Text(profile.description or "A local private workspace for files, notes, and WDVA layers.", size=13, color=LightTheme.TEXT_SECONDARY),
                    ft.Container(height=16),
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    ft.Container(height=12),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                            ft.Text(f"Base model: {model_display}", size=12, color=LightTheme.TEXT_PRIMARY),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS),
                            ft.Text(f"{profile_status.get('document_count', 0)} indexed documents", size=12, color=LightTheme.TEXT_PRIMARY),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=16, color=LightTheme.ACCENT_WARNING),
                            ft.Text(f"{profile_status.get('adapter_count', 0)} WDVA layers attached", size=12, color=LightTheme.TEXT_PRIMARY),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.GPP_GOOD_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS),
                            ft.Text("Sheriff lease and audit controls available", size=12, color=LightTheme.TEXT_PRIMARY),
                        ],
                        spacing=8,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "Open Chat",
                                icon=ft.Icons.CHAT_ROUNDED,
                                on_click=lambda e: self._open_test_agent_chat(),
                                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                            ),
                            ft.TextButton(
                                "Create Profile",
                                icon=ft.Icons.ADD_ROUNDED,
                                on_click=self._open_create_profile_dialog,
                                style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=0,
            ),
            width=360,
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=18,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

        hero_panel = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            content=ft.Text("PRIVATE LANGUAGE MODEL", size=11, color=LightTheme.ACCENT_PRIMARY, weight=ft.FontWeight.BOLD),
                                            padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                            bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                                            border_radius=999,
                                        ),
                                        ft.Container(
                                            content=ft.Text("LOCAL FIRST", size=11, color=LightTheme.ACCENT_SUCCESS, weight=ft.FontWeight.BOLD),
                                            padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                            bgcolor=LightTheme.ACCENT_SUCCESS + "10",
                                            border_radius=999,
                                        ) if local_mode_active else ft.Container(),
                                    ],
                                    spacing=10,
                                    wrap=True,
                                ),
                                ft.Container(height=18),
                                ft.Text(
                                    "Chat with private files like it is already category-defining.",
                                    size=34,
                                    weight=ft.FontWeight.BOLD,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Container(height=12),
                                ft.Text(
                                    "Enclave turns local files into a controlled Private Language Model: encrypted context, WDVA-ready adaptation, and Data Sheriff guardrails on the same Mac.",
                                    size=15,
                                    color=LightTheme.TEXT_SECONDARY,
                                ),
                                ft.Container(height=22),
                                ft.Row(
                                    [
                                        ft.ElevatedButton(
                                            "Add Files",
                                            icon=ft.Icons.FILE_UPLOAD_ROUNDED,
                                            on_click=self._open_private_files_picker,
                                            style=ft.ButtonStyle(
                                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                                color="white",
                                                padding=ft.padding.symmetric(horizontal=24, vertical=16),
                                                shape=ft.RoundedRectangleBorder(radius=12),
                                            ),
                                        ),
                                        ft.OutlinedButton(
                                            "Add Folder",
                                            icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED,
                                            on_click=self._open_private_folder_picker,
                                            style=ft.ButtonStyle(
                                                color=LightTheme.TEXT_PRIMARY,
                                                padding=ft.padding.symmetric(horizontal=22, vertical=16),
                                                side=ft.BorderSide(1, LightTheme.BORDER_COLOR),
                                                shape=ft.RoundedRectangleBorder(radius=12),
                                            ),
                                        ),
                                        ft.TextButton(
                                            "Open Secure Chat",
                                            icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                                            on_click=lambda e: self._open_test_agent_chat(),
                                            style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                                        ),
                                    ],
                                    spacing=12,
                                    wrap=True,
                                ),
                                ft.Container(height=18),
                                ft.Text(self._private_model_note, size=12, color=LightTheme.TEXT_MUTED),
                                ft.Container(height=22),
                                ft.Row(
                                    [
                                        metric_chip(
                                            "Secure context",
                                            str(profile_status.get("document_count", 0)),
                                            ft.Icons.FOLDER_ROUNDED,
                                            LightTheme.ACCENT_PRIMARY,
                                        ),
                                        metric_chip(
                                            "Encrypted chunks",
                                            str(profile_status.get("chunk_count", 0)),
                                            ft.Icons.DATA_OBJECT_ROUNDED,
                                            LightTheme.ACCENT_SUCCESS,
                                        ),
                                        metric_chip(
                                            "WDVA layers",
                                            str(profile_status.get("adapter_count", 0)),
                                            ft.Icons.AUTO_AWESOME_ROUNDED,
                                            LightTheme.ACCENT_WARNING,
                                        ),
                                    ],
                                    spacing=12,
                                    wrap=True,
                                ),
                            ],
                            spacing=0,
                        ),
                        expand=True,
                    ),
                    overview_card,
                ],
                spacing=24,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=32,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=24,
            border=ft.border.all(1, LightTheme.ACCENT_PRIMARY + "20"),
        )

        privacy_banner = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.VERIFIED_USER_ROUNDED, size=26, color=LightTheme.ACCENT_SUCCESS),
                        padding=12,
                        border_radius=12,
                        bgcolor=LightTheme.ACCENT_SUCCESS + "12",
                    ),
                    ft.Column(
                        [
                            ft.Text(f"{total_secured_items} items secured across vault and private context", size=18, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(
                                "ChaCha20-Poly1305 at rest, keys kept locally, and local MLX inference by default.",
                                size=13,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row([ft.Icon(ft.Icons.LOCK_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Device-local keys", size=11, color=LightTheme.ACCENT_SUCCESS)], spacing=6),
                                ft.Row([ft.Icon(ft.Icons.GPP_GOOD_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Sheriff audit trail", size=11, color=LightTheme.ACCENT_SUCCESS)], spacing=6),
                                ft.Row([ft.Icon(ft.Icons.CLOUD_OFF_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Cloud optional, not required", size=11, color=LightTheme.ACCENT_SUCCESS)], spacing=6),
                            ],
                            spacing=6,
                        ),
                        padding=ft.padding.only(left=12),
                    ),
                ],
                spacing=16,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=20,
            bgcolor=LightTheme.ACCENT_SUCCESS + "08",
            border_radius=16,
            border=ft.border.all(1, LightTheme.ACCENT_SUCCESS + "25"),
        )

        documents_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Private Context Library", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Container(expand=True),
                            ft.TextButton("View all", on_click=lambda e: self.show_my_data_view(active_tab="knowledge"), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                        ]
                    ),
                    ft.Container(height=12),
                    ft.Column(
                        [document_card(doc) for doc in documents] if documents else [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=34, color=LightTheme.TEXT_MUTED),
                                        ft.Text("No private files indexed yet", size=14, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text("Bring in documents, code, notes, or PDFs and start chatting locally.", size=12, color=LightTheme.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                padding=28,
                            )
                        ],
                        spacing=10,
                    ),
                ],
                spacing=0,
            ),
            expand=True,
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=18,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

        wdva_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("WDVA Layers", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Container(expand=True),
                            ft.TextButton("Profiles", on_click=lambda e: self.show_my_data_view(active_tab="library"), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                        ]
                    ),
                    ft.Container(height=12),
                    ft.Column(
                        [adapter_card(adapter) for adapter in profile.wdva_adapters[:4]] if profile.wdva_adapters else [
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=34, color=LightTheme.TEXT_MUTED),
                                        ft.Text("No WDVA layers attached yet", size=14, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text(
                                            "This profile is ready for adaptive layers when you want domain-specific behavior without moving data off-device.",
                                            size=12,
                                            color=LightTheme.TEXT_MUTED,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                padding=28,
                            )
                        ],
                        spacing=10,
                    ),
                ],
                spacing=0,
            ),
            expand=True,
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=18,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

        recent_items_list = []
        if recent_items:
            for item in recent_items:
                recent_items_list.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.LOCK_ROUNDED, size=18, color=LightTheme.ACCENT_SUCCESS),
                                ft.Text(item["name"][:30] + ("..." if len(item["name"]) > 30 else ""), size=14, color=LightTheme.TEXT_PRIMARY, expand=True),
                                ft.Container(
                                    content=ft.Text(item["type"], size=11, color=LightTheme.ACCENT_PRIMARY),
                                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                    bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                                    border_radius=999,
                                ),
                                ft.Text(item["time_ago"], size=11, color=LightTheme.TEXT_MUTED),
                            ],
                            spacing=12,
                        ),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=12,
                        bgcolor=LightTheme.BG_PRIMARY,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        else:
            recent_items_list.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.INBOX_ROUNDED, size=32, color=LightTheme.TEXT_MUTED),
                            ft.Text("No encrypted vault items yet", size=14, color=LightTheme.TEXT_PRIMARY),
                            ft.Text("Secrets, credentials, and synced artifacts will appear here.", size=12, color=LightTheme.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    padding=32,
                    alignment=ft.alignment.center,
                )
            )

        recent_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Encrypted Vault Activity", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Container(expand=True),
                            ft.TextButton("My Data", on_click=lambda e: self.on_nav_change(0), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                        ]
                    ),
                    ft.Container(height=12),
                    ft.Column(recent_items_list, spacing=10),
                ],
                spacing=0,
            ),
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=18,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )

        sheriff_wizard = self._build_sheriff_quickstart_wizard()

        main_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=28),
                    ft.Container(content=hero_panel, padding=ft.padding.symmetric(horizontal=48)),
                    ft.Container(height=20),
                    ft.Container(content=privacy_banner, padding=ft.padding.symmetric(horizontal=48)),
                    ft.Container(height=16),
                    ft.Container(content=sheriff_wizard, padding=ft.padding.symmetric(horizontal=48)),
                    ft.Container(height=16),
                    ft.Container(
                        content=ft.Row(
                            [documents_panel, wdva_panel],
                            spacing=16,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=ft.padding.symmetric(horizontal=48),
                    ),
                    ft.Container(height=16),
                    ft.Container(content=recent_section, padding=ft.padding.symmetric(horizontal=48)),
                    ft.Container(height=28),
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        # Initialize sidebar with new structure
        if not hasattr(self, 'sidebar') or self.sidebar is None:
            self.sidebar = ModernSidebar(
                on_nav_change=self.on_nav_change,
                selected_index=-1,
                translate=self.tr,
            )
        else:
            self.sidebar.selected_index = -1
            self.sidebar.translate = self.tr

        sidebar_container = self.sidebar.build()

        self.page.add(
            ft.Row(
                [sidebar_container, main_content],
                spacing=0,
                expand=True,
            )
        )
        self.page.update()

        # Start automatic status polling for pending/training documents
        self._start_landing_status_polling()

        return

        # === LEGACY CODE (unreachable, kept for reference during transition) ===
        doc_items = []
        for filename, status_info in self.processing_documents.items():
            if status_info.get("status") == "processing":
                doc_items.append(self._create_processing_card(filename, status_info))
        
        # Second: Ready documents (trained adapters) - with click to query
        for adapter in trained_adapters:
            # Capture adapter in closure
            adapter_copy = adapter.copy()
            is_selected = self.selected_adapter_id == adapter.get("adapter_id")
            
            doc_items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.DESCRIPTION_ROUNDED, 
                                size=14, 
                                color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.ACCENT_SUCCESS
                            ),
                            ft.Text(
                                adapter["name"][:22] + ("..." if len(adapter["name"]) > 22 else ""),
                                size=12,
                                color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_PRIMARY,
                                weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_400,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                expand=True,
                            ),
                            # Actions popup menu
                            ft.PopupMenuButton(
                                icon=ft.Icons.MORE_VERT_ROUNDED,
                                icon_size=14,
                                icon_color=LightTheme.TEXT_MUTED,
                                tooltip="Actions",
                                items=[
                                    ft.PopupMenuItem(
                                        text="Chat with this",
                                        icon=ft.Icons.CHAT_ROUNDED,
                                        on_click=lambda e, a=adapter_copy: self._select_and_ask(a),
                                    ),
                                    ft.PopupMenuItem(
                                        text="View Details",
                                        icon=ft.Icons.INFO_OUTLINE_ROUNDED,
                                        on_click=lambda e, a=adapter_copy: self._show_document_details(a),
                                    ),
                                    ft.PopupMenuItem(
                                        text="Load for Local Inference",
                                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                                        on_click=lambda e, a=adapter_copy: self._load_adapter_locally(a),
                                    ),
                                    ft.PopupMenuItem(),  # Divider
                                    ft.PopupMenuItem(
                                        text="Retrain",
                                        icon=ft.Icons.REFRESH_ROUNDED,
                                        on_click=lambda e, a=adapter_copy: self._retrain_document(a),
                                    ),
                                    ft.PopupMenuItem(
                                        text="Delete",
                                        icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                        on_click=lambda e, a=adapter_copy: self._delete_document(a),
                                    ),
                                ],
                            ),
                        ],
                        spacing=6,
                    ),
                    padding=ft.padding.only(left=12, top=6, bottom=6, right=4),
                    border_radius=8,
                    bgcolor=LightTheme.ACCENT_PRIMARY + "15" if is_selected else "transparent",
                    border=ft.border.all(1, LightTheme.ACCENT_PRIMARY) if is_selected else None,
                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" and not is_selected else (LightTheme.ACCENT_PRIMARY + "15" if is_selected else "transparent")),
                    on_click=lambda e, a=adapter_copy: self._select_and_ask(a),
                    ink=True,
                    tooltip=f"Click to chat with {adapter['name']}",
                )
            )
        
        # Third: Cloud training in progress (submitted to RunPod)
        # Track already-shown documents to avoid duplicates
        shown_documents = set(adapter["name"] for adapter in trained_adapters)
        
        for entry in all_entries:
            # Skip if already shown as a trained adapter
            if entry.service in shown_documents:
                continue
                
            if entry.tags:
                status = None
                for tag in entry.tags:
                    if tag.startswith("training_status:"):
                        status = tag.split(":", 1)[1]
                        break
                if status in ["pending", "training"]:
                    shown_documents.add(entry.service)  # Track to avoid duplicates
                    status_text = "⏳ Queued" if status == "pending" else "☁️ Training..."
                    entry_name = entry.service  # Capture for lambda
                    doc_items.append(
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.ProgressRing(width=14, height=14, stroke_width=2, color=LightTheme.ACCENT_WARNING) if status == "training" else ft.Icon(ft.Icons.HOURGLASS_EMPTY_ROUNDED, size=14, color=LightTheme.ACCENT_WARNING),
                                    ft.Text(
                                        entry.service[:20] + ("..." if len(entry.service) > 20 else ""),
                                        size=12,
                                        color=LightTheme.TEXT_MUTED,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                    ft.Text(status_text, size=9, color=LightTheme.TEXT_MUTED),
                                ],
                                spacing=8,
                            ),
                            padding=ft.padding.symmetric(horizontal=12, vertical=8),
                            border_radius=8,
                            tooltip=f"Click to view training status for {entry.service}",
                            on_click=lambda e, name=entry_name: self._on_queued_doc_click(name),
                            on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                            ink=True,
                        )
                    )
        
        left_sidebar = ft.Container(
                        content=ft.Column(
                            [
                    # Logo and title
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("🔐", size=24),
                                ft.Text("Enclave", size=18, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                            ],
                            spacing=8,
                        ),
                        padding=ft.padding.only(left=16, top=16, bottom=8),
                    ),
                    
                    # New Chat button
                    ft.Container(
                        content=ft.ElevatedButton(
                            "✨ New Chat",
                            icon=ft.Icons.ADD_ROUNDED,
                            on_click=lambda e: self._new_chat(),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            width=200,
                        ),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    ),
                    
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    
                    # Recents section
                    ft.Container(
                        content=ft.Text("Recents", size=11, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500),
                        padding=ft.padding.only(left=16, top=12, bottom=4),
                    ),
                    ft.Column(
                        chat_history_items if chat_history_items else [
                            ft.Container(
                                content=ft.Text("No recent chats", size=12, color=LightTheme.TEXT_MUTED, italic=True),
                                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                            )
                        ],
                        spacing=2,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    
                    # Documents section
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("📚 Documents", size=11, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500),
                                ft.Container(expand=True),
                                ft.IconButton(
                                    ft.Icons.ADD_ROUNDED,
                                    icon_size=16,
                                    icon_color=LightTheme.TEXT_MUTED,
                                    tooltip="Add PDF",
                                    on_click=lambda e: self._on_upload_click(e),
                                ),
                            ],
                        ),
                        padding=ft.padding.only(left=16, right=4, top=8, bottom=4),
                    ),
                    ft.Column(
                        doc_items if doc_items else [
                                ft.Container(
                                content=ft.Column([
                                    ft.Text("No documents yet", size=12, color=LightTheme.TEXT_MUTED, italic=True),
                                    ft.TextButton(
                                        "Upload PDF",
                                        icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                                        on_click=lambda e: self._on_upload_click(e),
                                        style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                                    ),
                                ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                            )
                        ],
                        spacing=2,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    
                    # Quick navigation
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.KEY_ROUNDED, size=14, color=LightTheme.TEXT_MUTED),
                                        ft.Text("Secrets", size=11, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=8),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    border_radius=6,
                                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                                    on_click=lambda e: self.build_ui(),
                                    ink=True,
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.FOLDER_ROUNDED, size=14, color=LightTheme.TEXT_MUTED),
                                        ft.Text("Library", size=11, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=8),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    border_radius=6,
                                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                                    on_click=lambda e: self.show_library_view(),
                                    ink=True,
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.HISTORY_ROUNDED, size=14, color=LightTheme.TEXT_MUTED),
                                        ft.Text("Activity Log", size=11, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=8),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    border_radius=6,
                                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                                    on_click=lambda e: self.show_activity_view(),
                                    ink=True,
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.SETTINGS_ROUNDED, size=14, color=LightTheme.TEXT_MUTED),
                                        ft.Text("Settings", size=11, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=8),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    border_radius=6,
                                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                                    on_click=lambda e: self.show_settings(),
                                    ink=True,
                                ),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.GPP_GOOD_ROUNDED, size=14, color=LightTheme.TEXT_MUTED),
                                        ft.Text("Data Sheriff", size=11, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=8),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    border_radius=6,
                                    on_hover=lambda e: setattr(e.control, 'bgcolor', LightTheme.BG_HOVER if e.data == "true" else "transparent"),
                                    on_click=lambda e: self.show_settings_hub(active_tab="sheriff"),
                                    ink=True,
                                ),
                            ],
                            spacing=2,
                        ),
                        padding=ft.padding.only(left=4, right=4, top=8, bottom=8),
                    ),
                    
                    ft.Divider(height=1, color=LightTheme.BORDER_COLOR),
                    
                    # MCP Integration status
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("AI Integrations", size=10, color=LightTheme.TEXT_MUTED, weight=ft.FontWeight.W_500),
                                ft.Container(height=6),
                                # Claude Desktop status
                                ft.Container(
                                    content=ft.Row([
                                        ft.Text("🤖", size=12),
                                        ft.Text("Claude", size=11, color=LightTheme.TEXT_SECONDARY, expand=True),
                                        ft.Icon(
                                            ft.Icons.CHECK_CIRCLE_ROUNDED if mcp_configured else ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                                            size=14,
                                            color=LightTheme.ACCENT_SUCCESS if mcp_configured else LightTheme.ACCENT_PRIMARY,
                                        ),
                                    ], spacing=6),
                                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                    border_radius=6,
                                    bgcolor=LightTheme.ACCENT_SUCCESS + "10" if mcp_configured else LightTheme.BG_HOVER,
                                    on_click=lambda e: self._configure_claude_mcp() if not mcp_configured else None,
                                    tooltip="✓ Claude Desktop configured" if mcp_configured else "Click to configure Claude Desktop",
                                ),
                                # ChatGPT status (future)
                                ft.Container(
                                    content=ft.Row([
                                        ft.Text("💬", size=12),
                                        ft.Text("ChatGPT", size=11, color=LightTheme.TEXT_MUTED, expand=True),
                                        ft.Text("Soon", size=9, color=LightTheme.TEXT_MUTED, italic=True),
                                    ], spacing=6),
                                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                    border_radius=6,
                                    bgcolor=LightTheme.BG_HOVER,
                                    tooltip="ChatGPT integration coming soon",
                                ),
                            ],
                            spacing=4,
                        ),
                        padding=ft.padding.only(left=12, right=12, top=8, bottom=8),
                    ),
                    
                    # Privacy status at bottom
                    ft.Container(
                                        content=ft.Column(
                                            [
                                ft.Row([
                                    ft.Icon(ft.Icons.VERIFIED_USER_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS),
                                    ft.Text("E2E Encrypted", size=10, color=LightTheme.ACCENT_SUCCESS),
                                ], spacing=6),
                                ft.Row([
                                    ft.Icon(ft.Icons.KEY_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS),
                                    ft.Text("Local Keys", size=10, color=LightTheme.ACCENT_SUCCESS),
                                ], spacing=6),
                                ft.Row([
                                    ft.Icon(
                                        ft.Icons.CLOUD_DONE_ROUNDED if backend_connected else ft.Icons.CLOUD_OFF_ROUNDED,
                                        size=14,
                                        color=LightTheme.ACCENT_SUCCESS if backend_connected else LightTheme.TEXT_MUTED,
                                                ),
                                                ft.Text(
                                        "Cloud Sync" if backend_connected else "Offline",
                                        size=10,
                                        color=LightTheme.ACCENT_SUCCESS if backend_connected else LightTheme.TEXT_MUTED,
                                    ),
                                ], spacing=6),
                                            ],
                                            spacing=4,
                                    ),
                                    padding=16,
                        bgcolor=LightTheme.ACCENT_SUCCESS + "08",
                        border=ft.border.only(top=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            width=240,
            bgcolor=LightTheme.BG_SECONDARY,
            border=ft.border.only(right=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )
        
        # ===== MAIN CHAT AREA =====
        
        # Chat messages container
        chat_messages_list = ft.ListView(
            spacing=16,
            padding=ft.padding.symmetric(horizontal=40, vertical=20),
            expand=True,
            auto_scroll=True,
        )
        
        # Populate with existing messages or welcome
        if self.chat_messages:
            for msg in self.chat_messages:
                chat_messages_list.controls.append(
                    self._create_chat_bubble(
                        msg["role"],
                        msg["content"],
                        msg.get("document"),
                        msg.get("sources"),
                    )
                )
        else:
            # Welcome message
            chat_messages_list.controls.append(
                                ft.Container(
                                        content=ft.Column(
                                            [
                                                ft.Text(
                                f"✨ {greeting}, {user_first_name}",
                                size=32,
                                                    weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                            ft.Container(height=8),
                                                ft.Text(
                                "Your private AI — only you can see this conversation",
                                size=14,
                                color=LightTheme.TEXT_MUTED,
                                                    text_align=ft.TextAlign.CENTER,
                                                ),
                            ft.Container(height=24),
                            # Quick action chips
                            ft.Row(
                                [
                                    self._create_action_chip("📝 Summarize", "Summarize the main points", trained_adapters),
                                    self._create_action_chip("🔍 Find", "Find specific information about", trained_adapters),
                                    self._create_action_chip("📊 Compare", "Compare and contrast", trained_adapters),
                                    self._create_action_chip("💡 Explain", "Explain in simple terms", trained_adapters),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=12,
                                wrap=True,
                            ),
                        ],
                                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    padding=ft.padding.only(top=80),
                )
            )
        
        # Store reference for updates
        self.chat_messages_list = chat_messages_list
        self.trained_adapters = trained_adapters
        
        # Input area - always enabled! Users can chat with base model even without documents
        chat_input = ft.TextField(
            hint_text="Ask me anything..." if adapter_count == 0 else f"Ask about your {adapter_count} document{'s' if adapter_count != 1 else ''}...",
            border_radius=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            content_padding=ft.padding.symmetric(horizontal=20, vertical=14),
            expand=True,
            disabled=False,  # Always enabled - can chat with base model
            on_submit=lambda e: self._send_chat_message(e, chat_input, trained_adapters),
        )
        self.chat_input = chat_input  # Store reference
        
        # Inference mode indicator (local-only)
        inference_toggle = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.COMPUTER_ROUNDED, size=14, color="white"),
                            ft.Text("Local", size=11, color="white"),
                        ], spacing=4),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                        border_radius=8,
                        tooltip="Local inference only (cloud disabled)",
                    ),
                ],
                spacing=0,
            ),
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            border_radius=8,
        )
        
        input_area = ft.Container(
            content=ft.Column(
                [
                    # Controls row: ALWAYS visible - Inference mode + Document selector
                    ft.Row(
                        [
                            # Document/Adapter selector with loaded status
                            ft.Container(
                                content=ft.Row(
                                    [
                                        # Show loaded adapter status prominently
                                        ft.Icon(
                                            ft.Icons.MEMORY_ROUNDED if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter else (
                                                ft.Icons.SMART_TOY_ROUNDED if adapter_count == 0 else ft.Icons.DESCRIPTION_ROUNDED
                                            ),
                                            size=12, 
                                            color=LightTheme.ACCENT_SUCCESS if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter else LightTheme.ACCENT_PRIMARY
                                        ),
                                        ft.Text(
                                            self._get_loaded_adapter_display(trained_adapters),
                                            size=11,
                                            color=LightTheme.ACCENT_SUCCESS if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter else LightTheme.ACCENT_PRIMARY,
                                            weight=ft.FontWeight.W_600 if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter else ft.FontWeight.W_400,
                                        ),
                                        ft.Icon(ft.Icons.ARROW_DROP_DOWN_ROUNDED, size=16, color=LightTheme.TEXT_MUTED) if adapter_count > 1 else ft.Container(),
                                    ],
                                    spacing=4,
                                ),
                                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                bgcolor=(LightTheme.ACCENT_SUCCESS + "15") if hasattr(self, '_loaded_local_adapter') and self._loaded_local_adapter else (LightTheme.ACCENT_PRIMARY + "10"),
                                border_radius=12,
                                on_click=lambda e: self._show_adapter_selector(trained_adapters) if adapter_count > 1 else None,
                                tooltip=self._get_loaded_adapter_tooltip(trained_adapters),
                            ),
                            ft.Container(expand=True),
                            # Inference mode toggle - ALWAYS visible
                            inference_toggle,
                            ft.Container(width=8),
                            # Privacy indicator
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.LOCK_ROUNDED, size=12, color=LightTheme.ACCENT_SUCCESS),
                                        ft.Text("E2E", size=11, color=LightTheme.ACCENT_SUCCESS),
                                    ],
                                    spacing=4,
                                ),
                                tooltip="End-to-end encrypted",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Container(height=8),
                    # Input row
                    ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                                icon_color=LightTheme.TEXT_MUTED,
                                tooltip="Upload PDF to enhance AI knowledge",
                                on_click=lambda e: self._on_upload_click(e),
                            ),
                            chat_input,
                            ft.Container(
                                content=ft.IconButton(
                                    ft.Icons.SEND_ROUNDED,
                                    icon_color="white",
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    on_click=lambda e: self._send_chat_message(e, chat_input, trained_adapters),
                                    disabled=False,  # Always enabled
                                ),
                                border_radius=24,
                            ),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.symmetric(horizontal=40, vertical=16),
            bgcolor=LightTheme.BG_PRIMARY,
            border=ft.border.only(top=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )
        
        # Main chat container
        main_chat = ft.Container(
            content=ft.Column(
                [
                    # Header with user email
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(expand=True),
                                ft.Container(
                                    content=ft.Row(
                                        [
                                            ft.Icon(ft.Icons.PERSON_ROUNDED, size=16, color=LightTheme.TEXT_MUTED),
                                            ft.Text(user_email, size=12, color=LightTheme.TEXT_MUTED),
                                        ],
                                        spacing=6,
                                    ),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                                    bgcolor=LightTheme.BG_HOVER,
                                    border_radius=16,
                                ),
                                ft.IconButton(
                                    ft.Icons.SETTINGS_ROUNDED,
                                    icon_color=LightTheme.TEXT_MUTED,
                                    icon_size=20,
                                    tooltip="Settings",
                                    on_click=lambda e: self.show_settings(),
                                ),
                                ft.IconButton(
                                    ft.Icons.LOGOUT_ROUNDED,
                                    icon_color=LightTheme.TEXT_MUTED,
                                    icon_size=20,
                                    tooltip="Logout",
                                    on_click=lambda e: self.logout(),
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
                    ),
                    # Chat messages
                    chat_messages_list,
                    # Input area
                    input_area,
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )
        
        # Full layout
        self.page.add(
            ft.Row(
                [
                    left_sidebar,
                    main_chat,
                ],
                spacing=0,
                expand=True,
            )
        )
        self.page.update()
        
        # Start automatic status polling for pending/training documents
        self._start_landing_status_polling()
    
    def _stop_landing_status_polling(self):
        """Stop automatic status polling for landing page."""
        self._landing_status_polling_active = False
        if self._landing_status_timer:
            self._landing_status_timer.cancel()
            self._landing_status_timer = None
    
    def _start_landing_status_polling(self):
        """Start automatic status polling for pending/training documents on landing page."""
        # Stop any existing polling first
        self._stop_landing_status_polling()
        
        def poll_status():
            """Poll status for pending/training documents."""
            if not self._landing_status_polling_active or self.current_view != "landing":
                return
            
            try:
                # Find documents with pending/training status
                query_filter = QueryFilter()
                all_entries = self.vault.kv_store.search(query_filter)
                
                pending_docs = []
                for entry in all_entries:
                    if entry.tags:
                        status = None
                        adapter_id = None
                        for tag in entry.tags:
                            if tag.startswith("training_status:"):
                                status = tag.split(":", 1)[1]
                            elif tag.startswith("training_job:"):
                                adapter_id = tag.split(":", 1)[1]
                        
                        if status in ["pending", "training"] and adapter_id:
                            pending_docs.append({
                                "name": entry.service,
                                "adapter_id": adapter_id,
                                "status": status
                            })
                
                if not pending_docs:
                    # No pending documents, stop polling
                    self._landing_status_polling_active = False
                    return
                
                # Check status for each pending document
                updated_count = 0
                for doc in pending_docs:
                    try:
                        if not self.training_manager:
                            continue
                        
                        status_result = self.training_manager.get_job_status(doc["adapter_id"])
                        new_status = status_result.get("status", "unknown").lower()
                        
                        if new_status == "completed" and doc["status"] != "completed":
                            # Status changed to completed! Update vault
                            logger.info(f"Status changed to completed for {doc['name']}")
                            self._update_document_status(doc["name"], "completed", doc["adapter_id"])
                            updated_count += 1
                        elif new_status == "failed" and doc["status"] != "failed":
                            # Status changed to failed
                            logger.info(f"Status changed to failed for {doc['name']}")
                            self._update_document_status(doc["name"], "failed", doc["adapter_id"])
                            updated_count += 1
                    except Exception as e:
                        logger.debug(f"Error checking status for {doc['name']}: {e}")
                
                # If any status changed, refresh the landing page
                if updated_count > 0:
                    logger.info(f"Refreshing landing page after {updated_count} status updates")
                    self.show_landing_page()
                    return
                
                # Schedule next poll (every 10 seconds)
                self._landing_status_timer = threading.Timer(10.0, poll_status)
                self._landing_status_timer.daemon = True
                self._landing_status_timer.start()
                
            except Exception as e:
                logger.debug(f"Error in landing status polling: {e}")
                # Retry in 15 seconds on error
                self._landing_status_timer = threading.Timer(15.0, poll_status)
                self._landing_status_timer.daemon = True
                self._landing_status_timer.start()
        
        # Start polling if there are pending documents
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            
            has_pending = False
            for entry in all_entries:
                if entry.tags:
                    for tag in entry.tags:
                        if tag.startswith("training_status:"):
                            status = tag.split(":", 1)[1]
                            if status in ["pending", "training"]:
                                has_pending = True
                                break
                    if has_pending:
                        break
            
            if has_pending:
                self._landing_status_polling_active = True
                # Start first poll after 5 seconds
                self._landing_status_timer = threading.Timer(5.0, poll_status)
                self._landing_status_timer.daemon = True
                self._landing_status_timer.start()
                logger.info("Started automatic status polling for landing page")
        except Exception as e:
            logger.debug(f"Could not start landing status polling: {e}")
    
    def _get_rag_stats(self) -> dict:
        """Get lightweight statistics for the active local Private Model profile."""
        try:
            profile = self._ensure_private_model_profile()
            status = self._get_private_model_status()
            db_path = self.private_model_manager._profile_vault_path(profile.name) / "rag.db"
            return {
                "document_count": int(status.get("document_count", 0)),
                "chunk_count": int(status.get("chunk_count", 0)),
                "embedding_dimension": 0,
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "db_path": str(db_path),
                "encrypted": True,
                "hnsw_enabled": db_path.with_suffix(".hnsw").exists(),
            }
        except Exception as e:
            logger.debug(f"Failed to read local profile stats: {e}")
            return {"document_count": 0, "chunk_count": 0, "embedding_dimension": 0}

    def _get_rag_status(self) -> dict:
        """Get normalized RAG status payload used by landing widgets."""
        stats = self._get_rag_stats() or {}
        deps = self._check_rag_dependencies()
        return {
            "document_count": int(stats.get("document_count", 0) or 0),
            "chunk_count": int(stats.get("chunk_count", 0) or 0),
            "embedding_dimension": int(stats.get("embedding_dimension", 0) or 0),
            "ready": bool(deps.get("ready")),
            "missing": deps.get("missing", []),
            "error": deps.get("error"),
        }

    def _check_rag_dependencies(self) -> dict:
        """Check if RAG dependencies are available."""
        result = {
            "ready": False,
            "missing": [],
            "model_loaded": False,
            "error": None
        }
        try:
            # Check sentence-transformers
            try:
                from sentence_transformers import SentenceTransformer
                result["model_loaded"] = True
            except ImportError:
                result["missing"].append("sentence-transformers")

            # Check numpy
            try:
                import numpy
            except ImportError:
                result["missing"].append("numpy")

            # Check cryptography
            try:
                from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
            except ImportError:
                result["missing"].append("cryptography")

            # If no missing dependencies, RAG is ready
            if not result["missing"]:
                result["ready"] = True

        except Exception as e:
            result["error"] = str(e)

        return result

    def _get_rag_documents(self) -> list:
        """Get the documents indexed in the active Private Model profile."""
        try:
            return self._get_private_model_documents()
        except Exception:
            return []

    def _delete_rag_document(self, document_id: str):
        """Delete a document from the active Private Model profile."""
        try:
            profile = self._ensure_private_model_profile()
            rag = self.private_model_manager._open_rag_index(profile.name)
            try:
                success = rag.delete_document(document_id)
            finally:
                rag.close()
            self._reset_private_model_session()
            if success:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Document removed from active profile"),
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                )
            else:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text("Document not found"),
                    bgcolor=LightTheme.ACCENT_WARNING,
                )
            self.page.snack_bar.open = True
            self.page.update()
            if self.current_view == "my_data":
                self.show_my_data_view(active_tab="knowledge")
            else:
                self.show_landing_page()
        except Exception as e:
            logger.error(f"Failed to delete RAG document: {e}")

    def _index_document_in_rag(self, name: str, content: str, source_path: str = None):
        """Index a document into the active Private Model profile."""
        try:
            profile = self._ensure_private_model_profile()
            session = self.private_model_manager.open_session(profile.name)
            try:
                doc = session.add_document(name=name, content=content, source_path=source_path)
            finally:
                session.close()
            self._reset_private_model_session()
            self._private_model_note = f"Added {name} to {profile.name}. It is ready for local chat."
            logger.info(f"Indexed '{name}' in Private Model profile '{profile.name}': {len(doc.chunks)} chunks")
        except Exception as e:
            logger.error(f"Private Model indexing error: {e}")

    def _show_workspace_view(self, initial_question: Optional[str] = None):
        """Render the primary Private Model workspace."""
        self.current_view = "agent_chat"
        self._ensure_chat_messages_loaded()

        profile = self._ensure_private_model_profile()
        profiles = self._get_private_model_profiles()
        profile_status = self._get_private_model_status()
        documents = self._get_private_model_documents(limit=10)
        module_statuses = self._update_module_status_snapshots()
        user_label = self._get_identity_label()

        self.page.clean()
        self._ensure_private_model_pickers()

        chat_stream = ft.Column(
            spacing=16,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        if self.chat_messages:
            for msg in self.chat_messages:
                chat_stream.controls.append(
                    self._create_chat_bubble(
                        msg["role"],
                        msg["content"],
                        msg.get("document"),
                        msg.get("sources"),
                    )
                )
        else:
            quick_prompts = [
                "Summarize the main themes across my indexed files.",
                "What are the most important risks or open questions in this context?",
                "Give me an investor-ready narrative from these materials.",
                "What should I read first to get up to speed quickly?",
            ]
            chat_stream.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, size=48, color=LightTheme.ACCENT_PRIMARY),
                                padding=18,
                                border_radius=18,
                                bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                            ),
                            ft.Container(height=8),
                            ft.Text(
                                f"{profile.name} is ready for private local chat",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                                color=LightTheme.TEXT_PRIMARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Ask from your encrypted context, keep documents local, and let WDVA layers shape behavior when attached.",
                                size=14,
                                color=LightTheme.TEXT_SECONDARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=20),
                            ft.Row(
                                [
                                    self._create_action_chip("Summarize", quick_prompts[0], []),
                                    self._create_action_chip("Risks", quick_prompts[1], []),
                                    self._create_action_chip("Narrative", quick_prompts[2], []),
                                    self._create_action_chip("Onboard", quick_prompts[3], []),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=12,
                                wrap=True,
                            ),
                            ft.Container(height=20),
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Add Files",
                                        icon=ft.Icons.FILE_UPLOAD_ROUNDED,
                                        on_click=self._open_private_files_picker,
                                        style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                                    ),
                                    ft.OutlinedButton(
                                        "Add Folder",
                                        icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED,
                                        on_click=self._open_private_folder_picker,
                                        style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                                    ),
                                    ft.OutlinedButton(
                                        "Open Library",
                                        icon=ft.Icons.FOLDER_ROUNDED,
                                        on_click=lambda e: self.show_my_data_view(active_tab="context"),
                                        style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=12,
                                wrap=True,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=0,
                    ),
                    alignment=ft.alignment.center,
                    padding=36,
                    border_radius=20,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    margin=ft.margin.only(top=56, bottom=24),
                )
            )

        self.chat_messages_list = chat_stream
        self.trained_adapters = []

        chat_input = ft.TextField(
            hint_text=(
                f"Ask about your {profile_status.get('document_count', 0)} indexed document(s)..."
                if profile_status.get("document_count", 0) > 0
                else "Ask a question, then add files or folders to deepen the context..."
            ),
            border_radius=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            content_padding=ft.padding.symmetric(horizontal=20, vertical=14),
            expand=True,
            on_submit=lambda e: self._send_chat_message(
                e,
                chat_input,
                [],
                mode_override="local",
                allow_cloud_fallback=False,
            ),
        )
        self.chat_input = chat_input

        sidebar_controls: List[ft.Control] = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Active Profile", size=13, color=LightTheme.TEXT_MUTED),
                                ft.Container(expand=True),
                                ft.TextButton(
                                    "New",
                                    icon=ft.Icons.ADD_ROUNDED,
                                    on_click=self._open_create_profile_dialog,
                                    style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                                ),
                            ]
                        ),
                        ft.Dropdown(
                            value=profile.name,
                            options=[ft.dropdown.Option(item.name, item.name) for item in profiles],
                            border_radius=12,
                            filled=True,
                            bgcolor=LightTheme.BG_PRIMARY,
                            on_change=lambda e: self._set_active_private_profile(e.control.value),
                        ),
                        ft.Container(height=12),
                        ft.Text(profile.description or "Private context workspace", size=12, color=LightTheme.TEXT_SECONDARY),
                    ],
                    spacing=8,
                ),
                padding=20,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
            ft.Container(height=12),
            ft.Container(
                content=ft.Row(
                    [
                        ft.ElevatedButton(
                            "Add Files",
                            icon=ft.Icons.FILE_UPLOAD_ROUNDED,
                            on_click=self._open_private_files_picker,
                            style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                        ),
                        ft.OutlinedButton(
                            "Add Folder",
                            icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED,
                            on_click=self._open_private_folder_picker,
                            style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                        ),
                    ],
                    spacing=10,
                    wrap=True,
                ),
            ),
            ft.Container(height=12),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Workspace Status", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        ft.Container(height=10),
                        ft.Row([ft.Icon(ft.Icons.FOLDER_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY), ft.Text(f"{profile_status.get('document_count', 0)} documents", size=12, color=LightTheme.TEXT_PRIMARY)], spacing=8),
                        ft.Row([ft.Icon(ft.Icons.DATA_OBJECT_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS), ft.Text(f"{profile_status.get('chunk_count', 0)} encrypted chunks", size=12, color=LightTheme.TEXT_PRIMARY)], spacing=8),
                        ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=16, color=LightTheme.ACCENT_WARNING), ft.Text(f"{len(profile.wdva_adapters)} WDVA layers", size=12, color=LightTheme.TEXT_PRIMARY)], spacing=8),
                        ft.Row([ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY), ft.Text((profile_status.get("model_name") or DEFAULT_PRIVATE_MODEL_NAME).split("/")[-1], size=12, color=LightTheme.TEXT_PRIMARY)], spacing=8),
                    ],
                    spacing=8,
                ),
                padding=20,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
            ft.Container(height=12),
            ft.Text("Indexed Context", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
        ]

        if documents:
            for doc in documents[:8]:
                parent_name = Path(doc.get("source_path") or doc.get("name", "")).parent.name or "Local import"
                sidebar_controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                ft.Column(
                                    [
                                        ft.Text(doc.get("name", "Untitled"), size=12, color=LightTheme.TEXT_PRIMARY, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                        ft.Text(f"{doc.get('chunk_count', 0)} chunks • {parent_name}", size=10, color=LightTheme.TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=12,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=12,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        else:
            sidebar_controls.append(
                ft.Container(
                    content=ft.Text(
                        "Add files or a folder to build context for this profile.",
                        size=12,
                        color=LightTheme.TEXT_MUTED,
                    ),
                    padding=12,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_radius=12,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                )
            )

        sidebar_controls.extend(
            [
                ft.Container(height=12),
                ft.Text("WDVA Layers", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ]
        )

        if profile.wdva_adapters:
            for adapter in profile.wdva_adapters[:4]:
                sidebar_controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=18, color=LightTheme.ACCENT_WARNING),
                                ft.Column(
                                    [
                                        ft.Text(adapter.name, size=12, color=LightTheme.TEXT_PRIMARY, weight=ft.FontWeight.W_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                        ft.Text(adapter.description or "Private WDVA layer", size=10, color=LightTheme.TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Text(f"{int(adapter.weight * 100)}%", size=10, color=LightTheme.ACCENT_WARNING),
                            ],
                            spacing=10,
                        ),
                        padding=12,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=12,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        else:
            sidebar_controls.append(
                ft.Container(
                    content=ft.Text(
                        "No WDVA layers attached yet. This profile is ready when you want domain-specific behavior.",
                        size=12,
                        color=LightTheme.TEXT_MUTED,
                    ),
                    padding=12,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_radius=12,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                )
            )

        context_panel = ft.Container(
            content=ft.Column(sidebar_controls, spacing=0, scroll=ft.ScrollMode.AUTO),
            width=340,
            padding=20,
            bgcolor=LightTheme.BG_SECONDARY,
            border=ft.border.only(right=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Secure Chat Workspace", size=22, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                            ft.Text("Private context, local generation, and investor-demo polish in one place.", size=13, color=LightTheme.TEXT_SECONDARY),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.COMPUTER_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Local MLX", size=11, color=LightTheme.ACCENT_SUCCESS)], spacing=6),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.ACCENT_SUCCESS + "10",
                        border_radius=999,
                    ),
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.LOCK_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Encrypted context", size=11, color=LightTheme.ACCENT_SUCCESS)], spacing=6),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.ACCENT_SUCCESS + "10",
                        border_radius=999,
                    ),
                    ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.PERSON_ROUNDED, size=14, color=LightTheme.TEXT_MUTED), ft.Text(user_label, size=11, color=LightTheme.TEXT_MUTED)], spacing=6),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=999,
                    ),
                ],
                spacing=10,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=18),
            bgcolor=LightTheme.BG_PRIMARY,
            border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )

        workspace_toolbar = ft.Container(
            content=ft.Row(
                [
                    ft.Dropdown(
                        value=profile.name,
                        options=[ft.dropdown.Option(item.name, item.name) for item in profiles],
                        width=220,
                        border_radius=12,
                        filled=True,
                        bgcolor=LightTheme.BG_PRIMARY,
                        on_change=lambda e: self._set_active_private_profile(e.control.value),
                    ),
                    ft.ElevatedButton(
                        "Add Files",
                        icon=ft.Icons.FILE_UPLOAD_ROUNDED,
                        on_click=self._open_private_files_picker,
                        style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                    ),
                    ft.OutlinedButton(
                        "Add Folder",
                        icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED,
                        on_click=self._open_private_folder_picker,
                        style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                    ),
                    ft.TextButton(
                        "Library",
                        icon=ft.Icons.FOLDER_ROUNDED,
                        on_click=lambda e: self.show_my_data_view(active_tab="context"),
                        style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                    ),
                    ft.Container(
                        content=ft.Text(f"{profile_status.get('document_count', 0)} docs", size=11, color=LightTheme.ACCENT_PRIMARY),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                        border_radius=999,
                    ),
                    ft.Container(
                        content=ft.Text(f"{len(profile.wdva_adapters)} WDVA", size=11, color=LightTheme.ACCENT_WARNING),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.ACCENT_WARNING + "10",
                        border_radius=999,
                    ),
                    ft.Container(
                        content=ft.Text((profile_status.get("model_name") or DEFAULT_PRIVATE_MODEL_NAME).split("/")[-1], size=11, color=LightTheme.TEXT_MUTED),
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=LightTheme.BG_PRIMARY,
                        border_radius=999,
                    ),
                ],
                spacing=10,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=16),
            bgcolor=LightTheme.BG_ELEVATED,
            border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )

        def status_tile(label: str, value: str, icon: str, color: str) -> ft.Container:
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=16, color=color),
                            padding=8,
                            border_radius=10,
                            bgcolor=color + "12",
                        ),
                        ft.Column(
                            [
                                ft.Text(value, size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                ft.Text(label, size=11, color=LightTheme.TEXT_MUTED),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                    ],
                    spacing=10,
                ),
                padding=ft.padding.symmetric(horizontal=14, vertical=12),
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=14,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            )

        vault_runtime_status = module_statuses.get("vault", {}).get("details", {})
        wallet_runtime_status = module_statuses.get("wallet", {}).get("details", {})
        workspace_status_strip = ft.Container(
            content=ft.Row(
                [
                    status_tile(
                        "Documents",
                        str(vault_runtime_status.get("document_count", profile_status.get("document_count", 0))),
                        ft.Icons.FOLDER_ROUNDED,
                        LightTheme.ACCENT_PRIMARY,
                    ),
                    status_tile(
                        "Encrypted Chunks",
                        str(vault_runtime_status.get("chunk_count", profile_status.get("chunk_count", 0))),
                        ft.Icons.DATA_OBJECT_ROUNDED,
                        LightTheme.ACCENT_SUCCESS,
                    ),
                    status_tile(
                        "WDVA Layers",
                        str(vault_runtime_status.get("adapter_count", len(profile.wdva_adapters))),
                        ft.Icons.AUTO_AWESOME_ROUNDED,
                        LightTheme.ACCENT_WARNING,
                    ),
                    status_tile(
                        "Wallet Pending",
                        str(wallet_runtime_status.get("pending_count", 0)),
                        ft.Icons.ACCOUNT_BALANCE_WALLET_ROUNDED,
                        LightTheme.ACCENT_PRIMARY,
                    ),
                ],
                spacing=12,
                wrap=True,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=16),
            bgcolor=LightTheme.BG_PRIMARY,
            border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )

        recent_context_strip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                    ft.Text("Indexed Context", size=12, color=LightTheme.TEXT_MUTED),
                    ft.Container(expand=True),
                    *[
                        ft.Container(
                            content=ft.Text(
                                doc.get("name", "Untitled"),
                                size=11,
                                color=LightTheme.TEXT_PRIMARY,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            padding=ft.padding.symmetric(horizontal=10, vertical=6),
                            bgcolor=LightTheme.BG_ELEVATED,
                            border_radius=999,
                            border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        )
                        for doc in documents[:3]
                    ],
                ],
                spacing=10,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            bgcolor=LightTheme.BG_PRIMARY,
            border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
            visible=bool(documents),
        )

        input_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(self._private_model_note, size=11, color=LightTheme.TEXT_MUTED, expand=True),
                            ft.TextButton(
                                "New Chat",
                                icon=ft.Icons.ADD_COMMENT_ROUNDED,
                                on_click=lambda e: self._new_chat(),
                                style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.ATTACH_FILE_ROUNDED,
                                icon_color=LightTheme.TEXT_MUTED,
                                tooltip="Add files to this profile",
                                on_click=self._open_private_files_picker,
                            ),
                            chat_input,
                            ft.Container(
                                content=ft.IconButton(
                                    ft.Icons.SEND_ROUNDED,
                                    icon_color="white",
                                    bgcolor=LightTheme.ACCENT_PRIMARY,
                                    on_click=lambda e: self._send_chat_message(
                                        e,
                                        chat_input,
                                        [],
                                        mode_override="local",
                                        allow_cloud_fallback=False,
                                    ),
                                ),
                                border_radius=24,
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=18),
            bgcolor=LightTheme.BG_PRIMARY,
            border=ft.border.only(top=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        )

        chat_surface = ft.Container(
            content=chat_stream,
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
            padding=ft.padding.symmetric(horizontal=28, vertical=24),
        )

        chat_panel = ft.Container(
            content=ft.Column(
                [
                    header,
                    workspace_toolbar,
                    workspace_status_strip,
                    recent_context_strip,
                    chat_surface,
                    input_panel,
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        if not hasattr(self, "sidebar") or self.sidebar is None:
            self.sidebar = ModernSidebar(
                on_nav_change=self.on_nav_change,
                selected_index=-1,
                translate=self.tr,
            )
        else:
            self.sidebar.selected_index = -1
            self.sidebar.translate = self.tr
        sidebar_container = self.sidebar.build()

        self.page.add(
            ft.Row(
                [
                    sidebar_container,
                    chat_panel,
                ],
                spacing=0,
                expand=True,
            )
        )
        self.page.update()

        if initial_question:
            chat_input.value = initial_question
            self.page.update()
            self._send_chat_message(
                None,
                chat_input,
                [],
                mode_override="local",
                allow_cloud_fallback=False,
            )

    def _open_test_agent_chat(self, initial_question: Optional[str] = None):
        """Backward-compatible wrapper for opening the primary workspace."""
        self._show_workspace_view(initial_question=initial_question)

    def _close_dialog(self, dlg):
        """Close a dialog."""
        dlg.open = False
        self.page.update()

    def _set_example_question(self, input_field: ft.TextField, question: str):
        """Set example question in the input field."""
        input_field.value = question
        self.page.update()
    
    def _create_chat_bubble(
        self,
        role: str,
        content: str,
        document: str = None,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> ft.Container:
        """Create a chat message bubble."""
        is_user = role == "user"

        source_controls: List[ft.Control] = []
        if sources and not is_user:
            source_controls.append(ft.Container(height=6))
            source_controls.append(
                ft.Text(
                    "Sources:",
                    size=11,
                    color=LightTheme.TEXT_MUTED,
                    weight=ft.FontWeight.W_600,
                )
            )
            for source in sources[:3]:
                doc = source.get("document") or source.get("document_name") or "Unknown"
                score = source.get("score")
                excerpt = source.get("excerpt")
                confidence = f"{int(float(score) * 100)}%" if score is not None else "n/a"
                source_controls.append(
                    ft.Text(
                        f"• {doc} ({confidence})",
                        size=11,
                        color=LightTheme.TEXT_MUTED,
                        italic=True,
                    )
                )
                if excerpt:
                    source_controls.append(
                        ft.Text(
                            f"  \"{excerpt}\"",
                            size=10,
                            color=LightTheme.TEXT_MUTED,
                            italic=True,
                            max_lines=2,
                        )
                    )
        
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=40) if is_user else ft.Container(
                        content=ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=20, color="white"),
                        width=36,
                        height=36,
                        bgcolor=LightTheme.ACCENT_PRIMARY,
                        border_radius=18,
                        alignment=ft.alignment.center,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    content,
                                    size=14,
                                    color=LightTheme.TEXT_PRIMARY,
                                    selectable=True,
                                ),
                                *source_controls,
                                ft.Container(height=4) if document and not is_user else ft.Container(),
                                ft.Text(
                                    f"📄 Based on: {document}",
                                    size=11,
                                    color=LightTheme.TEXT_MUTED,
                                    italic=True,
                                ) if document and not is_user else ft.Container(),
                            ],
                            spacing=0,
                        ),
                        padding=16,
                        bgcolor=LightTheme.ACCENT_PRIMARY + "10" if is_user else LightTheme.BG_ELEVATED,
                        border_radius=ft.border_radius.only(
                            top_left=16,
                            top_right=16,
                            bottom_left=4 if is_user else 16,
                            bottom_right=16 if is_user else 4,
                        ),
                    expand=True,
                    ),
                    ft.Container(
                        content=ft.Icon(ft.Icons.PERSON_ROUNDED, size=20, color="white"),
                        width=36,
                        height=36,
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                        border_radius=18,
                        alignment=ft.alignment.center,
                    ) if is_user else ft.Container(width=40),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            margin=ft.margin.only(left=60 if is_user else 0, right=0 if is_user else 60),
        )
    
    def _create_action_chip(self, label: str, prompt: str, adapters: list) -> ft.Container:
        """Create a quick action chip."""
        return ft.Container(
            content=ft.TextButton(
                label,
                on_click=lambda e: self._quick_ask(prompt, adapters),
                style=ft.ButtonStyle(
                    color=LightTheme.TEXT_PRIMARY,
                    shape=ft.RoundedRectangleBorder(radius=20),
                ),
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=20,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
        )
    
    def _quick_ask(self, question: str, adapters: list):
        """Handle quick ask from history or chips."""
        if hasattr(self, 'chat_input') and self.chat_input:
            self.chat_input.value = question
        self.page.update()
            # Optionally auto-submit
            # self._send_chat_message(None, self.chat_input, adapters)
    
    def _new_chat(self):
        """Start a new chat session."""
        self._reset_private_model_session()
        self.chat_messages = []
        self._chat_history_profile = self.active_private_profile_name or "workspace"
        self._save_chat_history_to_file()
        if self.current_view == "agent_chat":
            self._open_test_agent_chat()
        else:
            self.show_landing_page()
    
    def _load_chat_history(self) -> list:
        """Load chat history from file."""
        import json
        chat_file = self._chat_history_file_path()
        try:
            if chat_file.exists():
                with open(chat_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to load chat history: {e}")
        return []
    
    def _save_chat_history_to_file(self):
        """Save chat history to file."""
        import json
        chat_file = self._chat_history_file_path()
        try:
            with open(chat_file, 'w') as f:
                json.dump(self.chat_messages if hasattr(self, 'chat_messages') else [], f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save chat history: {e}")
    
    def _create_processing_card(self, filename: str, status_info: Dict[str, Any]) -> ft.Container:
        """
        Create a document processing card for the sidebar.
        
        Shows step-by-step progress with visual indicators.
        
        Status info structure:
        {
            "status": "processing" | "completed" | "failed",
            "step": 0-4 (current step),
            "progress": 0.0-1.0,
            "message": "Current action...",
            "steps_completed": [True, False, False, False],
            "error": Optional[str]
        }
        """
        step = status_info.get("step", 0)
        progress = status_info.get("progress", 0.0)
        message = status_info.get("message", "Processing...")
        status = status_info.get("status", "processing")
        steps_completed = status_info.get("steps_completed", [False, False, False, False])
        error = status_info.get("error")
        
        # Step labels (updated terminology - no "training")
        step_labels = [
            "Extracting text",
            "Analyzing content",
            "Encrypting data",
            "Syncing to cloud",
        ]
        
        # Truncate filename for display
        display_name = filename[:22] + "..." if len(filename) > 25 else filename
        
        # Icon based on status
        if status == "completed":
            status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=16, color=LightTheme.ACCENT_SUCCESS)
            header_color = LightTheme.ACCENT_SUCCESS
        elif status == "failed":
            status_icon = ft.Icon(ft.Icons.ERROR_ROUNDED, size=16, color=LightTheme.ACCENT_ERROR)
            header_color = LightTheme.ACCENT_ERROR
        else:
            status_icon = ft.ProgressRing(width=16, height=16, stroke_width=2, color=LightTheme.ACCENT_PRIMARY)
            header_color = LightTheme.ACCENT_PRIMARY
        
        # Build step indicators
        step_items = []
        for i, label in enumerate(step_labels):
            if steps_completed[i]:
                icon = ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=12, color=LightTheme.ACCENT_SUCCESS)
                text_color = LightTheme.ACCENT_SUCCESS
            elif i == step and status == "processing":
                icon = ft.Container(
                    content=ft.ProgressRing(width=10, height=10, stroke_width=2, color=LightTheme.ACCENT_PRIMARY),
                    padding=1,
                )
                text_color = LightTheme.TEXT_PRIMARY
            else:
                icon = ft.Icon(ft.Icons.CIRCLE_OUTLINED, size=12, color=LightTheme.TEXT_MUTED)
                text_color = LightTheme.TEXT_MUTED
            
            step_items.append(
                ft.Row(
                    [icon, ft.Text(label, size=10, color=text_color)],
                    spacing=6,
                )
            )
        
        # Main content
        content_children = [
            # Header with filename and status
            ft.Row(
                [
                    ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=14, color=header_color),
                    ft.Text(
                        display_name,
                        size=12,
                        weight=ft.FontWeight.W_500,
                        color=LightTheme.TEXT_PRIMARY,
                        expand=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    status_icon,
                ],
                spacing=8,
            ),
        ]
        
        # Show step details only while processing
        if status == "processing":
            content_children.extend([
                ft.Container(height=8),
                # Step indicators
                ft.Column(step_items, spacing=4),
                ft.Container(height=8),
                # Progress bar
                ft.ProgressBar(
                    value=progress,
                    color=LightTheme.ACCENT_PRIMARY,
                    bgcolor=LightTheme.BG_HOVER,
                    bar_height=4,
                ),
                ft.Container(height=4),
                # Current message
                ft.Text(
                    f"Step {step + 1}/4 • {message}",
                    size=10,
                    color=LightTheme.TEXT_MUTED,
                ),
            ])
        elif status == "completed":
            content_children.append(
                ft.Container(
                    content=ft.Text("✓ Ready to query", size=10, color=LightTheme.ACCENT_SUCCESS),
                    padding=ft.padding.only(top=4),
                )
            )
        elif status == "failed" and error:
            content_children.append(
                ft.Container(
                    content=ft.Text(f"❌ {error[:30]}...", size=10, color=LightTheme.ACCENT_ERROR),
                    padding=ft.padding.only(top=4),
                )
            )
        
        return ft.Container(
            content=ft.Column(
                content_children,
                spacing=0,
            ),
            padding=ft.padding.all(12),
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=8,
            border=ft.border.all(1, header_color + "30"),
            margin=ft.margin.only(left=12, right=12, bottom=8),
        )
    
    def _update_processing_status(self, filename: str, step: int, message: str, 
                                   progress: float = None, status: str = "processing",
                                   error: str = None):
        """
        Update the processing status for a document and refresh the UI.
        
        Args:
            filename: Document filename
            step: Current step (0-3)
            message: Status message
            progress: Overall progress (0.0-1.0), calculated from step if not provided
            status: "processing", "completed", or "failed"
            error: Error message if failed
        """
        if progress is None:
            # Calculate progress from step (each step is 25%)
            progress = min((step + 0.5) / 4, 1.0)
        
        # Update steps_completed based on current step
        steps_completed = [i < step for i in range(4)]
        
        self.processing_documents[filename] = {
            "status": status,
            "step": step,
            "progress": progress,
            "message": message,
            "steps_completed": steps_completed,
            "error": error,
        }
        
        # Refresh sidebar if on landing page
        if self.current_view == "landing":
            try:
                self._refresh_sidebar_documents()
            except Exception as e:
                logger.debug(f"Could not refresh sidebar: {e}")
    
    def _refresh_sidebar_documents(self):
        """Refresh just the document list in sidebar without full page reload."""
        # This is called from background thread, so we need to be careful
        # For now, we'll trigger a full refresh - can optimize later
        if hasattr(self, 'page') and self.current_view == "landing":
            try:
                self.page.update()
            except Exception as e:
                logger.debug(f"Sidebar refresh failed: {e}")
    
    def _show_completion_toast(self, filename: str, success: bool = True, error_msg: str = None):
        """Show a toast notification when document processing completes."""
        if success:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="white", size=20),
                        ft.Text(f'"{filename}" is ready to query!', color="white", weight=ft.FontWeight.W_500),
                    ],
                    spacing=12,
                ),
                bgcolor=LightTheme.ACCENT_SUCCESS,
                duration=5000,  # 5 seconds
                action="Ask Now",
                action_color="white",
                on_action=lambda e: self.show_landing_page(),
            )
        else:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_ROUNDED, color="white", size=20),
                        ft.Text(f'Failed to process "{filename}"', color="white"),
                    ],
                    spacing=12,
                ),
                bgcolor=LightTheme.ACCENT_ERROR,
                duration=6000,
                action="Retry",
                action_color="white",
            )
        
        self.page.snack_bar.open = True
        self.page.update()

    def _query_private_model(self, query: str) -> Dict[str, Any]:
        """Run a chat request through the active local Private Model profile."""
        profile = self._ensure_private_model_profile()
        session = self._get_private_model_session()
        result = session.ask(question=query, temperature=0.2)

        sources = []
        for item in result.get("sources", []):
            normalized = dict(item)
            if "document" not in normalized and normalized.get("document_name"):
                normalized["document"] = normalized["document_name"]
            sources.append(normalized)

        ordered_documents = []
        for source in sources:
            name = source.get("document")
            if name and name not in ordered_documents:
                ordered_documents.append(name)

        if ordered_documents:
            document_label = ", ".join(ordered_documents[:3])
        elif result.get("adapters"):
            document_label = f"{profile.name} + {len(result.get('adapters', []))} WDVA layer(s)"
        else:
            document_label = profile.name

        return {
            "answer": result.get("answer", ""),
            "document": document_label,
            "sources": sources,
            "warning": result.get("warning"),
        }
    
    def _send_chat_message(
        self,
        e,
        input_field: ft.TextField,
        adapters: list,
        mode_override: Optional[str] = None,
        allow_cloud_fallback: bool = False,
    ):
        """Send a chat message and get AI response."""
        query = input_field.value.strip() if input_field.value else ""
        if not query:
            return
        
        # Clear input
        input_field.value = ""
        self.page.update()
        
        # Add user message to chat
        user_msg = {"role": "user", "content": query}
        if not hasattr(self, 'chat_messages'):
            self.chat_messages = []
        self.chat_messages.append(user_msg)
        
        # Add to UI
        if hasattr(self, 'chat_messages_list'):
            # Remove welcome message if it's first message
            if len(self.chat_messages) == 1 and self.chat_messages_list.controls:
                self.chat_messages_list.controls.clear()
            
            self.chat_messages_list.controls.append(
                self._create_chat_bubble("user", query)
            )
            
            # Add loading indicator
            loading_bubble = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=20, color="white"),
                            width=36,
                            height=36,
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            border_radius=18,
                            alignment=ft.alignment.center,
                        ),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.ProgressRing(width=16, height=16, stroke_width=2, color=LightTheme.ACCENT_PRIMARY),
                                    ft.Text("Thinking...", size=14, color=LightTheme.TEXT_MUTED, italic=True),
                                ],
                                spacing=12,
                            ),
                            padding=16,
                            bgcolor=LightTheme.BG_ELEVATED,
                            border_radius=16,
                        ),
                        ft.Container(width=40),
                    ],
                    spacing=12,
                ),
                margin=ft.margin.only(right=60),
            )
            self.chat_messages_list.controls.append(loading_bubble)
            self.page.update()
        
        # Determine if we have adapters to use
        has_adapters = adapters and len(adapters) > 0
        
        # Use selected adapter or first one (if available)
        adapter = None
        if has_adapters:
            if self.selected_adapter_id:
                adapter = next((a for a in adapters if a.get("adapter_id") == self.selected_adapter_id), adapters[0])
            else:
                adapter = adapters[0]
        
        inference_mode = mode_override or self.inference_mode  # Capture current mode
        
        def run_inference():
            try:
                response_text = None
                profile_name = self._ensure_private_model_profile().name
                doc_name = profile_name
                source_items: List[Dict[str, Any]] = []

                # PRIORITY 1: Active Private Model profile
                if inference_mode == "local":
                    try:
                        result = self._query_private_model(query)
                        response_text = result.get("answer", "")
                        doc_name = result.get("document") or profile_name
                        source_items = result.get("sources", [])
                    except Exception as private_err:
                        logger.warning(f"Private model chat error: {private_err}")
                        response_text = None

                # PRIORITY 2: Legacy LocalAgent fallback for older indexes
                if response_text is None and inference_mode == "local":
                    try:
                        from advanced_vault.mcp_server.agent import get_agent

                        agent = get_agent(vault_path=str(self.vault_path))
                        result = agent.query(question=query, temperature=0.4)

                        if result.get("error") is None or result.get("answer"):
                            response_text = result.get("answer", "")
                            sources = result.get("sources", [])
                            if sources:
                                source_items = sources
                                doc_name = ", ".join((s.get("document") or "Indexed Documents") for s in sources[:3])
                            elif result.get("rag_used"):
                                doc_name = "Legacy Indexed Documents"
                            else:
                                doc_name = result.get("model_used") or profile_name
                    except Exception as agent_err:
                        logger.warning(f"Local agent error: {agent_err}")
                        response_text = None

                # PRIORITY 3: Local MLX base model fallback
                if response_text is None and inference_mode == "local":
                    try:
                        from local_inference import get_local_engine
                        engine = get_local_engine()
                        if not engine.model:
                            engine.load_model()
                        if adapter:
                            response_text = engine.query(
                                query=query,
                                adapter_id=adapter["adapter_id"],
                                encryption_key_hex=adapter.get("encryption_key")
                            )
                        else:
                            response_text = engine.query_base(query=query)
                        doc_name = adapter["name"] if adapter else profile_name
                    except ImportError:
                        logger.debug("Local inference engine not available")
                    except Exception as local_err:
                        logger.debug(f"Local inference error: {local_err}")

                # PRIORITY 4: Cloud inference (opt-in fallback)
                if response_text is None:
                    if allow_cloud_fallback and adapter:
                        response = self.training_manager.inference_with_adapter(
                            adapter_id=adapter["adapter_id"],
                            query=query,
                            encryption_key_hex=adapter["encryption_key"]
                        )
                        response_text = response.get("response", "I couldn't generate a response.") if response else "No response received."
                        doc_name = adapter["name"]
                    elif allow_cloud_fallback:
                        response_text = (
                            "Welcome to Enclave — your privacy-first AI agent.\n\n"
                            "To get started:\n"
                            "1. **Drop a PDF** on the home screen to index it\n"
                            "2. **Ask questions** — I'll answer from your indexed documents\n"
                            "3. **Connect Claude Desktop** for seamless MCP integration\n\n"
                            "Your data stays local. External AIs never see your raw documents."
                        )
                    else:
                        response_text = (
                            "Your local Private Language Model is unavailable right now.\n\n"
                            "Try again after local model setup finishes."
                        )
                        doc_name = profile_name
                
                # Add AI response
                ai_msg = {
                    "role": "assistant",
                    "content": response_text,
                    "document": doc_name,
                    "sources": source_items,
                }
                self.chat_messages.append(ai_msg)
                self._save_chat_history_to_file()
                
                # Save to question history too
                self._save_question_history(query, doc_name, response_text, mode=inference_mode)
                
                def update_ui():
                    # Remove loading bubble
                    if hasattr(self, 'chat_messages_list') and self.chat_messages_list.controls:
                        self.chat_messages_list.controls.pop()
                    
                    # Add response bubble
                    self.chat_messages_list.controls.append(
                        self._create_chat_bubble("assistant", response_text, doc_name, source_items)
                    )
                    self.page.update()
                
                update_ui()
                
            except Exception as ex:
                logger.error(f"Chat inference error: {ex}")
                ex_str = str(ex)
                if "session expired" in ex_str.lower() or "401" in ex_str:
                    error_msg = (
                        "Your cloud session expired. Please sign in again in Enclave "
                        "to continue cloud inference."
                    )
                else:
                    error_msg = f"Sorry, I encountered an error: {ex_str}"
                
                def show_error():
                    if hasattr(self, 'chat_messages_list') and self.chat_messages_list.controls:
                        self.chat_messages_list.controls.pop()
                    
                    self.chat_messages_list.controls.append(
                        self._create_chat_bubble("assistant", error_msg)
                    )
                    self.page.update()
                
                show_error()
        
        # Run inference in background
        thread = threading.Thread(target=run_inference, daemon=True)
        thread.start()
    
    def _save_question_history(self, question: str, document: str, response: str, mode: str = "cloud"):
        """Save a question to history."""
        import json
        try:
            history = []
            if self.question_history_path.exists():
                with open(self.question_history_path, 'r') as f:
                    history = json.load(f)
            
            # Add new entry
            history.insert(0, {
                "question": question,
                "document": document,
                "response": response[:200] + "..." if len(response) > 200 else response,
                "mode": mode,
                "timestamp": datetime.now().isoformat(),
            })
            
            # Keep only last 20 questions
            history = history[:20]
            
            with open(self.question_history_path, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save question history: {e}")
    
    def _get_recent_questions(self, limit: int = 5) -> List[Dict]:
        """Get recent questions from history."""
        import json
        try:
            if self.question_history_path.exists():
                with open(self.question_history_path, 'r') as f:
                    history = json.load(f)
                    return history[:limit]
        except Exception as e:
            logger.debug(f"Failed to load question history: {e}")
        return []
    
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
                    except (ValueError, TypeError):
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
        self._ensure_private_model_profile()

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
        if not self.session_data and self.local_first_mode and not self.require_authentication:
            self._show_user_message("Local-first mode is active. There is no cloud session to log out from.", level="info")
            self.show_landing_page()
            return

        # Clear session
        AuthScreen.clear_session()
        self.session_data = None
        self.vault = None

        # Show auth screen
        self.show_auth_screen()
    
    def _prompt_relogin(self, reason: str = "Session expired"):
        """Show a dialog prompting the user to re-login."""
        def do_logout(e):
            dialog.open = False
            self.page.update()
            self.logout()
        
        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_ROUNDED, color=LightTheme.ACCENT_WARNING, size=24),
                ft.Text("Session Expired", size=18, weight=ft.FontWeight.W_600),
            ], spacing=12),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(reason, size=14),
                    ft.Container(height=12),
                    ft.Text(
                        "Your login session has expired. Please log out and log back in to continue.",
                        size=13,
                        color=LightTheme.TEXT_MUTED,
                    ),
                ], spacing=0),
                width=350,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            actions=[
                ft.TextButton("Later", on_click=lambda e: self._close_dialog(dialog)),
                ft.ElevatedButton(
                    "Log Out & Re-Login",
                    icon=ft.Icons.LOGOUT_ROUNDED,
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    on_click=do_logout,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()
    
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
        user_email = self._get_identity_label()

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
                    tooltip=self.tr("ui.add_entry.tooltip"),
                    icon_size=28,
                    icon_color=LightTheme.ACCENT_PRIMARY,
                    items=[
                        ft.PopupMenuItem(
                            text=self.tr("ui.add_secret"),
                            icon=ft.Icons.LOCK_ROUNDED,
                            on_click=lambda e: self.show_add_dialog(e, default_type="secret"),
                        ),
                        ft.PopupMenuItem(
                            text=self.tr("ui.upload_pdf_knowledge"),
                            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                            on_click=lambda e: self._on_upload_click(e),
                        ),
                    ],
                ),
                ft.IconButton(
                    ft.Icons.CREATE_NEW_FOLDER_ROUNDED,
                    tooltip=self.tr("ui.new_folder"),
                    on_click=lambda _: self._show_create_folder_dialog(),
                    icon_size=28,
                    icon_color=LightTheme.ACCENT_PRIMARY,
                ),
                ft.IconButton(
                    ft.Icons.REFRESH_ROUNDED,
                    tooltip=self.tr("ui.refresh"),
                    on_click=lambda _: self.load_secrets(),
                    icon_size=28,
                    icon_color=LightTheme.TEXT_SECONDARY,
                ),
                ft.IconButton(
                    ft.Icons.LOGOUT_ROUNDED,
                    tooltip=self.tr("ui.logout"),
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
            hint_text=self.tr("ui.search_secrets"),
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
                ft.dropdown.Option("all", self.tr("ui.filter.all")),
                ft.dropdown.Option("secret", self.tr("sidebar.secrets")),
                ft.dropdown.Option("knowledge", self.tr("sidebar.knowledge")),
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
            selected_index=-1,  # Start with Home selected
            translate=self.tr,
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
        
        # Add floating chat button for quick access to AI assistant (only on non-chat views)
        # First, clear any existing floating buttons to prevent stacking
        items_to_remove = [o for o in self.page.overlay if isinstance(o, ft.Container) and hasattr(o, 'content') and isinstance(getattr(o, 'content', None), ft.FloatingActionButton)]
        for item in items_to_remove:
            self.page.overlay.remove(item)
        
        floating_chat_button = ft.Container(
            content=ft.FloatingActionButton(
                icon=ft.Icons.AUTO_AWESOME_ROUNDED,
                bgcolor=LightTheme.ACCENT_PRIMARY,
                foreground_color="white",
                tooltip=self.tr("ui.chat_with_ai"),
                on_click=lambda e: self.show_landing_page(),
                mini=False,
            ),
            right=24,
            bottom=24,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )
        
        self.page.overlay.append(floating_chat_button)

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
        """Handle navigation change for simplified 4-item structure."""
        # Update sidebar selection
        self.sidebar.selected_index = index
        sidebar_container = self.sidebar.build()

        # Update sidebar in layout
        layout = self.page.controls[0]  # Get the Row layout
        if layout and isinstance(layout, ft.Row) and len(layout.controls) > 0:
            layout.controls[0] = sidebar_container  # Update sidebar

        # Handle navigation with simplified structure:
        # -1: Workspace
        #  0: Library
        #  1: Workspace (legacy agent callbacks)
        #  2: Security
        if index == -1:  # Workspace
            self.show_landing_page()
        elif index == 0:  # Library
            self.show_my_data_view(active_tab="context")
        elif index == 1:  # Workspace / Agent
            self._show_workspace_view()
        elif index == 2:  # Security
            self.show_settings_hub(active_tab="sheriff")
        # Backward compatibility for legacy nav indices used in older callbacks.
        elif index == 3:  # Activity
            self.show_agent_view(active_tab="activity")
        elif index == 4:  # Statistics
            self.show_settings_hub(active_tab="stats")
        elif index == 5:  # Setup/Settings
            self.show_settings_hub(active_tab="setup")
        elif index == 6:  # LangChain policies
            self.show_settings_hub(active_tab="policies")
        elif index == 7:  # Library
            self.show_my_data_view(active_tab="profiles")
        elif index == 8:  # Permissions
            self.show_agent_view(active_tab="permissions")
        elif index == 9:  # Data Sheriff
            self.show_settings_hub(active_tab="sheriff")

        self.page.update()

    def show_my_data_view(self, active_tab: str = "context"):
        """Simplified library view for context, secrets, and profiles."""
        self.current_view = "my_data"
        self.page.clean()

        # Tab state
        tab_index = {
            "context": 0,
            "knowledge": 0,
            "all": 0,
            "secrets": 1,
            "profiles": 2,
            "library": 2,
        }.get(active_tab, 0)

        def filter_button(label: str, key: str, icon: str) -> ft.Container:
            is_selected = tab_index == {"context": 0, "secrets": 1, "profiles": 2}[key]
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=16, color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY),
                        ft.Text(label, size=12, color=LightTheme.TEXT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY, weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_400),
                    ],
                    spacing=8,
                ),
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                bgcolor=LightTheme.ACCENT_PRIMARY + "10" if is_selected else LightTheme.BG_ELEVATED,
                border_radius=999,
                border=ft.border.all(1, LightTheme.ACCENT_PRIMARY + "25" if is_selected else LightTheme.BORDER_COLOR),
                on_click=lambda e, view=key: self.show_my_data_view(active_tab=view),
            )

        # Build content based on active tab
        content_items = []
        if active_tab in {"context", "knowledge", "all"}:
            content_items = self._build_knowledge_content()
        elif active_tab == "secrets":
            content_items = self._build_secrets_content()
        elif active_tab in {"profiles", "library"}:
            content_items = self._build_library_content()

        # Main content
        main_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text("Library", size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.only(left=32, top=24, bottom=8),
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                filter_button("Context", "context", ft.Icons.FOLDER_ROUNDED),
                                filter_button("Secrets", "secrets", ft.Icons.KEY_ROUNDED),
                                filter_button("Profiles", "profiles", ft.Icons.PSYCHOLOGY_ROUNDED),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        padding=ft.padding.symmetric(horizontal=32),
                    ),
                    ft.Container(
                        content=ft.Column(content_items, scroll=ft.ScrollMode.AUTO, expand=True),
                        padding=ft.padding.symmetric(horizontal=32, vertical=16),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        # Initialize sidebar
        if not hasattr(self, 'sidebar') or self.sidebar is None:
            self.sidebar = ModernSidebar(on_nav_change=self.on_nav_change, selected_index=0)
        else:
            self.sidebar.selected_index = 0
        sidebar_container = self.sidebar.build()

        self.page.add(ft.Row([sidebar_container, main_content], spacing=0, expand=True))
        self.page.update()

    def _build_all_items_content(self) -> list:
        """Build combined list of all vault items."""
        items = []
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            sorted_entries = sorted(all_entries, key=lambda e: e.created_at if e.created_at else datetime.min, reverse=True)

            for entry in sorted_entries[:50]:
                icon = ft.Icons.KEY_ROUNDED if entry.entry_type in [EntryType.SECRET, EntryType.API_KEY, EntryType.PASSWORD] else ft.Icons.DESCRIPTION_ROUNDED
                items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(icon, size=18, color=LightTheme.ACCENT_PRIMARY),
                            ft.Text(entry.service[:40], size=14, color=LightTheme.TEXT_PRIMARY, expand=True),
                            ft.Container(
                                content=ft.Text(entry.entry_type.value if hasattr(entry.entry_type, 'value') else str(entry.entry_type), size=11, color=LightTheme.TEXT_MUTED),
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=LightTheme.BG_HOVER,
                                border_radius=8,
                            ),
                        ], spacing=12),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e, ent=entry: self.view_secret(ent),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading items: {e}")
            items.append(ft.Text("Error loading items", color=LightTheme.TEXT_MUTED))

        if not items:
            items.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.INBOX_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                    ft.Text("No items yet", size=16, color=LightTheme.TEXT_MUTED),
                    ft.Text("Add secrets or documents to get started", size=13, color=LightTheme.TEXT_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=64,
                alignment=ft.alignment.center,
            ))

        return items

    def _build_secrets_content(self) -> list:
        """Build secrets list content."""
        items = []
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            secrets = [e for e in all_entries if e.entry_type in [EntryType.SECRET, EntryType.API_KEY, EntryType.PASSWORD, EntryType.TOKEN, EntryType.CREDENTIAL]]
            sorted_secrets = sorted(secrets, key=lambda e: e.created_at if e.created_at else datetime.min, reverse=True)

            for entry in sorted_secrets[:50]:
                items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.KEY_ROUNDED, size=18, color=LightTheme.ACCENT_WARNING),
                            ft.Text(entry.service[:40], size=14, color=LightTheme.TEXT_PRIMARY, expand=True),
                            ft.Icon(ft.Icons.LOCK_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS),
                        ], spacing=12),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e, ent=entry: self.view_secret(ent),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading secrets: {e}")

        if not items:
            items.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.KEY_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                    ft.Text("No secrets stored", size=16, color=LightTheme.TEXT_MUTED),
                    ft.ElevatedButton("Add Secret", icon=ft.Icons.ADD_ROUNDED, on_click=lambda e: self.show_add_dialog(e, default_type="secret")),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                padding=64,
                alignment=ft.alignment.center,
            ))

        return items

    def _build_knowledge_content(self) -> list:
        """Build knowledge content for the active local Private Model profile."""
        items: List[ft.Control] = []
        try:
            profile = self._ensure_private_model_profile()
            status = self._get_private_model_status()
            documents = self._get_rag_documents()

            items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(f"Profile: {profile.name}", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(
                                profile.description or "This local profile stores encrypted context for private chat.",
                                size=13,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Container(height=12),
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Text(f"{status.get('document_count', 0)} docs", size=12, color=LightTheme.ACCENT_PRIMARY),
                                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                        bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                                        border_radius=999,
                                    ),
                                    ft.Container(
                                        content=ft.Text(f"{status.get('chunk_count', 0)} chunks", size=12, color=LightTheme.ACCENT_SUCCESS),
                                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                        bgcolor=LightTheme.ACCENT_SUCCESS + "10",
                                        border_radius=999,
                                    ),
                                    ft.Container(
                                        content=ft.Text(f"{status.get('adapter_count', 0)} WDVA layers", size=12, color=LightTheme.ACCENT_WARNING),
                                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                        bgcolor=LightTheme.ACCENT_WARNING + "10",
                                        border_radius=999,
                                    ),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                            ft.Container(height=14),
                            ft.Row(
                                [
                                    ft.ElevatedButton("Add Files", icon=ft.Icons.FILE_UPLOAD_ROUNDED, on_click=self._open_private_files_picker, style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white")),
                                    ft.OutlinedButton("Add Folder", icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, on_click=self._open_private_folder_picker, style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY)),
                                    ft.TextButton("Open Chat", icon=ft.Icons.CHAT_ROUNDED, on_click=lambda e: self._open_test_agent_chat(), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                        ],
                        spacing=0,
                    ),
                    padding=24,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_radius=16,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                )
            )
            items.append(ft.Container(height=16))

            for doc in documents[:50]:
                source_name = Path(doc.get("source_path") or doc.get("name", "")).parent.name or "Local import"
                items.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.DESCRIPTION_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                ft.Column(
                                    [
                                        ft.Text(doc.get("name", "Unknown"), size=14, color=LightTheme.TEXT_PRIMARY, weight=ft.FontWeight.W_600, expand=True),
                                        ft.Text(f'{doc.get("chunk_count", 0)} chunks • {source_name}', size=11, color=LightTheme.TEXT_MUTED),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE_ROUNDED,
                                    icon_size=16,
                                    icon_color=LightTheme.TEXT_MUTED,
                                    tooltip="Remove from this profile",
                                    on_click=lambda e, did=doc.get("id"): self._delete_rag_document(did),
                                ),
                            ],
                            spacing=12,
                        ),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=12,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading knowledge: {e}")

        if len(items) <= 2:
            items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.LIGHTBULB_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                            ft.Text("No documents indexed for this profile", size=16, color=LightTheme.TEXT_MUTED),
                            ft.Row(
                                [
                                    ft.ElevatedButton("Add Files", icon=ft.Icons.UPLOAD_ROUNDED, on_click=self._open_private_files_picker),
                                    ft.OutlinedButton("Add Folder", icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, on_click=self._open_private_folder_picker),
                                ],
                                spacing=10,
                                wrap=True,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    padding=64,
                    alignment=ft.alignment.center,
                )
            )

        return items

    def _build_library_content(self) -> list:
        """Build local profile/model library content."""
        items: List[ft.Control] = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Private Model Profiles", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                ft.Text("Each profile has its own encrypted context, model preference, and WDVA layers.", size=13, color=LightTheme.TEXT_SECONDARY),
                            ],
                            spacing=4,
                            expand=True,
                        ),
                        ft.ElevatedButton(
                            "Create Profile",
                            icon=ft.Icons.ADD_ROUNDED,
                            on_click=self._open_create_profile_dialog,
                            style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                        ),
                    ],
                    spacing=12,
                    wrap=True,
                ),
                padding=24,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
            ft.Container(height=16),
        ]

        try:
            for profile in self._get_private_model_profiles():
                session = self.private_model_manager.open_session(profile.name)
                try:
                    status = session.get_status()
                finally:
                    session.close()

                is_active = profile.name == self.active_private_profile_name
                items.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.PSYCHOLOGY_ROUNDED, size=20, color=LightTheme.ACCENT_PRIMARY),
                                        ft.Text(profile.name, size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY, expand=True),
                                        ft.Container(
                                            content=ft.Text("Active" if is_active else "Available", size=11, color=LightTheme.ACCENT_SUCCESS if is_active else LightTheme.TEXT_MUTED),
                                            padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                            bgcolor=(LightTheme.ACCENT_SUCCESS if is_active else LightTheme.BORDER_COLOR) + "12",
                                            border_radius=999,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                ft.Container(height=8),
                                ft.Text(profile.description or "Private local profile", size=13, color=LightTheme.TEXT_SECONDARY),
                                ft.Container(height=12),
                                ft.Row(
                                    [
                                        ft.Text(f"{status.get('document_count', 0)} docs", size=12, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text("•", size=12, color=LightTheme.TEXT_MUTED),
                                        ft.Text(f"{status.get('chunk_count', 0)} chunks", size=12, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text("•", size=12, color=LightTheme.TEXT_MUTED),
                                        ft.Text(f"{len(profile.wdva_adapters)} WDVA", size=12, color=LightTheme.TEXT_PRIMARY),
                                    ],
                                    spacing=8,
                                    wrap=True,
                                ),
                                ft.Container(height=12),
                                ft.Row(
                                    [
                                        ft.Text((profile.model_name or DEFAULT_PRIVATE_MODEL_NAME).split("/")[-1], size=12, color=LightTheme.TEXT_MUTED),
                                        ft.Container(expand=True),
                                        ft.TextButton("Set Active", on_click=lambda e, name=profile.name: self._set_active_private_profile(name), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                        ft.TextButton("Open Chat", on_click=lambda e, name=profile.name: self._set_active_private_profile(name, refresh=False) or self._open_test_agent_chat(), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                    ],
                                    spacing=8,
                                    wrap=True,
                                ),
                            ],
                            spacing=0,
                        ),
                        padding=20,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.ACCENT_PRIMARY + "25" if is_active else LightTheme.BORDER_COLOR),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading private model library: {e}")

        return items

    def show_agent_view(self, active_tab: str = "chat"):
        """Combined view for Chat + Permissions + Activity with tabs."""
        if active_tab == "chat":
            self._show_workspace_view()
            return

        self.current_view = "agent"
        self.page.clean()

        tab_index = {"chat": 0, "connections": 1, "permissions": 2, "activity": 3}.get(active_tab, 0)

        def on_tab_change(e):
            tab_names = ["chat", "connections", "permissions", "activity"]
            self.show_agent_view(active_tab=tab_names[e.control.selected_index])

        tabs = ft.Tabs(
            selected_index=tab_index,
            animation_duration=200,
            tabs=[
                ft.Tab(text="Chat", icon=ft.Icons.CHAT_ROUNDED),
                ft.Tab(text="Connections", icon=ft.Icons.CABLE_ROUNDED),
                ft.Tab(text="Permissions", icon=ft.Icons.SHIELD_ROUNDED),
                ft.Tab(text="Activity", icon=ft.Icons.HISTORY_ROUNDED),
            ],
            on_change=on_tab_change,
            expand=True,
        )

        content_items = []
        if active_tab == "chat":
            content_items = self._build_chat_content()
        elif active_tab == "connections":
            content_items = self._build_connections_content()
        elif active_tab == "permissions":
            content_items = self._build_permissions_content()
        elif active_tab == "activity":
            content_items = self._build_activity_content()

        main_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text("Private Model Agent", size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.only(left=32, top=24, bottom=8),
                    ),
                    ft.Container(content=tabs, padding=ft.padding.symmetric(horizontal=32), height=48),
                    ft.Container(
                        content=ft.Column(content_items, scroll=ft.ScrollMode.AUTO, expand=True),
                        padding=ft.padding.symmetric(horizontal=32, vertical=16),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        if not hasattr(self, 'sidebar') or self.sidebar is None:
            self.sidebar = ModernSidebar(on_nav_change=self.on_nav_change, selected_index=1)
        else:
            self.sidebar.selected_index = 1
        sidebar_container = self.sidebar.build()

        self.page.add(ft.Row([sidebar_container, main_content], spacing=0, expand=True))
        self.page.update()

    def _build_chat_content(self) -> list:
        """Build a profile-aware chat entry surface."""
        profile = self._ensure_private_model_profile()
        status = self._get_private_model_status()
        chat_input = ft.TextField(
            hint_text="Ask your agent a question...",
            expand=True,
            border_radius=12,
            on_submit=lambda e: self._send_chat_from_agent_view(e, chat_input),
        )

        return [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Talk to Your Private Model", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text("Chat against encrypted local context, with WDVA layers when attached.", size=13, color=LightTheme.TEXT_SECONDARY),
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                ft.Container(
                                    content=ft.Text(profile.name, size=12, color=LightTheme.ACCENT_PRIMARY),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                                    border_radius=999,
                                ),
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                        ft.Container(height=16),
                        ft.Row(
                            [
                                ft.Container(
                                    content=ft.Text(f"{status.get('document_count', 0)} docs", size=12, color=LightTheme.ACCENT_PRIMARY),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                                    border_radius=999,
                                ),
                                ft.Container(
                                    content=ft.Text(f"{status.get('chunk_count', 0)} chunks", size=12, color=LightTheme.ACCENT_SUCCESS),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor=LightTheme.ACCENT_SUCCESS + "10",
                                    border_radius=999,
                                ),
                                ft.Container(
                                    content=ft.Text(f"{status.get('adapter_count', 0)} WDVA", size=12, color=LightTheme.ACCENT_WARNING),
                                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                    bgcolor=LightTheme.ACCENT_WARNING + "10",
                                    border_radius=999,
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        ft.Container(height=16),
                        ft.Row(
                            [
                                chat_input,
                                ft.IconButton(
                                    ft.Icons.SEND_ROUNDED,
                                    icon_color=LightTheme.ACCENT_PRIMARY,
                                    on_click=lambda e: self._send_chat_from_agent_view(e, chat_input),
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Container(height=12),
                        ft.Row(
                            [
                                ft.TextButton("Add Files", icon=ft.Icons.FILE_UPLOAD_ROUNDED, on_click=self._open_private_files_picker, style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                ft.TextButton("Add Folder", icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED, on_click=self._open_private_folder_picker, style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                ft.TextButton("Open Full Workspace", icon=ft.Icons.OPEN_IN_NEW_ROUNDED, on_click=lambda e: self._open_test_agent_chat(), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                            ],
                            spacing=8,
                            wrap=True,
                        ),
                    ],
                    spacing=0,
                ),
                padding=24,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=12,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
        ]

    def _build_connections_content(self) -> list:
        """Build MCP connections panel for one-click setup."""
        mcp_status = {}
        try:
            if hasattr(self, 'mcp_setup') and self.mcp_setup:
                mcp_status = self.mcp_setup.get_setup_status()
        except Exception:
            mcp_status = {}

        claude_configured = bool(mcp_status.get("claude_mcp_configured", mcp_status.get("mcp_configured", False)))
        cursor_configured = bool(mcp_status.get("cursor_mcp_configured", False))
        chatgpt_installed = bool(mcp_status.get("chatgpt_installed", False))
        chatgpt_supported = bool(mcp_status.get("chatgpt_local_mcp_supported", False))
        chatgpt_support_message = mcp_status.get(
            "chatgpt_support_message",
            "Local MCP setup for ChatGPT is not supported.",
        )

        def create_client_card(
            name,
            icon,
            color,
            configure_func,
            is_connected=False,
            is_available=True,
            status_override: Optional[str] = None,
            tooltip: Optional[str] = None,
        ):
            if status_override is not None:
                status_text = status_override
                status_color = LightTheme.TEXT_MUTED
                border_color = LightTheme.BORDER_COLOR
            elif is_connected:
                status_text = "Connected"
                status_color = LightTheme.ACCENT_SUCCESS
                border_color = LightTheme.ACCENT_SUCCESS
            elif is_available:
                status_text = "Configure"
                status_color = LightTheme.ACCENT_PRIMARY
                border_color = LightTheme.BORDER_COLOR
            else:
                status_text = "Not detected"
                status_color = LightTheme.TEXT_MUTED
                border_color = LightTheme.BORDER_COLOR

            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=32, color=color if not is_connected else LightTheme.ACCENT_SUCCESS),
                    ft.Text(name, size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                    ft.Container(
                        content=ft.Text(status_text, size=11, color=status_color),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=(status_color if status_color != LightTheme.TEXT_MUTED else LightTheme.BORDER_COLOR) + "15",
                        border_radius=8,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=24,
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=12,
                border=ft.border.all(1, border_color),
                on_click=configure_func if (not is_connected and is_available and status_override is None) else None,
                tooltip=tooltip,
                width=150,
            )

        return [
            ft.Text("Connect Your AI Assistants", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("One-click setup for popular AI clients via MCP", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
            ft.Row([
                create_client_card(
                    "Claude",
                    ft.Icons.SMART_TOY_ROUNDED,
                    "#D97706",
                    lambda e: self._configure_claude_mcp(),
                    is_connected=claude_configured,
                    is_available=bool(mcp_status.get("claude_installed", False)),
                ),
                create_client_card(
                    "Cursor",
                    ft.Icons.EDIT_ROUNDED,
                    "#000000",
                    lambda e: self._configure_cursor_mcp(),
                    is_connected=cursor_configured,
                    is_available=bool(mcp_status.get("cursor_installed", False)),
                ),
                create_client_card(
                    "ChatGPT",
                    ft.Icons.CHAT_ROUNDED,
                    "#10A37F",
                    lambda e: self._configure_chatgpt_mcp(),
                    is_connected=False,
                    is_available=chatgpt_installed,
                    status_override=("Unsupported" if chatgpt_installed and not chatgpt_supported else ("Not detected" if not chatgpt_installed else None)),
                    tooltip=chatgpt_support_message if chatgpt_installed else "ChatGPT desktop not detected",
                ),
                create_client_card("VS Code", ft.Icons.CODE_ROUNDED, "#007ACC", lambda e: self._configure_vscode_mcp()),
                create_client_card("Other", ft.Icons.MORE_HORIZ_ROUNDED, LightTheme.TEXT_MUTED, lambda e: self._copy_mcp_json()),
            ], spacing=16, wrap=True),
            ft.Container(height=24),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CONTENT_COPY_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                    ft.Text("Copy MCP Config JSON", size=13, color=LightTheme.ACCENT_PRIMARY),
                ], spacing=8),
                padding=ft.padding.symmetric(horizontal=16, vertical=10),
                bgcolor=LightTheme.ACCENT_PRIMARY + "10",
                border_radius=8,
                on_click=lambda e: self._copy_mcp_json(),
            ),
        ]

    def _build_permissions_content(self) -> list:
        """Build permissions management content."""
        items = []
        try:
            from advanced_vault.mcp_server.consent import ConsentManager
            cm = ConsentManager(vault_path=str(self.vault_path))
            agents = cm.list_agents()

            for agent_id in agents:
                perm = cm.get_permission(agent_id)
                items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                            ft.Text(agent_id[:30], size=14, color=LightTheme.TEXT_PRIMARY, expand=True),
                            ft.Container(
                                content=ft.Text("Active" if perm else "Configured", size=11, color=LightTheme.ACCENT_SUCCESS),
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                bgcolor=LightTheme.ACCENT_SUCCESS + "15",
                                border_radius=8,
                            ),
                        ], spacing=12),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading permissions: {e}")

        if not items:
            items.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.SHIELD_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                    ft.Text("No agents registered", size=16, color=LightTheme.TEXT_MUTED),
                    ft.Text("Connect an AI assistant to manage its permissions", size=13, color=LightTheme.TEXT_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=64,
                alignment=ft.alignment.center,
            ))

        return [
            ft.Text("Agent Permissions", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Control what each AI agent can access", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
        ] + items

    def _build_activity_content(self) -> list:
        """Build activity log content."""
        items = []
        try:
            activity_logger = ActivityLogger(vault_path=str(self.vault_path))
            activities = activity_logger.get_recent_activity(limit=20)

            for activity in activities:
                timestamp = activity.get('timestamp', '')
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    time_str = ""

                granted = activity.get('granted', False)
                tool_name = activity.get('tool_name', 'unknown').replace('vault_', '').replace('agent_', '').replace('_', ' ').title()
                app_name = activity.get('app_name', 'Unknown')

                items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(
                                ft.Icons.CHECK_CIRCLE_ROUNDED if granted else ft.Icons.CANCEL_ROUNDED,
                                size=18, color=LightTheme.ACCENT_SUCCESS if granted else LightTheme.ACCENT_ERROR,
                            ),
                            ft.Text(f"{app_name}: {tool_name}", size=14, color=LightTheme.TEXT_PRIMARY, expand=True),
                            ft.Text(time_str, size=11, color=LightTheme.TEXT_MUTED),
                        ], spacing=12),
                        padding=ft.padding.symmetric(horizontal=16, vertical=12),
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    )
                )
        except Exception as e:
            logger.warning(f"Error loading activity: {e}")

        if not items:
            items.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.HISTORY_ROUNDED, size=48, color=LightTheme.TEXT_MUTED),
                    ft.Text("No activity yet", size=16, color=LightTheme.TEXT_MUTED),
                    ft.Text("Agent access requests will appear here", size=13, color=LightTheme.TEXT_MUTED),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=64,
                alignment=ft.alignment.center,
            ))

        return [
            ft.Text("Access Activity", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Log of all agent access requests", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
        ] + items

    def show_settings_hub(self, active_tab: str = "sheriff"):
        """Simplified settings hub for security, integrations, and advanced tools."""
        self.current_view = "settings_hub"
        self.page.clean()

        normalized_tab = {
            "sheriff": "security",
            "setup": "advanced",
            "training": "advanced",
            "stats": "advanced",
            "policies": "advanced",
            "connections": "integrations",
        }.get(active_tab, active_tab if active_tab in {"security", "integrations", "advanced"} else "security")

        selected_index = {"security": 0, "integrations": 1, "advanced": 2}[normalized_tab]

        def filter_button(label: str, key: str, icon: str) -> ft.Container:
            is_selected = normalized_tab == key
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=16, color=LightTheme.ACCENT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY),
                        ft.Text(label, size=12, color=LightTheme.TEXT_PRIMARY if is_selected else LightTheme.TEXT_SECONDARY, weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.W_400),
                    ],
                    spacing=8,
                ),
                padding=ft.padding.symmetric(horizontal=14, vertical=10),
                bgcolor=LightTheme.ACCENT_PRIMARY + "10" if is_selected else LightTheme.BG_ELEVATED,
                border_radius=999,
                border=ft.border.all(1, LightTheme.ACCENT_PRIMARY + "25" if is_selected else LightTheme.BORDER_COLOR),
                on_click=lambda e, tab_key=key: self.show_settings_hub(active_tab=tab_key),
            )

        content_items = []
        if normalized_tab == "security":
            content_items = self._build_sheriff_content()
        elif normalized_tab == "integrations":
            content_items = self._build_connections_content()
        else:
            content_items = [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Advanced Tools", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Text("Legacy configuration, queue management, and policy editors live here when you need them.", size=13, color=LightTheme.TEXT_SECONDARY),
                            ft.Container(height=16),
                            ft.Row(
                                [
                                    ft.ElevatedButton("System Setup", icon=ft.Icons.SETTINGS_ROUNDED, on_click=lambda e: self.show_settings(), style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white")),
                                    ft.OutlinedButton("Training Queue", icon=ft.Icons.PSYCHOLOGY_ROUNDED, on_click=lambda e: self.show_training_view(), style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY)),
                                    ft.OutlinedButton("Policies", icon=ft.Icons.SECURITY_ROUNDED, on_click=lambda e: self.show_langchain_policies(), style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY)),
                                    ft.OutlinedButton("Activity Log", icon=ft.Icons.HISTORY_ROUNDED, on_click=lambda e: self.show_activity_view(), style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY)),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                        ],
                        spacing=0,
                    ),
                    padding=24,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_radius=16,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                )
            ]

        main_content = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Text("Security & Integrations", size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.only(left=32, top=24, bottom=8),
                    ),
                    ft.Container(
                        content=ft.Row(
                            [
                                filter_button("Security", "security", ft.Icons.GPP_GOOD_ROUNDED),
                                filter_button("Integrations", "integrations", ft.Icons.CABLE_ROUNDED),
                                filter_button("Advanced", "advanced", ft.Icons.TUNE_ROUNDED),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        padding=ft.padding.symmetric(horizontal=32),
                    ),
                    ft.Container(
                        content=ft.Column(content_items, scroll=ft.ScrollMode.AUTO, expand=True),
                        padding=ft.padding.symmetric(horizontal=32, vertical=16),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            expand=True,
            bgcolor=LightTheme.BG_PRIMARY,
        )

        if not hasattr(self, 'sidebar') or self.sidebar is None:
            self.sidebar = ModernSidebar(on_nav_change=self.on_nav_change, selected_index=2)
        else:
            self.sidebar.selected_index = 2
        sidebar_container = self.sidebar.build()

        self.page.add(ft.Row([sidebar_container, main_content], spacing=0, expand=True))
        self.page.update()

    def _build_setup_content(self) -> list:
        """Build setup/configuration content."""
        return [
            ft.Text("Configuration", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Manage vault settings and components", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
            ft.ElevatedButton(
                "Open Data Sheriff",
                icon=ft.Icons.GPP_GOOD_ROUNDED,
                on_click=lambda e: self.show_settings_hub(active_tab="sheriff"),
                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_SUCCESS, color="white"),
            ),
            ft.ElevatedButton(
                "Open Full Settings",
                icon=ft.Icons.SETTINGS_ROUNDED,
                on_click=lambda e: self.show_settings(),
                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
            ),
        ]

    def _load_sheriff_scan_summary(self) -> None:
        """Load cached sheriff scan summary from local metadata."""
        try:
            if not self._sheriff_summary_path.exists():
                self._sheriff_last_summary = None
                return
            with open(self._sheriff_summary_path, "r", encoding="utf-8") as f:
                self._sheriff_last_summary = json.load(f)
        except Exception as e:
            logger.debug(f"Could not load sheriff summary cache: {e}")
            self._sheriff_last_summary = None

    def _save_sheriff_scan_summary(self) -> None:
        """Persist last sheriff scan summary for landing wizard continuity."""
        try:
            if self._sheriff_last_summary is None:
                return
            self._sheriff_summary_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._sheriff_summary_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._sheriff_last_summary, f, indent=2)
            tmp_path.replace(self._sheriff_summary_path)
        except Exception as e:
            logger.debug(f"Could not persist sheriff summary cache: {e}")

    def _parse_sheriff_scan_paths(self) -> List[str]:
        """Parse comma/newline separated scan roots from UI field."""
        raw = (self._sheriff_scan_paths_text or "").strip()
        if not raw:
            return [str(Path.home() / "Documents")]

        chunks = raw.replace("\n", ",").split(",")
        parsed = [str(Path(chunk.strip()).expanduser()) for chunk in chunks if chunk.strip()]
        return parsed or [str(Path.home() / "Documents")]

    def _start_sheriff_scan(self) -> None:
        """Run risk scan in background and refresh Sheriff panel on completion."""
        if self._sheriff_scan_in_progress:
            return

        paths = self._parse_sheriff_scan_paths()
        max_files = max(1, int(self._sheriff_max_files or 2000))
        self._sheriff_scan_in_progress = True
        self._sheriff_last_error = None
        self._sheriff_last_action_note = (
            f"Risk scan started at {datetime.now().strftime('%H:%M:%S')} "
            f"for {len(paths)} root(s), max {max_files} files."
        )
        self._show_user_message("Sheriff scan started...", level="info")
        self._refresh_sheriff_views()

        def worker():
            try:
                summary = self.sheriff_core.scan_risk(paths=paths, max_files=max_files)
                self._sheriff_last_summary = summary.model_dump(mode="json")
                self._save_sheriff_scan_summary()
                self._sheriff_last_error = None
                self._sheriff_last_action_note = (
                    f"Risk scan complete at {datetime.now().strftime('%H:%M:%S')}: "
                    f"{summary.critical_count} critical, {summary.sensitive_count} sensitive."
                )
                self._show_user_message(
                    f"Sheriff scan complete: {summary.critical_count} critical, {summary.sensitive_count} sensitive.",
                    level="success",
                )
            except Exception as ex:
                logger.error(f"Sheriff scan failed: {ex}")
                self._sheriff_last_error = str(ex)
                self._sheriff_last_action_note = f"Risk scan failed at {datetime.now().strftime('%H:%M:%S')}: {ex}"
                self._show_user_message(f"Sheriff scan failed: {ex}", level="error")
            finally:
                self._sheriff_scan_in_progress = False
                self._refresh_sheriff_views()

        threading.Thread(target=worker, daemon=True).start()

    def _protect_sheriff_recommended(self) -> None:
        """Protect top-risk findings with consent barrier rules."""
        summary = self._sheriff_last_summary or {}
        findings = summary.get("findings", [])
        candidate_paths: List[str] = []

        for finding in findings:
            label = finding.get("label")
            if label in {"CRITICAL", "SENSITIVE"} and finding.get("path"):
                candidate_paths.append(str(finding["path"]))
            if len(candidate_paths) >= 25:
                break

        if not candidate_paths:
            candidate_paths = self._parse_sheriff_scan_paths()

        unique_paths: List[str] = []
        seen = set()
        for path in candidate_paths:
            if path not in seen:
                unique_paths.append(path)
                seen.add(path)

        if not unique_paths:
            self._show_user_message("No paths selected for protection.", level="info")
            return

        self._sheriff_last_action_note = (
            f"Applying protection rules at {datetime.now().strftime('%H:%M:%S')} "
            f"for {len(unique_paths)} path(s)."
        )
        self._show_user_message("Applying protection rules...", level="info")
        try:
            rules = self.sheriff_core.protect_now(paths=unique_paths)
            self._sheriff_last_action_note = (
                f"Protection complete at {datetime.now().strftime('%H:%M:%S')}: "
                f"{len(rules)} rule(s) active."
            )
            self._show_user_message(f"Protected {len(rules)} path(s) with consent barrier.", level="success")
        except Exception as ex:
            logger.error(f"Failed to enable sheriff protection: {ex}")
            self._sheriff_last_action_note = f"Protection failed at {datetime.now().strftime('%H:%M:%S')}: {ex}"
            self._show_user_message(f"Protection failed: {ex}", level="error")

        self._refresh_sheriff_views()

    def _revoke_sheriff_lease(self, lease_id: str) -> None:
        """Revoke one active lease and refresh panel."""
        ok = self.sheriff_core.revoke_lease(lease_id=lease_id, actor="user")
        if ok:
            self._show_user_message(f"Lease revoked: {lease_id[:8]}...", level="success")
        else:
            self._show_user_message("Lease not found or already revoked.", level="info")
        if self.current_view == "settings_hub":
            self.show_settings_hub(active_tab="sheriff")

    def _build_sheriff_content(self) -> list:
        """Build Data Sheriff control panel."""
        enforcement = self.sheriff_core.enforcement_status()
        hardening_alerts = self.sheriff_core.hardening_report()
        active_leases = list(self.sheriff_core.leases.list_active().values())
        shared_status = self._update_module_status_snapshots()
        recent_activity = self.enclave_runtime.list_events(limit=12)
        rules_count = len(self.sheriff_core.policy.list_rules())
        summary = self._sheriff_last_summary or {}
        posture = self._get_sheriff_posture()
        kill_switch = self.enclave_runtime.get_kill_switch()
        wallet_snapshot = shared_status.get("wallet", {}).get("details", {})
        wallet_envelopes = self.wallet_service.list_envelopes()
        pending_requests = self.wallet_service.list_pending_requests()
        wallet_transactions = self.wallet_service.get_transactions()

        critical_count = int(summary.get("critical_count", 0))
        sensitive_count = int(summary.get("sensitive_count", 0))

        def update_paths(e):
            self._sheriff_scan_paths_text = e.control.value

        def update_max_files(e):
            try:
                self._sheriff_max_files = max(1, int((e.control.value or "2000").strip()))
            except Exception:
                pass

        def toggle_advanced(_):
            self._sheriff_show_advanced = not self._sheriff_show_advanced
            self.show_settings_hub(active_tab="sheriff")

        status_color = LightTheme.ACCENT_SUCCESS if enforcement.get("enabled") else LightTheme.ACCENT_WARNING
        findings_controls: List[ft.Control] = []
        for finding in summary.get("findings", [])[:12]:
            label = finding.get("label", "NORMAL")
            if label == "CRITICAL":
                chip_color = LightTheme.ACCENT_ERROR
            elif label == "SENSITIVE":
                chip_color = LightTheme.ACCENT_WARNING
            else:
                chip_color = LightTheme.TEXT_MUTED

            findings_controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(label, size=10, color="white"),
                                bgcolor=chip_color,
                                border_radius=12,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            ),
                            ft.Text(str(finding.get("path", "")), size=12, color=LightTheme.TEXT_PRIMARY, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(finding.get("recommendation", ""), size=11, color=LightTheme.TEXT_SECONDARY),
                        ],
                        spacing=10,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                )
            )

        lease_controls: List[ft.Control] = []
        for lease in active_leases[:8]:
            lease_controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.TIMER_ROUNDED, size=16, color=LightTheme.ACCENT_PRIMARY),
                            ft.Text(str(lease.subject_app), size=12, color=LightTheme.TEXT_PRIMARY, width=120),
                            ft.Text(str(lease.resource_scope), size=11, color=LightTheme.TEXT_SECONDARY, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(str(lease.expires_at), size=11, color=LightTheme.TEXT_MUTED, width=160, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.IconButton(
                                icon=ft.Icons.CANCEL_ROUNDED,
                                icon_color=LightTheme.ACCENT_ERROR,
                                tooltip="Revoke lease",
                                on_click=lambda e, lease_id=lease.lease_id: self._revoke_sheriff_lease(lease_id),
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                )
            )

        audit_controls: List[ft.Control] = []
        for event in recent_activity:
            decision = str(event.get("decision", ""))
            if decision == "DENY":
                icon = ft.Icons.BLOCK_ROUNDED
                icon_color = LightTheme.ACCENT_ERROR
            elif decision in {"ALLOW", "ALLOW_WITH_LEASE", "APPROVED"}:
                icon = ft.Icons.CHECK_CIRCLE_ROUNDED
                icon_color = LightTheme.ACCENT_SUCCESS
            elif decision == "PENDING":
                icon = ft.Icons.SCHEDULE_ROUNDED
                icon_color = LightTheme.ACCENT_WARNING
            else:
                icon = ft.Icons.HELP_OUTLINE_ROUNDED
                icon_color = LightTheme.ACCENT_WARNING

            audit_controls.append(
                ft.Row(
                    [
                        ft.Icon(icon, size=15, color=icon_color),
                        ft.Text(str(event.get("subject", "unknown")), size=12, color=LightTheme.TEXT_PRIMARY, width=110, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(str(event.get("module", "")), size=11, color=LightTheme.ACCENT_PRIMARY, width=80, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(str(event.get("tool", "")), size=11, color=LightTheme.TEXT_SECONDARY, width=160, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(
                            str(event.get("summary") or event.get("resource", "")),
                            size=11,
                            color=LightTheme.TEXT_MUTED,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=8,
                )
            )

        hardening_controls: List[ft.Control] = []
        for alert in hardening_alerts[:8]:
            severity = str(alert.get("severity", "info"))
            if severity in {"critical", "high"}:
                color = LightTheme.ACCENT_ERROR
                icon = ft.Icons.WARNING_ROUNDED
            elif severity == "warning":
                color = LightTheme.ACCENT_WARNING
                icon = ft.Icons.INFO_ROUNDED
            else:
                color = LightTheme.TEXT_MUTED
                icon = ft.Icons.CHECK_CIRCLE_ROUNDED

            message = str(alert.get("message", ""))
            path = str(alert.get("path", ""))
            hardening_controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(icon, size=15, color=color),
                                    ft.Text(message, size=12, color=LightTheme.TEXT_PRIMARY, expand=True),
                                ],
                                spacing=8,
                            ),
                            ft.Text(path, size=11, color=LightTheme.TEXT_MUTED) if path else ft.Container(),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                )
            )

        pending_request_controls: List[ft.Control] = []
        for request in pending_requests[:8]:
            pending_request_controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.SCHEDULE_ROUNDED, size=16, color=LightTheme.ACCENT_WARNING),
                            ft.Text(request.merchant, size=12, color=LightTheme.TEXT_PRIMARY, width=150, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"${request.amount:.2f}", size=12, color=LightTheme.TEXT_SECONDARY, width=90),
                            ft.Text(request.agent_id, size=11, color=LightTheme.TEXT_MUTED, width=120, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Container(expand=True),
                            ft.TextButton(
                                "Approve",
                                icon=ft.Icons.CHECK_ROUNDED,
                                on_click=lambda e, request_id=request.request_id: self._approve_wallet_request(request_id),
                                style=ft.ButtonStyle(color=LightTheme.ACCENT_SUCCESS),
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                )
            )

        advanced_controls: List[ft.Control] = []
        if self._sheriff_show_advanced:
            advanced_controls.extend(
                [
                    ft.Divider(height=14, color=LightTheme.BORDER_COLOR),
                    ft.Text("Advanced scan options", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                    ft.TextField(
                        label="Scan roots (comma or newline separated)",
                        value=self._sheriff_scan_paths_text,
                        on_change=update_paths,
                        border_radius=8,
                        bgcolor=LightTheme.BG_ELEVATED,
                        border_color=LightTheme.BORDER_COLOR,
                    ),
                    ft.Row(
                        [
                            ft.TextField(
                                label="Max files",
                                width=140,
                                value=str(self._sheriff_max_files),
                                on_change=update_max_files,
                                border_radius=8,
                                bgcolor=LightTheme.BG_ELEVATED,
                                border_color=LightTheme.BORDER_COLOR,
                            ),
                            ft.ElevatedButton(
                                "Scan Only",
                                icon=ft.Icons.PLAY_CIRCLE_ROUNDED,
                                on_click=lambda e: self._start_sheriff_scan(),
                                disabled=self._sheriff_scan_in_progress or self._sheriff_workflow_in_progress,
                                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                            ),
                            ft.ElevatedButton(
                                "Protect Only",
                                icon=ft.Icons.SHIELD_ROUNDED,
                                on_click=lambda e: self._protect_sheriff_recommended(),
                                disabled=self._sheriff_scan_in_progress or self._sheriff_workflow_in_progress,
                                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_SUCCESS, color="white"),
                            ),
                            ft.ElevatedButton(
                                "Refresh",
                                icon=ft.Icons.REFRESH_ROUNDED,
                                on_click=lambda e: self.show_settings_hub(active_tab="sheriff"),
                                style=ft.ButtonStyle(bgcolor=LightTheme.BG_ELEVATED, color=LightTheme.TEXT_PRIMARY),
                            ),
                        ],
                        spacing=10,
                    ),
                ]
            )

        content: List[ft.Control] = [
            ft.Text("Data Sheriff", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text(
                "Deny-by-default controls for sensitive files, with lease-based consent and audit trail.",
                size=13,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Container(height=8),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            f"Security status: {posture['headline']}",
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=posture["color"],
                        ),
                        ft.Text(
                            f"Is my data secure right now? {posture['security_answer']}",
                            size=12,
                            color=posture["color"],
                        ),
                        ft.Text(posture["detail"], size=12, color=LightTheme.TEXT_SECONDARY),
                        ft.Text(posture.get("enforcement_message", ""), size=11, color=LightTheme.TEXT_MUTED),
                        ft.Text(f"Last action: {self._sheriff_last_action_note}", size=11, color=LightTheme.TEXT_MUTED),
                    ],
                    spacing=4,
                ),
                padding=ft.padding.all(12),
                border=ft.border.all(1, posture["color"] + "40"),
                border_radius=10,
                bgcolor=LightTheme.BG_ELEVATED,
            ),
            ft.Container(height=12),
            ft.Row(
                [
                    self._stat_card("Critical", critical_count, ft.Icons.PRIORITY_HIGH_ROUNDED, LightTheme.ACCENT_ERROR),
                    self._stat_card("Sensitive", sensitive_count, ft.Icons.REPORT_GMAILERRORRED_ROUNDED, LightTheme.ACCENT_WARNING),
                    self._stat_card("Policy Rules", rules_count, ft.Icons.POLICY_ROUNDED, LightTheme.ACCENT_PRIMARY),
                    self._stat_card("Active Leases", len(active_leases), ft.Icons.TIMER_ROUNDED, LightTheme.ACCENT_SUCCESS),
                ],
                spacing=16,
            ),
            ft.Container(height=16),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Icon(
                                    ft.Icons.POWER_SETTINGS_NEW_ROUNDED,
                                    size=18,
                                    color=LightTheme.ACCENT_ERROR if kill_switch.enabled else LightTheme.ACCENT_SUCCESS,
                                ),
                                ft.Text(
                                    "Global Kill Switch",
                                    size=15,
                                    weight=ft.FontWeight.W_600,
                                    color=LightTheme.TEXT_PRIMARY,
                                ),
                                ft.Container(expand=True),
                                ft.ElevatedButton(
                                    "Disable" if kill_switch.enabled else "Enable",
                                    icon=ft.Icons.POWER_SETTINGS_NEW_ROUNDED,
                                    on_click=lambda e: self._set_global_kill_switch(not kill_switch.enabled),
                                    style=ft.ButtonStyle(
                                        bgcolor=LightTheme.ACCENT_ERROR if kill_switch.enabled else LightTheme.ACCENT_SUCCESS,
                                        color="white",
                                    ),
                                ),
                            ],
                            spacing=10,
                        ),
                        ft.Text(
                            "Stops privileged Vault actions and mock Wallet execution from one control-plane state.",
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Text(
                            f"Current state: {'enabled' if kill_switch.enabled else 'disabled'}"
                            + (f" • {kill_switch.reason}" if kill_switch.reason else ""),
                            size=11,
                            color=LightTheme.TEXT_MUTED,
                        ),
                    ],
                    spacing=8,
                ),
                padding=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                border_radius=10,
                bgcolor=LightTheme.BG_ELEVATED,
            ),
            ft.Container(height=12),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Wallet Governance", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                ft.Container(expand=True),
                                ft.Text(
                                    "Mock provider, local ledger, approval queue",
                                    size=11,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                            ],
                            spacing=10,
                        ),
                        ft.Text(
                            "Use this section to demo governed spend decisions without leaving the local Enclave shell.",
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Row(
                            [
                                self._stat_card("Envelopes", wallet_snapshot.get("envelope_count", len(wallet_envelopes)), ft.Icons.ACCOUNT_BALANCE_WALLET_ROUNDED, LightTheme.ACCENT_PRIMARY),
                                self._stat_card("Pending", wallet_snapshot.get("pending_count", len(pending_requests)), ft.Icons.SCHEDULE_ROUNDED, LightTheme.ACCENT_WARNING),
                                self._stat_card("Transactions", wallet_snapshot.get("transaction_count", len(wallet_transactions)), ft.Icons.RECEIPT_LONG_ROUNDED, LightTheme.ACCENT_SUCCESS),
                                self._stat_card("Frozen", "Yes" if wallet_snapshot.get("frozen") else "No", ft.Icons.LOCK_ROUNDED, LightTheme.ACCENT_ERROR if wallet_snapshot.get("frozen") else LightTheme.ACCENT_SUCCESS),
                            ],
                            spacing=16,
                        ),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Create Demo Envelope",
                                    icon=ft.Icons.ADD_CARD_ROUNDED,
                                    on_click=lambda e: (self._ensure_demo_wallet_envelope(), self.show_settings_hub(active_tab="sheriff")),
                                    style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                                ),
                                ft.OutlinedButton(
                                    "Request $19",
                                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                    on_click=lambda e: self._request_demo_wallet_purchase(19.0, "github.com", "Auto-approved demo spend"),
                                    style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                                ),
                                ft.OutlinedButton(
                                    "Request $85",
                                    icon=ft.Icons.HOURGLASS_TOP_ROUNDED,
                                    on_click=lambda e: self._request_demo_wallet_purchase(85.0, "openai.com", "Pending approval demo spend"),
                                    style=ft.ButtonStyle(color=LightTheme.TEXT_PRIMARY),
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                    ],
                    spacing=12,
                ),
                padding=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                border_radius=10,
                bgcolor=LightTheme.BG_ELEVATED,
            ),
            ft.Container(height=16),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Recommended: 1-click Secure", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        ft.Text(
                            "Use this first. It auto-configures supported AI apps, scans files, and enables protection rules.",
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.ElevatedButton(
                            "Secure My Data Now",
                            icon=ft.Icons.SHIELD_ROUNDED,
                            disabled=self._sheriff_workflow_in_progress or self._sheriff_scan_in_progress,
                            on_click=lambda e: self._run_sheriff_secure_now(),
                            style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_SUCCESS, color="white"),
                        ),
                        ft.Text(
                            self._sheriff_workflow_step if self._sheriff_workflow_in_progress else "",
                            size=12,
                            color=LightTheme.TEXT_MUTED,
                        ),
                        ft.TextButton(
                            "Hide advanced options" if self._sheriff_show_advanced else "Show advanced options",
                            icon=ft.Icons.EXPAND_LESS_ROUNDED if self._sheriff_show_advanced else ft.Icons.EXPAND_MORE_ROUNDED,
                            on_click=toggle_advanced,
                        ),
                        *advanced_controls,
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.INFO_ROUNDED, size=16, color=status_color),
                                ft.Text(
                                    f"Enforcement backend: {enforcement.get('backend')} ({enforcement.get('mode')})",
                                    size=12,
                                    color=LightTheme.TEXT_SECONDARY,
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Text(str(enforcement.get("message", "")), size=11, color=LightTheme.TEXT_MUTED),
                        ft.Row(
                            [
                                ft.ProgressRing(width=16, height=16, stroke_width=2, color=LightTheme.ACCENT_PRIMARY)
                                if (self._sheriff_scan_in_progress or self._sheriff_workflow_in_progress)
                                else ft.Container(width=16, height=16),
                                ft.Text(
                                    "Sheriff is working..." if (self._sheriff_scan_in_progress or self._sheriff_workflow_in_progress) else "Sheriff is idle.",
                                    size=11,
                                    color=LightTheme.TEXT_MUTED,
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Text(f"Last scan error: {self._sheriff_last_error}", size=12, color=LightTheme.ACCENT_ERROR) if self._sheriff_last_error else ft.Container(),
                    ],
                    spacing=10,
                ),
                padding=16,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                border_radius=10,
                bgcolor=LightTheme.BG_ELEVATED,
            ),
            ft.Container(height=12),
            ft.Text("Top Risk Findings", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Files are kept in place; only access is gated by policy and leases.", size=12, color=LightTheme.TEXT_SECONDARY),
        ]

        if findings_controls:
            content.extend(findings_controls)
        else:
            content.append(
                ft.Container(
                    content=ft.Text("No scan results yet. Run Scan to generate recommendations.", size=12, color=LightTheme.TEXT_MUTED),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=8,
                    bgcolor=LightTheme.BG_ELEVATED,
                )
            )

        content.extend(
            [
                ft.Container(height=12),
                ft.Text("Hardening Alerts", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ]
        )
        content.extend(hardening_controls or [ft.Text("No hardening alerts.", size=12, color=LightTheme.TEXT_MUTED)])

        content.extend(
            [
                ft.Container(height=12),
                ft.Text("Active Leases", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ]
        )
        content.extend(lease_controls or [ft.Text("No active leases.", size=12, color=LightTheme.TEXT_MUTED)])

        content.extend(
            [
                ft.Container(height=12),
                ft.Text("Pending Wallet Approvals", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ]
        )
        content.extend(pending_request_controls or [ft.Text("No pending wallet approvals.", size=12, color=LightTheme.TEXT_MUTED)])

        content.extend(
            [
                ft.Container(height=12),
                ft.Text("Recent Enclave Activity", size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ]
        )
        content.extend(audit_controls or [ft.Text("No runtime activity yet.", size=12, color=LightTheme.TEXT_MUTED)])

        return content

    def _build_training_content(self) -> list:
        """Build training management content."""
        return [
            ft.Text("Training Jobs", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Manage document training and adapters", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
            ft.ElevatedButton(
                "Open Training Manager",
                icon=ft.Icons.PSYCHOLOGY_ROUNDED,
                on_click=lambda e: self.show_training_view(),
                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
            ),
        ]

    def _build_stats_content(self) -> list:
        """Build statistics content."""
        rag_stats = self._get_rag_stats()
        total_secrets = 0
        try:
            query_filter = QueryFilter()
            all_entries = self.vault.kv_store.search(query_filter)
            total_secrets = len([e for e in all_entries if e.entry_type in [EntryType.SECRET, EntryType.API_KEY, EntryType.PASSWORD]])
        except Exception:
            pass

        return [
            ft.Text("Vault Statistics", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Container(height=16),
            ft.Row([
                self._stat_card("Documents", rag_stats.get("document_count", 0), ft.Icons.DESCRIPTION_ROUNDED, LightTheme.ACCENT_PRIMARY),
                self._stat_card("Chunks", rag_stats.get("chunk_count", 0), ft.Icons.DATA_ARRAY_ROUNDED, "#8b5cf6"),
                self._stat_card("Secrets", total_secrets, ft.Icons.KEY_ROUNDED, LightTheme.ACCENT_WARNING),
            ], spacing=16),
        ]

    def _stat_card(self, label, value, icon, color):
        """Create a stat card."""
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, size=24, color=color),
                ft.Text(str(value), size=28, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                ft.Text(label, size=12, color=LightTheme.TEXT_SECONDARY),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            padding=24,
            bgcolor=LightTheme.BG_ELEVATED,
            border_radius=12,
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            expand=True,
        )

    def _build_policies_content(self) -> list:
        """Build LangChain policies content."""
        return [
            ft.Text("LangChain Policies", size=18, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Configure agent behavior and restrictions", size=13, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
            ft.ElevatedButton(
                "Open Policy Editor",
                icon=ft.Icons.SECURITY_ROUNDED,
                on_click=lambda e: self.show_langchain_policies(),
                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
            ),
        ]

    def _send_chat_from_agent_view(self, e, text_field=None):
        """Handle chat from agent view."""
        if text_field and text_field.value:
            question = text_field.value.strip()
            if not question:
                return
            text_field.value = ""
            self.page.update()
            self._open_test_agent_chat(initial_question=question)

    def _configure_vscode_mcp(self):
        """Configure MCP for VS Code."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text("VS Code MCP config copied to clipboard. Paste in .vscode/mcp.json"),
            bgcolor=LightTheme.ACCENT_SUCCESS,
        )
        self.page.snack_bar.open = True
        self._copy_mcp_json()

    def _configure_cursor_mcp(self):
        """Configure MCP for Cursor."""
        self._configure_mcp_target("cursor", "Cursor")

    def _configure_chatgpt_mcp(self):
        """Attempt ChatGPT MCP setup (currently unsupported for local MCP)."""
        self._configure_mcp_target("chatgpt", "ChatGPT")

    def _copy_mcp_json(self):
        """Copy MCP config JSON to clipboard."""
        config = self.mcp_setup.generate_mcp_config() if self.mcp_setup else {
            "mcpServers": {
                "sheriff": {
                    "command": "python",
                    "args": ["-m", "advanced_vault.mcp_server"],
                    "env": {"VAULT_PATH": str(self.vault_path)},
                }
            }
        }
        self.page.set_clipboard(json.dumps(config, indent=2))
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text("MCP config copied to clipboard"),
            bgcolor=LightTheme.ACCENT_SUCCESS,
        )
        self.page.snack_bar.open = True
        self.page.update()

    def show_activity_view(self, search_query: str = "", filter_granted: str = "all", filter_days: str = "all"):
        """Show enhanced MCP access activity log with search, filter, and export."""
        self.current_view = "activity"

        if not hasattr(self, 'secrets_list') or self.secrets_list is None:
            self.build_ui()

        self.secrets_list.controls.clear()

        activity_logger = ActivityLogger(vault_path=str(self.vault_path))

        # Apply filters
        granted_filter = None
        if filter_granted == "granted":
            granted_filter = True
        elif filter_granted == "denied":
            granted_filter = False

        days_filter = None
        if filter_days == "today":
            days_filter = 1
        elif filter_days == "week":
            days_filter = 7

        activities = activity_logger.search_activity(
            query=search_query,
            granted_filter=granted_filter,
            days=days_filter,
            limit=200,
        )

        # Build activity view header
        activity_items = [
            ft.Text("Access Activity", size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Agent access log — search, filter, and export for compliance", size=14, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=12),
            # Search bar
            ft.TextField(
                hint_text="Search activity...",
                prefix_icon=ft.Icons.SEARCH_ROUNDED,
                value=search_query,
                border_radius=8,
                bgcolor=LightTheme.BG_ELEVATED,
                border_color=LightTheme.BORDER_COLOR,
                content_padding=ft.padding.symmetric(horizontal=16, vertical=10),
                on_submit=lambda e: self.show_activity_view(search_query=e.control.value, filter_granted=filter_granted, filter_days=filter_days),
            ),
            ft.Container(height=8),
            # Filter chips
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text("All", size=12, color="white" if filter_granted == "all" else LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=LightTheme.ACCENT_PRIMARY if filter_granted == "all" else LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e: self.show_activity_view(search_query=search_query, filter_granted="all", filter_days=filter_days),
                    ),
                    ft.Container(
                        content=ft.Text("Granted", size=12, color="white" if filter_granted == "granted" else LightTheme.ACCENT_SUCCESS),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=LightTheme.ACCENT_SUCCESS if filter_granted == "granted" else LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e: self.show_activity_view(search_query=search_query, filter_granted="granted", filter_days=filter_days),
                    ),
                    ft.Container(
                        content=ft.Text("Denied", size=12, color="white" if filter_granted == "denied" else LightTheme.ACCENT_ERROR),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=LightTheme.ACCENT_ERROR if filter_granted == "denied" else LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e: self.show_activity_view(search_query=search_query, filter_granted="denied", filter_days=filter_days),
                    ),
                    ft.Container(width=8),
                    ft.Container(
                        content=ft.Text("Today", size=12, color="white" if filter_days == "today" else LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=LightTheme.ACCENT_PRIMARY if filter_days == "today" else LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e: self.show_activity_view(search_query=search_query, filter_granted=filter_granted, filter_days="today"),
                    ),
                    ft.Container(
                        content=ft.Text("This Week", size=12, color="white" if filter_days == "week" else LightTheme.TEXT_PRIMARY),
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                        bgcolor=LightTheme.ACCENT_PRIMARY if filter_days == "week" else LightTheme.BG_ELEVATED,
                        border_radius=16,
                        border=ft.border.all(1, LightTheme.BORDER_COLOR),
                        on_click=lambda e: self.show_activity_view(search_query=search_query, filter_granted=filter_granted, filter_days="week"),
                    ),
                ],
                spacing=8,
            ),
            ft.Container(height=8),
            ft.Text(f"{len(activities)} results", size=12, color=LightTheme.TEXT_MUTED),
            ft.Container(height=12),
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
                except (ValueError, TypeError):
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
        
        # Add action buttons
        activity_items.append(
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Refresh",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=lambda _: self.show_activity_view(search_query=search_query, filter_granted=filter_granted, filter_days=filter_days),
                        style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white", shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                    ft.ElevatedButton(
                        "Export CSV",
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda _: self._export_activity("csv", activities),
                        style=ft.ButtonStyle(bgcolor=LightTheme.BG_ELEVATED, color=LightTheme.TEXT_PRIMARY, shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                    ft.ElevatedButton(
                        "Export JSON",
                        icon=ft.Icons.CODE_ROUNDED,
                        on_click=lambda _: self._export_activity("json", activities),
                        style=ft.ButtonStyle(bgcolor=LightTheme.BG_ELEVATED, color=LightTheme.TEXT_PRIMARY, shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                    ft.ElevatedButton(
                        "Clear Log",
                        icon=ft.Icons.DELETE_ROUNDED,
                        on_click=lambda _: self._clear_activity_log(),
                        style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_ERROR, color="white", shape=ft.RoundedRectangleBorder(radius=8)),
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
    
    def _export_activity(self, format_type: str, activities: list):
        """Export activity log to CSV or JSON file."""
        try:
            activity_logger = ActivityLogger(vault_path=str(self.vault_path))
            if format_type == "csv":
                content = activity_logger.export_csv(activities)
                ext = "csv"
            else:
                content = activity_logger.export_json(activities)
                ext = "json"

            export_path = self.vault_path / f"activity_export.{ext}"
            with open(export_path, 'w') as f:
                f.write(content)

            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Exported {len(activities)} entries to {export_path}"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
        except Exception as e:
            logger.error(f"Failed to export activity: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Export failed: {str(e)}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
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

    def show_permissions_view(self):
        """Show MCP agent permissions management screen."""
        self.current_view = "permissions"

        if not hasattr(self, 'secrets_list') or self.secrets_list is None:
            self.build_ui()

        self.secrets_list.controls.clear()

        # Load consent manager and agents
        try:
            from advanced_vault.mcp_server.consent import ConsentManager, AgentPermission, AccessScope
            consent_manager = ConsentManager(vault_path=str(self.vault_path))
            agents = consent_manager.list_agents()
        except Exception as e:
            logger.error(f"Failed to load consent manager: {e}")
            agents = []
            consent_manager = None

        permission_items = [
            ft.Text("Agent Permissions", size=24, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Control which AI agents can access your data via MCP", size=14, color=LightTheme.TEXT_SECONDARY),
            ft.Container(height=16),
        ]

        if not agents:
            permission_items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.SHIELD_ROUNDED, size=60, color=LightTheme.TEXT_MUTED),
                            ft.Container(height=16),
                            ft.Text("No agents registered yet", size=18, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(
                                "When AI agents connect via MCP, they'll appear here.\nConnect Claude Desktop to get started.",
                                size=14, color=LightTheme.TEXT_SECONDARY, text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=16),
                            ft.ElevatedButton(
                                "Connect Claude Desktop",
                                icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                                on_click=lambda e: self._configure_claude_mcp(),
                                style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white", shape=ft.RoundedRectangleBorder(radius=8)),
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
            for agent_info in agents:
                agent_id = agent_info.get("agent_id", "unknown")
                perm = consent_manager.get_agent_permission(agent_id) if consent_manager else None

                # Determine status
                is_expired = perm.is_expired() if perm else False
                auto_approve = perm.auto_approve if perm else False
                scope_value = perm.scope.value if perm else "all"
                allowed_tools = list(perm.allowed_tools) if perm and perm.allowed_tools else []
                denied_tools = list(perm.denied_tools) if perm and perm.denied_tools else []
                allowed_docs = list(perm.allowed_documents) if perm and perm.allowed_documents else []
                max_queries = perm.max_queries_per_hour if perm else 0

                status_color = LightTheme.ACCENT_ERROR if is_expired else (LightTheme.ACCENT_SUCCESS if auto_approve else LightTheme.ACCENT_WARNING)
                status_text = "Expired" if is_expired else ("Auto-approved" if auto_approve else "Manual consent")
                status_icon = ft.Icons.CANCEL_ROUNDED if is_expired else (ft.Icons.CHECK_CIRCLE_ROUNDED if auto_approve else ft.Icons.PENDING_ROUNDED)

                # MCP tools list
                all_mcp_tools = ["agent_query", "agent_summarize", "agent_draft", "agent_status", "vault_store", "vault_recall", "vault_list_entries", "vault_delete"]
                tool_chips = []
                for tool in all_mcp_tools:
                    is_denied = tool in denied_tools
                    is_allowed = not denied_tools or tool in allowed_tools
                    tool_chips.append(
                        ft.Container(
                            content=ft.Text(tool.replace("_", " ").title(), size=11, color=LightTheme.ACCENT_ERROR if is_denied else LightTheme.ACCENT_SUCCESS),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            bgcolor=(LightTheme.ACCENT_ERROR if is_denied else LightTheme.ACCENT_SUCCESS) + "15",
                            border_radius=12,
                        )
                    )

                card = ft.Container(
                    content=ft.Column(
                        [
                            # Header: agent name + status
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.SMART_TOY_ROUNDED, size=24, color=LightTheme.ACCENT_PRIMARY),
                                    ft.Column([
                                        ft.Text(agent_id, size=16, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
                                        ft.Text(f"Scope: {scope_value} | Max queries/hr: {max_queries or 'unlimited'}", size=12, color=LightTheme.TEXT_SECONDARY),
                                    ], spacing=2, expand=True),
                                    ft.Container(
                                        content=ft.Row([ft.Icon(status_icon, size=14, color=status_color), ft.Text(status_text, size=12, color=status_color)], spacing=4),
                                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                        bgcolor=status_color + "15",
                                        border_radius=12,
                                    ),
                                ],
                            ),
                            ft.Container(height=8),
                            # Tool permissions
                            ft.Text("Tool Access", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Row(tool_chips, wrap=True, spacing=6, run_spacing=6),
                            ft.Container(height=8),
                            # Document restrictions
                            ft.Text(
                                f"Document access: {', '.join(allowed_docs) if allowed_docs else 'All documents'}",
                                size=12, color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Container(height=12),
                            # Action buttons
                            ft.Row(
                                [
                                    ft.ElevatedButton(
                                        "Revoke Access",
                                        icon=ft.Icons.BLOCK_ROUNDED,
                                        on_click=lambda e, aid=agent_id: self._revoke_agent_permission(aid),
                                        style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_ERROR, color="white", shape=ft.RoundedRectangleBorder(radius=8)),
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=20,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_radius=12,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                )
                permission_items.append(card)
                permission_items.append(ft.Container(height=12))

        self.secrets_list.controls.append(
            ft.Container(
                content=ft.Column(permission_items, spacing=0),
                padding=24,
            )
        )
        self.page.update()

    def _revoke_agent_permission(self, agent_id: str):
        """Revoke an agent's permission."""
        try:
            from advanced_vault.mcp_server.consent import ConsentManager
            cm = ConsentManager(vault_path=str(self.vault_path))
            cm.revoke_permission(agent_id)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Revoked access for {agent_id}"),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
            self.show_permissions_view()
        except Exception as e:
            logger.error(f"Failed to revoke permission: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Failed to revoke: {str(e)}"),
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
        
        # Note: Removed separate "Add Knowledge" button - "Upload PDF" is the primary action
        # Knowledge entries are created by uploading PDFs, not text input
        
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
                                        upload_button,
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
            # Initialize file picker if needed
            if not hasattr(self, 'pdf_file_picker') or self.pdf_file_picker is None:
                logger.info("Initializing PDF file picker on first use...")
                self.pdf_file_picker = ft.FilePicker(
                    on_result=self.on_pdf_selected
                )
                self.page.overlay.append(self.pdf_file_picker)
                self.page.update()
            
            # Ensure picker is in overlay
            if self.pdf_file_picker not in self.page.overlay:
                logger.debug("Re-adding file picker to overlay")
                self.page.overlay.append(self.pdf_file_picker)
                self.page.update()
            
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
        """
        Handle PDF file selection - NON-BLOCKING with sidebar progress.
        
        User immediately returns to chat while document processes in background.
        Progress shown in sidebar, toast notification on completion.
        """
        logger.info(f"File picker result: {e}")
        logger.info(f"Files: {e.files if e.files else 'None'}")
        if not e.files or len(e.files) == 0:
            logger.info("No file selected")
            return
        
        file_path = e.files[0].path
        filename = e.files[0].name
        logger.info(f"Selected file: {filename} at {file_path}")
        
        # Initialize processing status in sidebar
        self._update_processing_status(filename, 0, "Starting...", 0.0)
        
        # Show brief toast and return to chat immediately (non-blocking!)
        self.page.snack_bar = ft.SnackBar(
            content=ft.Row(
                [
                    ft.ProgressRing(width=16, height=16, stroke_width=2, color="white"),
                    ft.Text(f"Processing {filename}... See progress in sidebar", color="white"),
                ],
                spacing=12,
            ),
            bgcolor=LightTheme.ACCENT_PRIMARY,
            duration=3000,
        )
        self.page.snack_bar.open = True
        
        # Return to chat - user can continue working!
        self.show_landing_page()
        
        # Process PDF in background thread
        def process_pdf_background():
            safe_pdf_path = None
            result = None
            
            try:
                # === STEP 0: Extracting text ===
                self._update_processing_status(filename, 0, "Extracting text...", 0.1)
                
                # Ensure PDF processor is initialized
                if self.pdf_processor is None:
                    self._initialize_pdf_processor()
                
                # Copy PDF to safe location
                vault_data_dir = Path(self.vault_path) / "temp_pdfs"
                vault_data_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_pdf_path = vault_data_dir / f"{timestamp}_{filename}"
                shutil.copy2(file_path, safe_pdf_path)
                logger.info(f"Copied PDF to safe location: {safe_pdf_path}")
                
                # Process PDF
                result = self.pdf_processor.process_pdf(str(safe_pdf_path))
                page_count = result['metadata']['page_count']
                chunk_count = len(result['text_chunks'])
                logger.info(f"Extracted {chunk_count} chunks from {page_count} pages")

                # Index in RAG for instant querying
                try:
                    full_text = "\n\n".join(result['text_chunks'])
                    self._index_document_in_rag(filename, full_text, source_path=str(safe_pdf_path))
                except Exception as rag_err:
                    logger.warning(f"RAG indexing failed (non-critical): {rag_err}")

                # === STEP 1: Analyzing content (Q&A generation) ===
                self._update_processing_status(filename, 1, f"Analyzing {page_count} pages...", 0.3)
                
                # Generate Q&A pairs automatically (no dialog)
                qa_pairs = []
                encryption_key_hex = None
                
                if self.qa_generator and len(result['text_chunks']) > 0:
                    try:
                        user_id = self._get_current_user_id()
                        # Try synthetic generation via RunPod first (better quality)
                        if hasattr(self.qa_generator, 'generate_synthetic_qa_via_runpod') and os.path.exists(str(safe_pdf_path)):
                            logger.info("Using cloud Q&A generation for better quality...")
                            self._update_processing_status(filename, 1, "Generating Q&A (cloud)...", 0.35)
                            
                            qa_pairs, encryption_key_hex = self.qa_generator.generate_synthetic_qa_via_runpod(
                                pdf_path=str(safe_pdf_path),
                                target_samples=500,  # Target 500 Q&A pairs
                                encryption_key_hex=None
                            )
                        else:
                            # Fallback to local generation
                            logger.info("Using local Q&A generation...")
                            self._update_processing_status(filename, 1, "Generating Q&A (local)...", 0.35)
                            qa_pairs = self.qa_generator.generate_from_chunks(
                                text_chunks=result['text_chunks'],
                                user_id=user_id
                            )
                            
                        logger.info(f"Generated {len(qa_pairs)} Q&A pairs")
                    except Exception as qa_err:
                        logger.warning(f"Cloud Q&A generation failed: {qa_err}, trying local fallback")
                        try:
                            qa_pairs = self.qa_generator.generate_from_chunks(
                                text_chunks=result['text_chunks'],
                                user_id=self._get_current_user_id()
                            )
                            logger.info(f"Generated {len(qa_pairs)} Q&A pairs with local fallback")
                        except Exception as local_qa_err:
                            logger.warning(f"Local fallback Q&A generation failed: {local_qa_err}, continuing without Q&A")
                            # Continue without Q&A - we can still store the document
                
                # === STEP 2: Encrypting data ===
                self._update_processing_status(filename, 2, "Encrypting data...", 0.6)
                
                # Store PDF binary encrypted
                with open(safe_pdf_path, 'rb') as f:
                    pdf_data = f.read()
                
                description_parts = [
                    f"PDF: {page_count} pages, {chunk_count} chunks",
                    f"Path: {safe_pdf_path}"
                ]
                if qa_pairs:
                    description_parts.append(f"Q&A: {len(qa_pairs)} pairs")
                
                entry_id = self.vault.kv_store.put(
                    service=filename,
                    secret_value=base64.b64encode(pdf_data).decode('utf-8'),
                    entry_type=EntryType.OTHER,
                    tags=["pdf", "document", "knowledge"],
                    description=" | ".join(description_parts)
                )
                logger.info(f"Stored PDF as knowledge entry: {filename} (ID: {entry_id})")
                
                # === STEP 3: Syncing to cloud ===
                self._update_processing_status(filename, 3, "Syncing to cloud...", 0.8)
                
                # Cloud sync
                if self.cloud_sync:
                    try:
                        self.cloud_sync.sync_entry_background(entry_id)
                    except Exception as sync_err:
                        logger.warning(f"Cloud sync failed (non-critical): {sync_err}")
                
                # Submit training job if we have Q&A pairs
                if qa_pairs and len(qa_pairs) > 0 and self.training_manager:
                    try:
                        self._update_processing_status(filename, 3, "Submitting to training...", 0.9)
                        
                        # Encrypt and save dataset
                        if encryption_key_hex is None:
                            encryption_key_hex = os.urandom(32).hex()
                        
                        # Convert hex to bytes for save_dataset
                        encryption_key_bytes = bytes.fromhex(encryption_key_hex)
                        
                        dataset_path = self.training_manager.save_dataset(
                            qa_pairs=qa_pairs,
                            filename=filename,
                            encryption_key=encryption_key_bytes
                        )
                        
                        if dataset_path:
                            training_result = self.training_manager.submit_training_job(
                                dataset_path=dataset_path,
                                encryption_key_hex=encryption_key_hex,
                                model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                            )

                            if training_result:
                                # Update vault entry with training info
                                self.vault.kv_store.update_tags(
                                    filename,
                                    ["pdf", "document", "knowledge",
                                     f"training_job:{training_result['adapter_id']}",
                                     f"training_key:{encryption_key_hex}",
                                     "training_status:pending"]
                                )
                                logger.info(f"Training job submitted: {training_result['adapter_id']}")
                    except Exception as train_err:
                        logger.warning(f"Training submission failed: {train_err}")
                        # Continue - document is still saved locally
                
                # === COMPLETE ===
                self._update_processing_status(filename, 4, "Ready!", 1.0, status="completed")
                
                # Remove from processing after short delay (let user see completion)
                def cleanup_and_notify():
                    time.sleep(2)  # Show "completed" state briefly
                    if filename in self.processing_documents:
                        del self.processing_documents[filename]
                    
                    # Show completion toast
                    self._show_completion_toast(filename, success=True)
                    
                    # Refresh landing page to show new document
                    if self.current_view == "landing":
                        self.show_landing_page()
                
                threading.Thread(target=cleanup_and_notify, daemon=True).start()
                
            except Exception as ex:
                logger.error(f"Error processing PDF: {ex}")
                user_msg, _ = make_user_friendly(str(ex), context="upload")
                
                # Update status to failed
                self._update_processing_status(
                    filename, 
                    self.processing_documents.get(filename, {}).get("step", 0),
                    "Failed",
                    status="failed",
                    error=user_msg
                )
                
                # Show error toast
                self._show_completion_toast(filename, success=False, error_msg=user_msg)
        
        # Start background processing
        thread = threading.Thread(target=process_pdf_background, daemon=True)
        thread.start()

    def _find_saved_dataset(self, filename: str) -> Optional[tuple]:
        """
        Check if there's a saved encrypted dataset for this PDF.
        
        Returns:
            Tuple of (dataset_path, encryption_key_hex) if found, None otherwise
        """
        if not self.training_manager or not self.training_manager.datasets_dir:
            return None
        
        try:
            datasets_dir = self.training_manager.datasets_dir
            if not datasets_dir.exists():
                return None
            
            # Look for datasets matching this filename
            base_name = Path(filename).stem
            
            # Find all matching encrypted datasets, sorted by modification time (newest first)
            matching_datasets = []
            for dataset_file in datasets_dir.glob(f"{base_name}*.encrypted"):
                matching_datasets.append((dataset_file, dataset_file.stat().st_mtime))
            
            if not matching_datasets:
                return None
            
            # Get the most recent one
            matching_datasets.sort(key=lambda x: x[1], reverse=True)
            dataset_path = matching_datasets[0][0]
            
            # Try to find the encryption key from the metadata file or vault
            key_file = dataset_path.with_suffix('.key')
            if key_file.exists():
                encryption_key_hex = key_file.read_text().strip()
                logger.info(f"Found saved dataset with key: {dataset_path}")
                return (str(dataset_path), encryption_key_hex)
            
            logger.info(f"Found saved dataset (no key file): {dataset_path}")
            return (str(dataset_path), None)
            
        except Exception as e:
            logger.warning(f"Error searching for saved datasets: {e}")
            return None

    def _resume_training_from_dataset(self, filename: str, dataset_path: str):
        """Resume training from a saved encrypted dataset (skip QA generation)."""
        # Create progress dialog
        progress_dialog, phase_text, progress_bar, phase_status, encryption_indicator, phase_steps = self._create_training_progress_dialog(filename)
        
        self.page.overlay.append(progress_dialog)
        progress_dialog.open = True
        self.page.update()
        
        def workflow():
            try:
                # Skip to Phase 2 completed - we already have the dataset
                def update_phase2():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=1,
                        message="✅ Using saved Q&A dataset",
                        submessage="Skipping Q&A generation...",
                        progress=0.5
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase2)
                    else:
                        update_phase2()
                except Exception:
                    update_phase2()
                
                import time
                time.sleep(0.5)
                
                # Phase 3: Upload saved dataset
                def update_phase3():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=2,
                        message="📤 Uploading encrypted data...",
                        submessage="Connecting to secure storage",
                        progress=0.6
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase3)
                    else:
                        update_phase3()
                except Exception:
                    update_phase3()
                
                # Read encryption key from key file or vault entry
                encryption_key_hex = None
                
                # Try key file first
                key_file = Path(dataset_path).with_suffix('.key')
                if key_file.exists():
                    encryption_key_hex = key_file.read_text().strip()
                    logger.info("Found encryption key in key file")
                else:
                    # Try to get from vault entry tags
                    logger.info("Key file not found, checking vault entry tags...")
                    try:
                        query_filter = QueryFilter()
                        all_entries = self.vault.kv_store.search(query_filter)
                        for entry in all_entries:
                            if entry.service == filename or filename in entry.service:
                                for tag in (entry.tags or []):
                                    if tag.startswith("training_key:") or tag.startswith("encryption_key:"):
                                        encryption_key_hex = tag.split(":", 1)[1]
                                        logger.info(f"Found encryption key in vault tags")
                                        break
                                if encryption_key_hex:
                                    break
                    except Exception as tag_err:
                        logger.warning(f"Could not check vault tags for key: {tag_err}")
                
                if not encryption_key_hex:
                    # Show helpful dialog instead of just error
                    def show_regenerate_prompt():
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Column([
                                ft.Text("⚠️ Encryption key not found for this dataset.", color="white", weight=ft.FontWeight.W_600),
                                ft.Text("Click 'Regenerate' to create new Q&A pairs.", color="white", size=12),
                            ], spacing=4, tight=True),
                            bgcolor=LightTheme.ACCENT_WARNING,
                            duration=6000,
                            action="Regenerate",
                            action_color="white",
                            on_action=lambda e: self._offer_training_from_entry({"service": filename}),
                        )
                        self.page.snack_bar.open = True
                        self.page.update()
                    show_regenerate_prompt()
                    raise ValueError("Encryption key not found. Please regenerate Q&A pairs.")
                
                # Upload dataset
                dataset_url = self.training_manager._upload_dataset_to_supabase_storage(dataset_path)
                
                if not dataset_url:
                    raise ValueError("Failed to upload dataset. Please log out and log back in, then try again.")
                
                logger.info(f"Dataset uploaded successfully: {dataset_url}")
                
                # Phase 4: Submit training job
                def update_phase4():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=3,
                        message="🚀 Submitting training job...",
                        submessage="Training on Qwen3-30B",
                        progress=0.8
                    )
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_phase4)
                    else:
                        update_phase4()
                except Exception:
                    update_phase4()
                
                # Generate adapter ID and submit
                import uuid
                adapter_id = str(uuid.uuid4())
                dataset_name = Path(dataset_path).stem
                
                # Prepare training request
                payload = {
                    "dataset_url": dataset_url,
                    "encryption_key_hex": encryption_key_hex,
                    "adapter_id": adapter_id,
                    "model_name": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                    "rank": 16,
                    "alpha": 32,
                    "epochs": 3,
                    "batch_size": 4,
                    "learning_rate": 2e-4,
                    "enable_compression": True,
                }
                
                # Submit via backend
                response = requests.post(
                    f"{self.training_manager.backend_url}/api/training/submit",
                    headers=self.training_manager.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code != 200:
                    error_msg = response.text
                    if "401" in error_msg or "unauthorized" in error_msg.lower():
                        raise ValueError("Session expired. Please log out and log back in.")
                    raise ValueError(f"Training submission failed: {error_msg}")
                
                result = response.json()
                job_id = result.get("job_id", adapter_id)
                
                logger.info(f"Training job submitted: {job_id}")
                
                # Store or update entry in vault (avoid duplicates)
                entry_tags = [
                    "data_type:knowledge",
                    "source:pdf",
                    f"training_status:pending",
                    f"training_job:{adapter_id}",
                    f"training_key:{encryption_key_hex}",
                ]
                
                self._store_or_update_knowledge_entry(
                    filename=filename,
                    adapter_id=adapter_id,
                    tags=entry_tags,
                    description=f"Knowledge adapter trained from {filename}. Adapter ID: {adapter_id}",
                )
                
                # Success!
                def update_success():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=3,
                        message="✅ Submitted to cloud!",
                        submessage="Training runs in background (~5-10 min). Click Done to continue using the app!",
                        progress=1.0
                    )
                    # Mark step 4 as completed
                    phase_steps.controls[3] = self._create_phase_step("Submit to cloud ☁️", 3, True)
                    progress_dialog.actions = [
                        ft.ElevatedButton(
                            "Done",
                            on_click=lambda e: setattr(progress_dialog, 'open', False) or self.page.update(),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_SUCCESS,
                                color="white",
                            ),
                        ),
                    ]
                    self.page.update()
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(update_success)
                    else:
                        update_success()
                except Exception:
                    update_success()
                
                logger.info(f"Resume training completed for {filename}")
                
            except Exception as ex:
                logger.error(f"Error resuming training: {ex}")
                user_msg, help_link = make_user_friendly(str(ex), context="training")
                is_session_error = help_link == "SESSION_EXPIRED"
                
                def show_error():
                    phase_text.value = f"❌ Error: {user_msg}"
                    phase_status.value = "Resume failed. Your data remains secure."
                    progress_bar.value = None
                    
                    actions = []
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
                
                try:
                    if hasattr(self.page, 'run_task'):
                        self.page.run_task(show_error)
                    else:
                        show_error()
                except Exception:
                    show_error()
        
        # Run workflow in background
        thread = threading.Thread(target=workflow, daemon=True)
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
        
        # Check for saved dataset (from previous failed attempt)
        saved_dataset = self._find_saved_dataset(filename)
        
        def on_yes(e):
            dialog.open = False
            self.page.update()
            self._start_training_workflow(filename, text_chunks, pdf_path=pdf_path)
        
        def on_resume(e):
            """Resume training from saved dataset."""
            dialog.open = False
            self.page.update()
            if saved_dataset:
                self._resume_training_from_dataset(filename, saved_dataset[0])
        
        def on_no(e):
            dialog.open = False
            self.page.update()
        
        # Build dialog content based on whether we have a saved dataset
        if saved_dataset:
            # Offer to resume from saved dataset
            saved_path = saved_dataset[0]
            content_text = (
                f"📁 Found saved Q&A dataset from previous attempt!\n\n"
                f"You can:\n"
                f"• Resume: Upload saved dataset (faster)\n"
                f"• Regenerate: Create new Q&A pairs\n\n"
                f"Saved: {Path(saved_path).name}"
            )
            actions = [
                ft.TextButton(
                    "Cancel",
                    on_click=on_no,
                    style=ft.ButtonStyle(color=LightTheme.TEXT_MUTED),
                ),
                ft.TextButton(
                    "Regenerate",
                    on_click=on_yes,
                    style=ft.ButtonStyle(color=LightTheme.TEXT_SECONDARY),
                ),
                ft.ElevatedButton(
                    "⚡ Resume Training",
                    on_click=on_resume,
                    style=ft.ButtonStyle(
                        bgcolor=LightTheme.ACCENT_SUCCESS,
                        color="white",
                    ),
                ),
            ]
        else:
            # Normal training offer
            content_text = (
                f"Would you like to generate Q&A pairs from this PDF and train a personalized model?\n\n"
                f"This will:\n"
                f"• Generate Q&A pairs from {len(text_chunks)} chunks\n"
                f"• Train a DoRA adapter on your data\n"
                f"• Store encrypted adapter in your vault\n\n"
                f"Note: This may take several minutes."
            )
            actions = [
                ft.TextButton(
                    "No",
                    on_click=on_no,
                    style=ft.ButtonStyle(color=LightTheme.TEXT_MUTED),
                ),
                ft.ElevatedButton(
                    "Yes, Train",
                    on_click=on_yes,
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                    ),
                ),
            ]
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Resume Training?" if saved_dataset else "Generate Training Model?",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Text(
                content_text,
                color=LightTheme.TEXT_SECONDARY,
            ),
            actions=actions,
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
        description = entry.get('description', '')
        
        # Try to find existing PDF path from description or temp_pdfs
        existing_pdf_path = None
        
        # Check description for path (format: "PDF: X pages, Y chunks | Path: /path/to/file")
        if description and "Path:" in description:
            try:
                path_part = description.split("Path:")[-1].strip()
                if os.path.exists(path_part):
                    existing_pdf_path = path_part
                    logger.info(f"Found existing PDF at: {existing_pdf_path}")
            except Exception:
                pass
        
        # Check temp_pdfs directory for matching file
        if not existing_pdf_path:
            vault_data_dir = Path(self.vault_path) / "temp_pdfs"
            if vault_data_dir.exists():
                # Look for files matching the service name
                for pdf_file in vault_data_dir.glob(f"*{service}*"):
                    if pdf_file.suffix.lower() == '.pdf' or 'pdf' in service.lower():
                        # Verify it's a valid PDF
                        try:
                            with open(pdf_file, 'rb') as f:
                                header = f.read(5)
                                if header == b'%PDF-':
                                    existing_pdf_path = str(pdf_file)
                                    logger.info(f"Found existing PDF in temp_pdfs: {existing_pdf_path}")
                                    break
                        except Exception:
                            continue
        
        # If we found an existing PDF, use it directly
        if existing_pdf_path and os.path.exists(existing_pdf_path):
            safe_pdf_path = Path(existing_pdf_path)
        else:
            # Extract PDF data from entry
            try:
                logger.info(f"Extracting PDF for training: {service}")
                secret_value = self.vault.kv_store.get(service)
                if not secret_value:
                    logger.error(f"No secret value found for service: {service}")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ Could not retrieve PDF data for '{service}'"),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                
                logger.info(f"Secret value type: {type(secret_value)}, length: {len(secret_value) if secret_value else 0}")
                
                # Decode base64 PDF data (with padding fix)
                pdf_data = None
                try:
                    # Add padding if needed (base64 strings should be multiple of 4)
                    if isinstance(secret_value, str):
                        missing_padding = len(secret_value) % 4
                        if missing_padding:
                            secret_value += '=' * (4 - missing_padding)
                        pdf_data = base64.b64decode(secret_value)
                except Exception as decode_err:
                    logger.warning(f"Base64 decode failed: {decode_err}")
                
                # Check if it's already raw bytes
                if pdf_data is None:
                    if isinstance(secret_value, bytes):
                        pdf_data = secret_value
                    elif isinstance(secret_value, str) and os.path.exists(secret_value):
                        # It might be a file path
                        with open(secret_value, 'rb') as f:
                            pdf_data = f.read()
                
                if pdf_data is None:
                    raise ValueError("Could not decode or read PDF data")
                
                # Validate PDF header
                if not pdf_data[:5] == b'%PDF-':
                    logger.error(f"Invalid PDF header. First 20 bytes: {pdf_data[:20]}")
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"❌ Stored data is not a valid PDF. Please re-upload the document."),
                        bgcolor=LightTheme.ACCENT_ERROR,
                        duration=5000,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
                    return
                
                # Write to persistent location
                vault_data_dir = Path(self.vault_path) / "temp_pdfs"
                vault_data_dir.mkdir(parents=True, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_pdf_path = vault_data_dir / f"{timestamp}_{service}"
                
                with open(safe_pdf_path, 'wb') as f:
                    f.write(pdf_data)
                
                logger.info(f"Saved PDF to persistent location: {safe_pdf_path}")
                
            except Exception as ex:
                logger.error(f"Error extracting PDF for training: {ex}")
                user_msg, _ = make_user_friendly(str(ex), context="training")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"❌ {user_msg}"),
                    bgcolor=LightTheme.ACCENT_ERROR,
                )
                self.page.snack_bar.open = True
                self.page.update()
                return
        
        # Now process the PDF
        tmp_path = None
        try:
            logger.info(f"Processing PDF: {safe_pdf_path}")
            
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
                self._create_phase_step("Extracting text", 0, False),
                self._create_phase_step("Analyzing content", 1, False),
                self._create_phase_step("Encrypting & uploading", 2, False),
                self._create_phase_step("Submit to cloud ☁️", 3, False),
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
                                    f"🔐 Preparing Your Document",
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
            ("Submit to cloud ☁️", "🚀 Submitting training job to secure cloud..."),
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
                
                # Phase 4: Submit to cloud (training job)
                def update_phase4():
                    self._update_training_phase(
                        phase_text, progress_bar, phase_status, phase_steps,
                        phase=3,
                        message="🚀 Submitting to cloud...",
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
                        message="☁️ Cloud training starting...",
                        submessage="Training runs asynchronously on secure cloud infrastructure",
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
                        "Encrypting & uploading",
                        "Submit to cloud ☁️"
                    ]
                    for i in range(4):
                        step = self._create_phase_step(phases[i], i, True)
                        phase_steps.controls[i] = step
                    
                    phase_text.value = "✅ Document Ready!"
                    phase_status.value = f"Your document is processed and encrypted. ID: {result['adapter_id'][:8]}...\n\n💡 Return to chat to ask questions!"
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
        
        # Check if local inference is available
        local_available = False
        try:
            from local_inference import LocalInferenceEngine
            engine = LocalInferenceEngine()
            local_available = engine.is_available()
        except Exception as e:
            logger.debug(f"Local inference not available: {e}")
        
        # Inference mode: local-only in current deployment.
        inference_mode = {"value": "local"}  # Use dict for mutable state in closure
        
        def on_mode_change(e):
            inference_mode["value"] = e.control.value
            # Update button text based on mode
            if e.control.value == "local":
                submit_button.text = "Ask Locally"
                submit_button.icon = ft.Icons.COMPUTER_ROUNDED
                mode_hint.value = "🏠 Runs on your device - private & offline"
            else:
                # Cloud is disabled; force local mode.
                inference_mode["value"] = "local"
                mode_dropdown.value = "local"
                submit_button.text = "Ask Locally"
                submit_button.icon = ft.Icons.COMPUTER_ROUNDED
                mode_hint.value = "🏠 Runs on your device - private & offline"
            self.page.update()
        
        mode_dropdown = ft.Dropdown(
            label="Inference Mode",
            value="local",
            options=[
                ft.dropdown.Option("local", "🏠 Local (Your Device)"),
            ],
            on_change=on_mode_change,
            width=200,
            border_radius=8,
            bgcolor=LightTheme.BG_ELEVATED,
            border_color=LightTheme.BORDER_COLOR,
            focused_border_color=LightTheme.ACCENT_PRIMARY,
            disabled=True,
        )
        
        mode_hint = ft.Text(
            "🏠 Runs on your device - private & offline",
            size=11,
            color=LightTheme.TEXT_MUTED,
            italic=True,
        )
        
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
        
        # Enhanced "AI is thinking" loading indicator
        thinking_phrases = [
            "🧠 AI is thinking...",
            "📚 Reading your document...",
            "💭 Formulating response...",
            "✨ Almost there...",
        ]
        
        loading_indicator = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Lottie(
                                    src="https://assets10.lottiefiles.com/packages/lf20_usmfx6bp.json",
                                    width=40,
                                    height=40,
                                    animate=True,
                                ) if False else ft.ProgressRing(  # Fallback to ProgressRing
                                    width=24, 
                                    height=24, 
                                    stroke_width=3,
                                    color=LightTheme.ACCENT_PRIMARY,
                                ),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "🧠 AI is thinking...", 
                                        size=14, 
                                        weight=ft.FontWeight.W_500,
                                        color=LightTheme.ACCENT_PRIMARY,
                                    ),
                                    ft.Text(
                                        "Analyzing your document with the trained knowledge base",
                                        size=11,
                                        color=LightTheme.TEXT_MUTED,
                                        italic=True,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=16,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
                    ft.Container(height=8),
                    ft.Container(
                        content=ft.ProgressBar(
                            value=None,  # Indeterminate
                            bgcolor=LightTheme.BORDER_COLOR,
                            color=LightTheme.ACCENT_PRIMARY,
                        ),
                        width=280,
                        height=4,
                        border_radius=2,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            padding=20,
            bgcolor=LightTheme.ACCENT_PRIMARY + "08",
            border_radius=12,
            border=ft.border.all(1, LightTheme.ACCENT_PRIMARY + "20"),
            visible=False,
        )
        
        loading_text = loading_indicator.content.controls[0].controls[1].controls[0]  # Reference for updating text
        
        def ask_query(e):
            """Send query to local inference endpoint."""
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
            mode_dropdown.disabled = True
            self.page.update()
            
            def run_inference():
                try:
                    # LOCAL INFERENCE - runs entirely on device
                    self._run_local_inference(
                        query, knowledge_id, encryption_key_hex, filename,
                        loading_text, loading_indicator, response_text,
                        response_container, query_field, submit_button, mode_dropdown
                    )
                    
                except Exception as ex:
                    logger.error(f"Demo query error: {ex}")
                    def show_error():
                        loading_indicator.visible = False
                        query_field.disabled = False
                        submit_button.disabled = False
                        mode_dropdown.disabled = False
                        response_text.value = f"Error: {str(ex)}"
                        response_container.visible = True
                        self.page.update()
                    
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
                f"Ask - {filename}",
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
                        ft.Container(height=12),
                        ft.Row(
                            [mode_dropdown, ft.Container(width=12), mode_hint],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
    
    def _run_cloud_inference(
        self, query: str, knowledge_id: str, encryption_key_hex: str, filename: str,
        loading_indicator, response_text, response_container,
        query_field, submit_button, mode_dropdown
    ):
        """Run inference using cloud RunPod endpoint."""
        import time
        
        try:
            # First check adapter status before inference
            try:
                max_polls = 5
                poll_interval = 2
                
                adapter_status = "unknown"
                for poll_count in range(max_polls):
                    status_result = self.training_manager.get_training_status(knowledge_id)
                    adapter_status = status_result.get("status", "unknown")
                    
                    if adapter_status == "completed":
                        break
                    elif adapter_status in ["pending", "training"]:
                        if poll_count < max_polls - 1:
                            time.sleep(poll_interval)
                            continue
                    break
                
                if adapter_status != "completed":
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
                        mode_dropdown.disabled = False
                        response_text.value = error_msg
                        response_container.visible = True
                        self.page.update()
                    
                    show_not_ready()
                    return
            except Exception as status_err:
                logger.warning(f"Could not check adapter status: {status_err}")
            
            # Call training manager's inference method
            response = self.training_manager.inference_with_adapter(
                adapter_id=knowledge_id,
                query=query,
                encryption_key_hex=encryption_key_hex
            )
            
            def update_ui():
                loading_indicator.visible = False
                query_field.disabled = False
                submit_button.disabled = False
                mode_dropdown.disabled = False
                
                if response and "response" in response:
                    response_text.value = response["response"]
                    response_container.visible = True
                    # Save to question history
                    self._save_question_history(query, filename, response["response"], mode="cloud")
                else:
                    response_text.value = "No response received"
                    response_container.visible = True
                
                self.page.update()
            
            update_ui()
            
        except Exception as ex:
            logger.error(f"Cloud inference error: {ex}")
            def show_error():
                loading_indicator.visible = False
                query_field.disabled = False
                submit_button.disabled = False
                mode_dropdown.disabled = False
                response_text.value = f"Error: {str(ex)}"
                response_container.visible = True
                self.page.update()
            
            show_error()
            
    def _run_local_inference(
        self, query: str, knowledge_id: str, encryption_key_hex: str, filename: str,
        loading_text, loading_indicator, response_text, response_container,
        query_field, submit_button, mode_dropdown
    ):
        """Run inference locally using downloaded adapter."""
        try:
            from local_inference import get_local_engine
            
            engine = get_local_engine()
            
            # Step 1: Load model if needed
            def update_loading(msg):
                loading_text.value = msg
                self.page.update()
            
            update_loading("Loading TinyLlama model...")
            
            if not engine.load_model(progress_callback=update_loading):
                raise RuntimeError("Failed to load model")
            
            # Step 2: Download and decrypt adapter
            update_loading("Downloading encrypted adapter...")
            
            # Get adapter download URL from backend
            adapter_path = self._download_adapter_for_local(knowledge_id)
            
            if not adapter_path:
                raise RuntimeError("⏳ Adapter not ready yet - training is still in progress on the cloud. Check back in 2-5 minutes.")
            
            update_loading("Decrypting adapter...")
            adapter_weights = engine.decrypt_adapter(adapter_path, encryption_key_hex)
            
            # Step 3: Apply adapter weights
            update_loading("Applying adapter weights...")
            engine.apply_adapter_weights(adapter_weights)
            
            # Step 4: Generate response
            update_loading("🤖 Generating response...")
            response = engine.generate(query, max_tokens=256, temperature=0.7)
            
            # Show response
            def update_ui():
                loading_indicator.visible = False
                query_field.disabled = False
                submit_button.disabled = False
                mode_dropdown.disabled = False
                response_text.value = response
                response_container.visible = True
                # Save to question history
                self._save_question_history(query, filename, response, mode="local")
                self.page.update()
            
            update_ui()
            
        except Exception as ex:
            logger.error(f"Local inference error: {ex}")
            def show_error():
                loading_indicator.visible = False
                query_field.disabled = False
                submit_button.disabled = False
                mode_dropdown.disabled = False
                response_text.value = f"Local inference error: {str(ex)}"
                response_container.visible = True
                self.page.update()
            
            show_error()
    
    def _store_or_update_knowledge_entry(
        self, 
        filename: str, 
        adapter_id: str, 
        tags: list, 
        description: str
    ):
        """
        Store or update a knowledge entry, avoiding duplicates.
        
        If an entry with the same filename exists, update it instead of creating a new one.
        """
        # Check if entry already exists
        existing_entry = None
        try:
            # Search for ANY entry with this filename
            filter = QueryFilter()
            results = self.vault.kv_store.search(filter)
            
            # Find existing entry for this filename (any knowledge-related entry)
            for entry in results:
                if entry.service == filename:
                    entry_tags = entry.tags or []
                    # Check if it's a knowledge/document entry (various tag formats)
                    is_knowledge = any(
                        t.startswith("data_type:knowledge") or
                        t == "knowledge" or
                        t == "document" or
                        t == "pdf" or
                        t.startswith("training_")
                        for t in entry_tags
                    )
                    if is_knowledge:
                        existing_entry = entry
                        logger.info(f"Found existing knowledge entry for {filename}: {entry.id}")
                        break
        except Exception as e:
            logger.warning(f"Could not search for existing entry: {e}")
        
        if existing_entry:
            # Update existing entry instead of creating duplicate
            logger.info(f"Updating existing knowledge entry for: {filename}")
            try:
                # Get decrypted value (or use placeholder)
                decrypted_value = self.vault.kv_store.get_by_id(existing_entry.id)
                if not decrypted_value:
                    decrypted_value = f"Adapter: {adapter_id}"
                
                # Update with new tags and description
                self.vault.kv_store.put(
                    service=filename,
                    secret_value=decrypted_value,
                    entry_type=existing_entry.entry_type,
                    tags=tags,
                    description=description,
                    entry_id=existing_entry.id,  # Use existing ID to update
                )
                logger.info(f"Updated existing entry: {existing_entry.id}")
            except Exception as e:
                logger.error(f"Failed to update existing entry, creating new: {e}")
                # Fall back to creating new entry
                self.vault.kv_store.put(
                    service=filename,
                    secret_value=f"Adapter: {adapter_id}",
                    tags=tags,
                    description=description,
                )
        else:
            # Create new entry
            logger.info(f"Creating new knowledge entry for: {filename}")
            self.vault.kv_store.put(
                service=filename,
                secret_value=f"Adapter: {adapter_id}",
                tags=tags,
                description=description,
            )
    
    def _download_adapter_for_local(self, adapter_id: str) -> Optional[str]:
        """Download encrypted adapter for local inference."""
        try:
            # Check if we have it cached locally first
            local_cache = Path(self.vault_path) / "adapters" / f"{adapter_id}.encrypted"
            if local_cache.exists():
                logger.info(f"Using cached adapter: {local_cache}")
                return str(local_cache)
            
            # Get download URL from backend
            response = requests.get(
                f"{self.backend_url}/api/adapters/{adapter_id}/download",
                headers=self.training_manager.headers if self.training_manager else {},
                timeout=30
            )
            
            if response.status_code == 404:
                logger.warning(f"Adapter not found (404) - training may still be in progress")
                return None
            elif response.status_code != 200:
                logger.error(f"Failed to get adapter download URL: {response.status_code}")
                return None
            
            data = response.json()
            download_url = data.get("download_url") or data.get("url")
            
            if not download_url:
                logger.error("No download URL in response")
                return None
            
            # Download the encrypted adapter
            logger.info(f"Downloading adapter from cloud...")
            adapter_response = requests.get(download_url, timeout=120)
            
            if adapter_response.status_code != 200:
                logger.error(f"Failed to download adapter: {adapter_response.status_code}")
                return None
            
            # Save to local cache
            local_cache.parent.mkdir(parents=True, exist_ok=True)
            with open(local_cache, 'wb') as f:
                f.write(adapter_response.content)
            
            logger.info(f"Adapter downloaded and cached: {local_cache}")
            return str(local_cache)
            
        except Exception as e:
            logger.error(f"Error downloading adapter: {e}")
            return None

    def show_training_view(self):
        """Show training jobs view."""
        self.current_view = "training"
        self._stop_landing_status_polling()  # Stop landing page polling
        
        # Ensure main UI layout exists (secrets_list is created by build_ui)
        if not hasattr(self, 'secrets_list') or self.secrets_list is None:
            self.build_ui()
        
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
        self._stop_landing_status_polling()  # Stop landing page polling
        # Prevent infinite loops
        if self._refreshing_settings:
            return
        
        self.current_view = "settings"
        
        # Ensure main UI layout exists (secrets_list is created by build_ui)
        if not hasattr(self, 'secrets_list') or self.secrets_list is None:
            self.build_ui()
        
        self.secrets_list.controls.clear()
        
        # Get MCP setup status (uses cache to avoid repeated initialization)
        mcp_status = self.mcp_setup.get_setup_status()
        
        # Build settings content
        settings_items = [
            ft.Text(
                self.tr("settings.title"),
                size=24,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            ft.Text(
                self.tr("language.selector.title"),
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                self.tr("language.selector.description"),
                size=12,
                color=LightTheme.TEXT_MUTED,
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Dropdown(
                            value=self.language,
                            width=220,
                            options=[
                                ft.dropdown.Option(code, label)
                                for code, label in SUPPORTED_LANGUAGES.items()
                            ],
                            on_change=lambda e: self.set_language(e.control.value),
                            border_radius=8,
                            bgcolor=LightTheme.BG_ELEVATED,
                            border_color=LightTheme.BORDER_COLOR,
                            focused_border_color=LightTheme.ACCENT_PRIMARY,
                        ),
                    ],
                ),
                padding=ft.padding.only(top=6, bottom=8),
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Vault Info Section
            ft.Text(
                self.tr("settings.vault_info.title"),
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                self.tr("settings.vault_info.path", path=self.vault_path),
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                self.tr("settings.vault_info.master_key", path=self.key_path),
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                self.tr("settings.vault_info.database", path=self.db_path),
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Encryption Info
            ft.Text(
                self.tr("settings.encryption.algorithm"),
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Text(
                self.tr("settings.encryption.key_size"),
                size=14,
                color=LightTheme.TEXT_SECONDARY,
            ),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            
            # Component Status Section
            ft.Text(
                self.tr("settings.components.title"),
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                self.tr("settings.components.subtitle"),
                size=12,
                color=LightTheme.TEXT_MUTED,
            ),
            ft.Container(height=8),
        ]
        
        # Add component status cards
        components = [
            {
                "name": self.tr("settings.components.ocr.name"),
                "description": self.tr("settings.components.ocr.description"),
                "status_key": "ocr",
                "icon": ft.Icons.DOCUMENT_SCANNER_ROUNDED,
            },
            {
                "name": self.tr("settings.components.qa.name"),
                "description": self.tr("settings.components.qa.description"),
                "status_key": "qa",
                "icon": ft.Icons.QUESTION_ANSWER_ROUNDED,
            },
            {
                "name": self.tr("settings.components.vault.name"),
                "description": self.tr("settings.components.vault.description"),
                "status_key": "vault",
                "icon": ft.Icons.LOCK_ROUNDED,
            },
            {
                "name": self.tr("settings.components.sync.name"),
                "description": self.tr("settings.components.sync.description"),
                "status_key": "cloud_sync",
                "icon": ft.Icons.CLOUD_DONE_ROUNDED,
            },
            {
                "name": self.tr("settings.components.training.name"),
                "description": self.tr("settings.components.training.description"),
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
                        status_info = {"status": "ready", "message": self.tr("settings.status.ready.optimized_ai"), "requires_setup": False}
                    elif qa_status.get("qa_model_available"):
                        status_info = {"status": "ready", "message": self.tr("settings.status.ready.local_ai"), "requires_setup": False}
                    elif qa_status.get("mlx_available"):
                        status_info = {"status": "checking", "message": self.tr("settings.status.setup_required_ai"), "requires_setup": True}
                    else:
                        status_info = {"status": "checking", "message": self.tr("settings.status.qa_model_missing"), "requires_setup": True}
                    # Update cache
                    self._component_status["qa"] = status_info
                except Exception as e:
                    logger.debug(f"Could not get Q&A status: {e}")
                    status_info = self._component_status.get(component["status_key"], {"status": "unknown", "message": self.tr("settings.status.unknown")})
            else:
                status_info = self._component_status.get(component["status_key"], {"status": "unknown", "message": self.tr("settings.status.unknown")})
            
            # Determine status color and icon
            if status_info["status"] == "ready":
                status_color = LightTheme.ACCENT_SUCCESS
                status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED
                status_text = self.tr("settings.status.ready")
            elif status_info["status"] == "installing":
                status_color = LightTheme.ACCENT_PRIMARY
                status_icon = ft.Icons.DOWNLOADING_ROUNDED
                status_text = status_info["message"]
            elif status_info["status"] == "checking":
                requires_setup = bool(status_info.get("requires_setup"))
                status_color = LightTheme.ACCENT_WARNING if requires_setup else LightTheme.TEXT_MUTED
                status_icon = ft.Icons.DOWNLOAD_ROUNDED if requires_setup else ft.Icons.HOURGLASS_EMPTY_ROUNDED
                status_text = status_info["message"]
            elif status_info["status"] == "error":
                status_color = LightTheme.ACCENT_ERROR
                status_icon = ft.Icons.ERROR_ROUNDED
                status_text = self.tr("settings.status.error")
            else:
                status_color = LightTheme.TEXT_MUTED
                status_icon = ft.Icons.HELP_OUTLINE_ROUNDED
                status_text = self.tr("settings.status.unknown")
            
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
                self.tr("settings.mcp.title"),
                size=18,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                self.tr("settings.mcp.subtitle"),
                size=12,
                color=LightTheme.TEXT_MUTED,
            ),
            ft.Container(height=8),
        ])
        
        # MCP Status
        claude_installed = bool(mcp_status.get("claude_installed"))
        claude_configured = bool(mcp_status.get("claude_mcp_configured", mcp_status.get("mcp_configured")))
        cursor_installed = bool(mcp_status.get("cursor_installed"))
        cursor_configured = bool(mcp_status.get("cursor_mcp_configured"))
        chatgpt_installed = bool(mcp_status.get("chatgpt_installed"))
        chatgpt_supported = bool(mcp_status.get("chatgpt_local_mcp_supported"))

        if claude_installed:
            status_color = LightTheme.ACCENT_SUCCESS if claude_configured else LightTheme.ACCENT_WARNING
            status_icon = ft.Icons.CHECK_CIRCLE_ROUNDED if claude_configured else ft.Icons.WARNING_ROUNDED
            status_text = self.tr("settings.mcp.status.configured") if claude_configured else self.tr("settings.mcp.status.not_configured")
            settings_items.append(
                ft.Row(
                    [
                        ft.Icon(status_icon, color=status_color, size=20),
                        ft.Text(
                            self.tr("settings.mcp.claude_status", status=status_text),
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
                            self.tr("settings.mcp.claude_not_detected"),
                            size=14,
                            color=LightTheme.TEXT_MUTED,
                        ),
                    ],
                    spacing=8,
                )
            )

        cursor_color = LightTheme.ACCENT_SUCCESS if cursor_configured else (LightTheme.ACCENT_WARNING if cursor_installed else LightTheme.TEXT_MUTED)
        cursor_icon = ft.Icons.CHECK_CIRCLE_ROUNDED if cursor_configured else (ft.Icons.WARNING_ROUNDED if cursor_installed else ft.Icons.INFO_ROUNDED)
        cursor_text = (
            "Cursor: configured"
            if cursor_configured
            else ("Cursor: detected, not configured" if cursor_installed else "Cursor: not detected")
        )
        settings_items.append(
            ft.Row(
                [
                    ft.Icon(cursor_icon, color=cursor_color, size=20),
                    ft.Text(cursor_text, size=14, color=cursor_color),
                ],
                spacing=8,
            )
        )

        chatgpt_color = LightTheme.ACCENT_WARNING if chatgpt_installed else LightTheme.TEXT_MUTED
        chatgpt_icon = ft.Icons.INFO_ROUNDED if chatgpt_installed else ft.Icons.INFO_OUTLINE_ROUNDED
        chatgpt_text = (
            "ChatGPT desktop detected; local MCP setup currently unsupported."
            if chatgpt_installed and not chatgpt_supported
            else ("ChatGPT: local MCP supported" if chatgpt_supported else "ChatGPT: not detected")
        )
        settings_items.append(
            ft.Row(
                [
                    ft.Icon(chatgpt_icon, color=chatgpt_color, size=20),
                    ft.Text(chatgpt_text, size=14, color=chatgpt_color),
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
                            self.tr("settings.mcp.test_result", message=mcp_status["test_message"]),
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
                            self.tr("settings.mcp.test_result", message=mcp_status["test_message"]),
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
                content=ft.Text(self.tr("settings.mcp.copied")),
                bgcolor=LightTheme.ACCENT_SUCCESS,
            )
            self.page.snack_bar.open = True
            self.page.update()
        
        mcp_buttons.append(
            ft.ElevatedButton(
                self.tr("settings.mcp.copy_config"),
                icon=ft.Icons.COPY_ROUNDED,
                on_click=copy_config,
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            )
        )
        
        # Auto-Configure Button (if at least one supported client is detected)
        if mcp_status.get("claude_installed") or mcp_status.get("cursor_installed"):
            def auto_configure(e):
                try:
                    result = self.mcp_setup.auto_configure_all_clients()
                    configured_count = int(result.get("configured_count", 0))

                    if configured_count > 0:
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text(f"Configured MCP for {configured_count} client(s). Restart apps to apply."),
                            bgcolor=LightTheme.ACCENT_SUCCESS,
                        )
                    else:
                        self.page.snack_bar = ft.SnackBar(
                            content=ft.Text("No supported client detected for auto-config."),
                            bgcolor=LightTheme.ACCENT_WARNING,
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
                        content=ft.Text(self.tr("settings.mcp.auto_configure.error", error=str(ex))),
                        bgcolor=LightTheme.ACCENT_ERROR,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            
            mcp_buttons.append(
                ft.ElevatedButton(
                    self.tr("settings.mcp.auto_configure.button"),
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
                        ft.Text(self.tr("settings.mcp.test_result", message=message)),
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
                self.tr("settings.mcp.test.button"),
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
                    self.tr("settings.mcp.instructions.title"),
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                ft.Text(
                    self.tr("settings.mcp.instructions.step1", path=mcp_status["config_path"]),
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    self.tr("settings.mcp.instructions.step2"),
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    self.tr("settings.mcp.instructions.step3"),
                    size=12,
                    color=LightTheme.ACCENT_WARNING,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    self.tr("settings.mcp.instructions.step4"),
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Text(
                    self.tr("settings.mcp.instructions.step5"),
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
            ])
        
        # Inference section (local-only)
        settings_items.extend([
            ft.Container(height=12),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            ft.Text("Inference Mode", size=18, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
            ft.Text("Local inference only (cloud mode currently disabled).", size=12, color=LightTheme.TEXT_MUTED),
            ft.Container(height=6),
            ft.ElevatedButton(
                "Run Local Setup",
                icon=ft.Icons.BOLT_ROUNDED,
                on_click=lambda e: self._run_local_setup(),
                style=ft.ButtonStyle(
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    color="white",
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            ),
            ft.Container(height=8),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("Use Local Inference", size=14, color=LightTheme.TEXT_PRIMARY),
                        ft.Container(expand=True),
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE_ROUNDED,
                            color=LightTheme.ACCENT_SUCCESS,
                            size=18,
                        ),
                    ],
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                bgcolor=LightTheme.BG_ELEVATED,
                border_radius=8,
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row([ft.Icon(ft.Icons.COMPUTER_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Runs on your device", size=12, color=LightTheme.TEXT_SECONDARY)], spacing=6),
                        ft.Row([ft.Icon(ft.Icons.VISIBILITY_OFF_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("No cloud endpoint required", size=12, color=LightTheme.TEXT_SECONDARY)], spacing=6),
                        ft.Row([ft.Icon(ft.Icons.WIFI_OFF_ROUNDED, size=14, color=LightTheme.ACCENT_SUCCESS), ft.Text("Works offline after local model setup", size=12, color=LightTheme.TEXT_SECONDARY)], spacing=6),
                    ],
                    spacing=4,
                ),
                padding=12,
                bgcolor=LightTheme.ACCENT_SUCCESS + "08",
                border_radius=8,
            ),
        ])

        # Permissions link
        settings_items.extend([
            ft.Container(height=12),
            ft.Divider(color=LightTheme.BORDER_COLOR),
            ft.Text(self.tr("settings.permissions.title"), size=18, weight=ft.FontWeight.BOLD, color=LightTheme.TEXT_PRIMARY),
            ft.Text(self.tr("settings.permissions.subtitle"), size=12, color=LightTheme.TEXT_MUTED),
            ft.Container(height=8),
            ft.ElevatedButton(
                self.tr("settings.permissions.button"),
                icon=ft.Icons.SHIELD_ROUNDED,
                on_click=lambda e: self.on_nav_change(8),
                style=ft.ButtonStyle(bgcolor=LightTheme.BG_ELEVATED, color=LightTheme.TEXT_PRIMARY, shape=ft.RoundedRectangleBorder(radius=8)),
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

        if not self.qa_generator:
            raise ValueError("QA generator not available")

        user_id = self._get_current_user_id()
        local_training_mode = self._use_local_training_mode()
        qa_pairs: List[Dict[str, str]] = []

        # Try cloud synthetic generation first when endpoint credentials are present.
        runpod_api_key = os.getenv("RUNPOD_API_KEY")
        qa_api_key = os.getenv("RUNPOD_QA_API_KEY")
        qa_endpoint_id = os.getenv("RUNPOD_QA_ENDPOINT_ID")
        api_key = qa_api_key or runpod_api_key

        if (not local_training_mode) and api_key and qa_endpoint_id:
            try:
                progress_callback(20.0, "Generating Q&A (cloud)...")
                qa_pairs, _ = self.qa_generator.generate_synthetic_qa_via_runpod(
                    pdf_path=file_path,
                    target_samples=100,
                    encryption_key_hex=None
                )
            except Exception as e:
                logger.warning(f"Cloud Q&A generation failed, using local fallback: {e}")

        if not qa_pairs:
            progress_callback(20.0, "Generating Q&A (local)...")
            qa_pairs = self.qa_generator.generate_from_chunks(
                text_chunks=text_chunks,
                user_id=user_id,
                num_pairs_per_chunk=3
            )

        qa_pairs = qa_pairs[:100]
        if not qa_pairs:
            raise ValueError("Failed to generate Q&A pairs")
        
        progress_callback(50.0, f"Generated {len(qa_pairs)} Q&A pairs")

        if local_training_mode:
            return self._train_document_locally(filename, qa_pairs, progress_callback)

        if not self.training_manager:
            raise ValueError("Training manager unavailable. Enable ENCLAVE_LOCAL_TRAINING=true for local training.")

        # Cloud training path
        progress_callback(55.0, "Encrypting dataset...")
        dataset_name = Path(filename).stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        encryption_key = os.urandom(32)
        encryption_key_hex = encryption_key.hex()

        dataset_path = self.training_manager.save_dataset(
            qa_pairs=qa_pairs,
            filename=dataset_name,
            encryption_key=encryption_key,
        )

        progress_callback(70.0, "Submitting training job...")
        submit_result = self.training_manager.submit_training_job(
            dataset_path=dataset_path,
            encryption_key_hex=encryption_key_hex,
            epochs=3,
            batch_size=4,
        )
        adapter_id = submit_result.get("adapter_id") or submit_result.get("job_id")
        if not adapter_id:
            raise ValueError("Training service did not return adapter_id")

        progress_callback(85.0, "Training submitted to cloud")

        # Store or update entry in vault (avoid duplicates)
        entry_tags = [
            "data_type:knowledge",
            "source:pdf",
            "training_mode:cloud",
            "training_status:pending",
            f"training_job:{adapter_id}",
            f"training_key:{encryption_key_hex}",
        ]

        self._store_or_update_knowledge_entry(
            filename=filename,
            adapter_id=adapter_id,
            tags=entry_tags,
            description=f"Knowledge adapter training submitted for {filename}. Adapter ID: {adapter_id}",
        )

        progress_callback(100.0, "Complete!")
        return adapter_id, encryption_key_hex

    def _use_local_training_mode(self) -> bool:
        """
        Decide whether training queue should use local MLX training.

        ENCLAVE_LOCAL_TRAINING values:
        - true/1/yes/on: force local mode
        - false/0/no/off: force cloud mode
        - unset/auto: local on Apple Silicon, cloud otherwise
        """
        setting = os.getenv("ENCLAVE_LOCAL_TRAINING", "auto").strip().lower()
        if setting in {"1", "true", "yes", "on"}:
            return True
        if setting in {"0", "false", "no", "off"}:
            return False
        return platform.machine() == "arm64"

    def _train_document_locally(self, filename: str, qa_pairs: List[Dict[str, str]], progress_callback) -> tuple:
        """Run local MLX LoRA/DoRA training and store adapter metadata in the vault."""
        progress_callback(60.0, "Starting local MLX training...")

        from advanced_vault.training import MLXTrainer, check_mlx_available

        if not check_mlx_available():
            raise ValueError("Local MLX training requires Apple Silicon MLX runtime (pip install mlx mlx-lm)")

        # Keep queue jobs responsive on laptops.
        qa_pairs = qa_pairs[: min(len(qa_pairs), 100)]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{Path(filename).stem}_{timestamp}"
        adapter_name = "".join(c if (c.isalnum() or c in {"-", "_"}) else "_" for c in base_name).strip("_")
        output_dir = self.vault_path / "local_adapters"

        trainer = MLXTrainer(
            output_dir=str(output_dir),
            config={
                "epochs": 2,
                "batch_size": 2,
                "max_seq_length": 512,
                "use_dora": True,
            },
        )

        def _local_progress(progress: float, message: str):
            # Map trainer's 0..1 progress to queue phase segment 60..95.
            mapped = 60.0 + (max(0.0, min(progress, 1.0)) * 35.0)
            progress_callback(mapped, message)

        training_result = trainer.train_from_qa_pairs(
            qa_pairs=qa_pairs,
            adapter_name=adapter_name,
            progress_callback=_local_progress,
        )

        adapter_id = f"local:{adapter_name}"
        encryption_key_hex = os.urandom(32).hex()

        entry_tags = [
            "data_type:knowledge",
            "source:pdf",
            "training_mode:local",
            "training_status:completed",
            f"local_adapter:{adapter_name}",
        ]
        self._store_or_update_knowledge_entry(
            filename=filename,
            adapter_id=adapter_id,
            tags=entry_tags,
            description=(
                f"Local MLX adapter trained from {filename}. "
                f"Path: {training_result.adapter_path}. "
                f"Examples: {training_result.num_examples}. "
                f"Final loss: {training_result.final_loss:.4f}"
            ),
        )

        progress_callback(100.0, "Local training complete")
        return adapter_id, encryption_key_hex
    
    def _refresh_library_view(self):
        """Refresh the library view UI."""
        if self.current_view == "library":
            self.show_library_view()
    
    def show_library_view(self):
        """Show the Knowledge Library with training queue and folder watching."""
        self.current_view = "library"
        self._stop_landing_status_polling()  # Stop landing page polling
        
        # Ensure main UI layout exists (secrets_list is created by build_ui)
        if not hasattr(self, 'secrets_list') or self.secrets_list is None:
            self.build_ui()
        
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
        
        # Create multi-file picker (must be added to overlay before use)
        pickers_added = False
        if not hasattr(self, 'multi_file_picker') or self.multi_file_picker is None:
            self.multi_file_picker = ft.FilePicker(
                on_result=self._on_multi_files_selected
            )
            self.page.overlay.append(self.multi_file_picker)
            pickers_added = True
        
        # Create folder picker
        if not hasattr(self, 'folder_picker') or self.folder_picker is None:
            self.folder_picker = ft.FilePicker(
                on_result=self._on_folder_selected
            )
            self.page.overlay.append(self.folder_picker)
            pickers_added = True
        
        # CRITICAL: Update page after adding pickers to overlay
        if pickers_added:
            self.page.update()
        
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
                            on_click=self._on_add_files_click,
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                        ),
                        ft.ElevatedButton(
                            "📂 Watch Folder",
                            icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                            on_click=self._on_watch_folder_click,
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
    
    def _on_add_files_click(self, e):
        """Handle Add Files button click with macOS fallback."""
        import platform
        
        if platform.system() == "Darwin":
            # Use macOS native file picker as it's more reliable than Flet's
            try:
                import subprocess
                
                # AppleScript to open multi-file selection dialog
                script = '''
                tell application "System Events"
                    activate
                end tell
                set selectedFiles to choose file of type {"pdf"} with prompt "Select PDF files to add to queue" with multiple selections allowed
                set filePaths to {}
                repeat with aFile in selectedFiles
                    set end of filePaths to POSIX path of aFile
                end repeat
                return filePaths as text
                '''
                
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout for file selection
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    # Parse comma-separated paths
                    paths = result.stdout.strip().split(", ")
                    
                    # Create fake FilePickerResultEvent
                    class FakeFile:
                        def __init__(self, path):
                            self.path = path.strip()
                            self.name = Path(path.strip()).name
                    
                    class FakeEvent:
                        def __init__(self, files):
                            self.files = files
                    
                    files = [FakeFile(p) for p in paths if p.strip()]
                    if files:
                        self._on_multi_files_selected(FakeEvent(files))
                    return
                    
            except Exception as ex:
                logger.debug(f"macOS native picker failed: {ex}")
        
        # Fallback to Flet FilePicker
        try:
            self.multi_file_picker.pick_files(
                allow_multiple=True,
                allowed_extensions=["pdf"],
            )
        except Exception as ex:
            logger.error(f"File picker error: {ex}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Could not open file picker: {ex}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def _on_watch_folder_click(self, e):
        """Handle Watch Folder button click with macOS fallback."""
        import platform
        
        if platform.system() == "Darwin":
            # Use macOS native folder picker
            try:
                import subprocess
                
                script = '''
                tell application "System Events"
                    activate
                end tell
                set selectedFolder to choose folder with prompt "Select folder to watch for PDFs"
                return POSIX path of selectedFolder
                '''
                
                result = subprocess.run(
                    ['osascript', '-e', script],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    folder_path = result.stdout.strip()
                    
                    # Create fake FilePickerResultEvent
                    class FakeEvent:
                        def __init__(self, path):
                            self.path = path
                    
                    self._on_folder_selected(FakeEvent(folder_path))
                    return
                    
            except Exception as ex:
                logger.debug(f"macOS native folder picker failed: {ex}")
        
        # Fallback to Flet FilePicker
        try:
            self.folder_picker.get_directory_path()
        except Exception as ex:
            logger.error(f"Folder picker error: {ex}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ Could not open folder picker: {ex}"),
                bgcolor=LightTheme.ACCENT_ERROR,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
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
