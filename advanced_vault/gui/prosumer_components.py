"""
Prosumer GUI Components for Enclave

Provides consumer-friendly UI components for:
- Document upload with auto-categorization
- One-click adapter training
- Vault category management
- Adapter backup/restore
- Onboarding flow

Designed to integrate with the existing Flet-based vault_app.py.
"""

import flet as ft

try:
    from light_theme import LightTheme
except ImportError:
    from .light_theme import LightTheme
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from advanced_vault.prosumer.vault_categories import (
    VaultCategory,
    list_categories,
    get_category_by_id,
)
from advanced_vault.prosumer.adapter_presets import (
    AdapterPreset,
    get_preset_for_category,
    list_presets,
)
from advanced_vault.prosumer.document_classifier import (
    DocumentClassifier,
    ClassificationResult,
)
from advanced_vault.prosumer.adapter_backup import (
    AdapterBackupManager,
    BackupManifest,
    BackupFormat,
)

logger = logging.getLogger(__name__)


# --- Color Palette (matches existing light theme) ---


class VaultCategoryCard(ft.Card):
    """Card displaying a vault category with stats and actions."""
    
    def __init__(
        self,
        category: VaultCategory,
        document_count: int = 0,
        adapter_status: str = "none",  # none, training, ready, error
        on_upload: Optional[Callable] = None,
        on_train: Optional[Callable] = None,
        on_open: Optional[Callable] = None,
    ):
        self.category = category
        self.document_count = document_count
        self.adapter_status = adapter_status
        self.on_upload = on_upload
        self.on_train = on_train
        self.on_open = on_open
        
        super().__init__(
            content=ft.Container(
                content=self._build_content(),
                padding=16,
                border_radius=12,
            ),
            elevation=2,
        )
    
    def _build_content(self) -> ft.Column:
        # Status indicator
        status_colors = {
            "none": "#9E9E9E",
            "training": LightTheme.ACCENT_WARNING,
            "ready": LightTheme.ACCENT_SUCCESS,
            "error": LightTheme.ACCENT_ERROR,
        }
        status_labels = {
            "none": "No adapter",
            "training": "Training...",
            "ready": "Adapter ready",
            "error": "Training failed",
        }
        
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            category.icon,
                            size=32,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    category.name,
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=category.color,
                                ),
                                ft.Text(
                                    category.description,
                                    size=12,
                                    color="#616161",
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            expand=True,
                            spacing=2,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Divider(height=8, color="transparent"),
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.DESCRIPTION, size=16, color="#616161"),
                                ft.Text(
                                    f"{self.document_count} documents",
                                    size=13,
                                    color="#616161",
                                ),
                            ],
                            spacing=4,
                        ),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Container(
                                        width=8,
                                        height=8,
                                        bgcolor=status_colors.get(self.adapter_status, "#9E9E9E"),
                                        border_radius=4,
                                    ),
                                    ft.Text(
                                        status_labels.get(self.adapter_status, "Unknown"),
                                        size=12,
                                        color=status_colors.get(self.adapter_status, "#9E9E9E"),
                                    ),
                                ],
                                spacing=6,
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            border_radius=12,
                            bgcolor=f"{status_colors.get(self.adapter_status, '#9E9E9E')}20",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(height=12, color="transparent"),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Upload",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=self.on_upload,
                            style=ft.ButtonStyle(
                                color=LightTheme.TEXT_PRIMARY,
                                bgcolor="#E0E0E0",
                            ),
                        ),
                        ft.ElevatedButton(
                            "Train AI",
                            icon=ft.Icons.MODEL_TRAINING,
                            on_click=self.on_train,
                            style=ft.ButtonStyle(
                                color="white",
                                bgcolor=category.color,
                            ),
                            disabled=self.document_count < category.min_documents_for_training,
                        ),
                    ],
                    spacing=8,
                ),
            ],
            spacing=0,
        )


class OnboardingFlow(ft.Column):
    """Step-by-step onboarding for new prosumer users."""
    
    def __init__(self, on_complete: Optional[Callable] = None):
        self.on_complete = on_complete
        self.current_step = 0
        self.selected_categories: List[str] = []
        self.uploaded_files: List[str] = []
        
        super().__init__(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
        self._build_step()
    
    def _build_step(self):
        self.controls.clear()
        
        if self.current_step == 0:
            self._build_welcome_step()
        elif self.current_step == 1:
            self._build_category_selection_step()
        elif self.current_step == 2:
            self._build_upload_step()
        elif self.current_step == 3:
            self._build_training_step()
        elif self.current_step == 4:
            self._build_complete_step()
        
        self.update()
    
    def _build_welcome_step(self):
        self.controls.extend([
            ft.Icon(ft.Icons.SECURITY, size=64, color=LightTheme.ACCENT_PRIMARY),
            ft.Text(
                "Welcome to Enclave",
                size=28,
                weight=ft.FontWeight.BOLD,
                color=LightTheme.TEXT_PRIMARY,
            ),
            ft.Text(
                "Your personal AI that learns from your documents \u2014\n"
                "and keeps everything encrypted on your device.",
                size=16,
                color="#616161",
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Divider(height=24, color="transparent"),
            ft.ElevatedButton(
                "Get Started",
                icon=ft.Icons.ARROW_FORWARD,
                on_click=lambda _: self._next_step(),
                style=ft.ButtonStyle(
                    color="white",
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                    padding=ft.padding.symmetric(horizontal=32, vertical=16),
                ),
            ),
        ])
    
    def _build_category_selection_step(self):
        category_chips = []
        for category in list_categories():
            category_chips.append(
                ft.Chip(
                    label=ft.Text(f"{category.icon} {category.name}"),
                    bgcolor=f"{category.color}15",
                    selected_color=category.color,
                    check_color="white",
                    on_select=lambda e, cid=category.id: self._toggle_category(cid, e.data),
                )
            )
        
        self.controls.extend([
            ft.Text(
                "What do you want to protect?",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Select the types of documents you'll store in Enclave.",
                size=14,
                color="#616161",
            ),
            ft.Divider(height=16, color="transparent"),
            ft.Wrap(
                category_chips,
                spacing=8,
                run_spacing=8,
                alignment=ft.WrapAlignment.CENTER,
            ),
            ft.Divider(height=24, color="transparent"),
            ft.ElevatedButton(
                "Continue",
                on_click=lambda _: self._next_step(),
                disabled=len(self.selected_categories) == 0,
                style=ft.ButtonStyle(
                    color="white",
                    bgcolor=LightTheme.ACCENT_PRIMARY,
                ),
            ),
        ])
    
    def _build_upload_step(self):
        category_names = [
            get_category_by_id(cid).name for cid in self.selected_categories
        ]
        
        self.controls.extend([
            ft.Text(
                "Upload your first documents",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                f"We'll automatically organize them into your {', '.join(category_names)} vaults.",
                size=14,
                color="#616161",
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Divider(height=16, color="transparent"),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.CLOUD_UPLOAD, size=48, color="#9E9E9E"),
                        ft.Text(
                            "Drag & drop files here",
                            size=16,
                            color="#9E9E9E",
                        ),
                        ft.Text(
                            "or click to browse",
                            size=12,
                            color="#BDBDBD",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                width=400,
                height=200,
                bgcolor="#FAFAFA",
                border=ft.border.all(2, "#E0E0E0", dash_pattern=[6, 3]),
                border_radius=12,
                alignment=ft.alignment.center,
            ),
            ft.Divider(height=16, color="transparent"),
            ft.ElevatedButton(
                "Skip for now",
                on_click=lambda _: self._next_step(),
                style=ft.ButtonStyle(
                    color="#616161",
                    bgcolor="transparent",
                ),
            ),
        ])
    
    def _build_training_step(self):
        self.controls.extend([
            ft.Text(
                "Train your personal AI?",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Your documents stay on your device. Only learned patterns \u2014\n"
                "encrypted as a 'weight delta vault adapter' \u2014 are saved.",
                size=14,
                color="#616161",
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Divider(height=24, color="transparent"),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.PSYCHOLOGY, size=48, color=LightTheme.ACCENT_PRIMARY),
                        ft.Text(
                            "Estimated time: 5-15 minutes",
                            size=14,
                            color="#616161",
                        ),
                        ft.Text(
                            "Your device may get warm. This is normal.",
                            size=12,
                            color="#9E9E9E",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=24,
                bgcolor="#E3F2FD",
                border_radius=12,
            ),
            ft.Divider(height=24, color="transparent"),
            ft.Row(
                [
                    ft.OutlinedButton(
                        "Skip",
                        on_click=lambda _: self._next_step(),
                    ),
                    ft.ElevatedButton(
                        "Train My AI",
                        icon=ft.Icons.MODEL_TRAINING,
                        on_click=lambda _: self._start_training(),
                        style=ft.ButtonStyle(
                            color="white",
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                        ),
                    ),
                ],
                spacing=12,
            ),
        ])
    
    def _build_complete_step(self):
        self.controls.extend([
            ft.Icon(ft.Icons.CHECK_CIRCLE, size=64, color=LightTheme.ACCENT_SUCCESS),
            ft.Text(
                "Your Enclave is ready",
                size=28,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "You can now chat with your personal AI about your documents.\n"
                "Everything stays encrypted and local.",
                size=14,
                color="#616161",
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Divider(height=24, color="transparent"),
            ft.ElevatedButton(
                "Start Chatting",
                icon=ft.Icons.CHAT,
                on_click=lambda _: self._complete(),
                style=ft.ButtonStyle(
                    color="white",
                    bgcolor=LightTheme.ACCENT_SUCCESS,
                    padding=ft.padding.symmetric(horizontal=32, vertical=16),
                ),
            ),
        ])
    
    def _toggle_category(self, category_id: str, selected: bool):
        if selected and category_id not in self.selected_categories:
            self.selected_categories.append(category_id)
        elif not selected and category_id in self.selected_categories:
            self.selected_categories.remove(category_id)
        self._build_step()
    
    def _next_step(self):
        self.current_step += 1
        self._build_step()
    
    def _start_training(self):
        # Would trigger actual training via LocalTrainingManager
        self._next_step()
    
    def _complete(self):
        if self.on_complete:
            self.on_complete()


class OneClickTrainingPanel(ft.Column):
    """Panel for one-click adapter training from vault documents."""
    
    def __init__(
        self,
        category: VaultCategory,
        document_count: int,
        on_train: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.category = category
        self.document_count = document_count
        self.on_train = on_train
        self.is_training = False
        self.progress = 0.0
        
        super().__init__(
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )
        self._build()
    
    def _build(self):
        preset = get_preset_for_category(self.category.id)
        
        self.controls = [
            ft.Text(
                f"Train {preset.name}",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=self.category.color,
            ),
            ft.Text(
                f"An AI that understands your {self.category.name.lower()} documents.\n"
                f"Trained on {self.document_count} documents using {preset.training_method.value.upper()}.",
                size=14,
                color="#616161",
            ),
            ft.Divider(height=8, color="transparent"),
            
            # Preset info card
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Training Configuration", weight=ft.FontWeight.BOLD),
                            ft.Divider(height=4, color="transparent"),
                            _info_row("Base Model", preset.base_model),
                            _info_row("Method", preset.training_method.value.upper()),
                            _info_row("LoRA Rank", str(preset.lora_rank)),
                            _info_row("Epochs", str(preset.num_epochs)),
                            _info_row("Est. Time", f"~{preset.estimate_time(self.document_count)} min"),
                        ],
                        spacing=8,
                    ),
                    padding=16,
                ),
                elevation=1,
            ),
            
            # Safety info
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SECURITY, size=20, color=LightTheme.ACCENT_PRIMARY),
                        ft.Text(
                            "Your documents never leave this device. Only encrypted learned weights are saved.",
                            size=12,
                            color="#616161",
                            expand=True,
                        ),
                    ],
                    spacing=8,
                ),
                padding=12,
                bgcolor="#E3F2FD",
                border_radius=8,
            ),
            
            # Training button or progress
            self._build_action_area(),
        ]
    
    def _build_action_area(self) -> ft.Control:
        if self.is_training:
            return ft.Column(
                [
                    ft.ProgressBar(value=self.progress, color=self.category.color),
                    ft.Text(
                        f"Training... {int(self.progress * 100)}%",
                        size=14,
                        color="#616161",
                    ),
                ],
                spacing=8,
            )
        
        can_train = self.document_count >= self.category.min_documents_for_training
        
        return ft.ElevatedButton(
            f"Train {get_preset_for_category(self.category.id).name}",
            icon=ft.Icons.MODEL_TRAINING,
            on_click=self._on_train_click,
            disabled=not can_train,
            style=ft.ButtonStyle(
                color="white",
                bgcolor=self.category.color if can_train else "#BDBDBD",
                padding=ft.padding.symmetric(horizontal=24, vertical=16),
            ),
        )
    
    def _on_train_click(self, _):
        if self.on_train:
            self.on_train(self.category.id, {})
    
    def update_progress(self, progress: float):
        """Update training progress (0.0-1.0)."""
        self.progress = progress
        self._build()
        self.update()


def _info_row(label: str, value: str) -> ft.Row:
    """Helper to build a label-value row."""
    return ft.Row(
        [
            ft.Text(label, size=13, color="#9E9E9E", width=100),
            ft.Text(value, size=13, color=LightTheme.TEXT_PRIMARY, expand=True),
        ],
        spacing=8,
    )


class AdapterBackupPanel(ft.Column):
    """Panel for backing up and restoring encrypted adapters."""
    
    def __init__(
        self,
        backup_manager: AdapterBackupManager,
        on_export: Optional[Callable] = None,
        on_import: Optional[Callable] = None,
    ):
        self.backup_manager = backup_manager
        self.on_export = on_export
        self.on_import = on_import
        
        super().__init__(
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )
        self._build()
    
    def _build(self):
        backups = self.backup_manager.list_backups()
        
        backup_list = []
        for backup in backups:
            backup_list.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.SHIELD, color=LightTheme.ACCENT_PRIMARY),
                    title=ft.Text(backup["filename"]),
                    subtitle=ft.Text(
                        f"{backup['size'] // 1024} KB \u00b7 {backup['modified'][:10]}"
                    ),
                    trailing=ft.PopupMenuButton(
                        items=[
                            ft.PopupMenuItem(text="Import", on_click=lambda e, p=backup["path"]: self._import_backup(p)),
                            ft.PopupMenuItem(text="Delete", on_click=lambda e, p=backup["path"]: self._delete_backup(p)),
                        ]
                    ),
                )
            )
        
        if not backup_list:
            backup_list.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.BACKUP, size=48, color="#E0E0E0"),
                            ft.Text(
                                "No backups yet",
                                size=16,
                                color="#9E9E9E",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=48,
                    alignment=ft.alignment.center,
                )
            )
        
        self.controls = [
            ft.Text(
                "Encrypted Adapter Backups",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Back up your trained adapters. Raw documents are never included \u2014\n"
                "only encrypted learned weights.",
                size=14,
                color="#616161",
            ),
            ft.Divider(height=8, color="transparent"),
            ft.Row(
                [
                    ft.ElevatedButton(
                        "Export Adapter",
                        icon=ft.Icons.UPLOAD,
                        on_click=lambda _: self.on_export() if self.on_export else None,
                    ),
                    ft.ElevatedButton(
                        "Import Adapter",
                        icon=ft.Icons.DOWNLOAD,
                        on_click=lambda _: self.on_import() if self.on_import else None,
                    ),
                ],
                spacing=12,
            ),
            ft.Divider(height=8, color="transparent"),
            ft.Card(
                content=ft.Column(backup_list, spacing=0),
                elevation=1,
            ),
        ]
    
    def _import_backup(self, path: str):
        try:
            adapter_path, manifest = self.backup_manager.import_adapter(path)
            # Show success
            pass
        except Exception as e:
            logger.error(f"Import failed: {e}")
    
    def _delete_backup(self, path: str):
        try:
            Path(path).unlink()
            self._build()
            self.update()
        except Exception as e:
            logger.error(f"Delete failed: {e}")


def build_vaults_grid(
    classifier: DocumentClassifier,
    category_counts: Dict[str, int],
    adapter_statuses: Dict[str, str],
    on_upload: Callable[[str], None],
    on_train: Callable[[str], None],
) -> ft.GridView:
    """Build a grid of vault category cards."""
    cards = []
    for category in list_categories():
        cards.append(
            VaultCategoryCard(
                category=category,
                document_count=category_counts.get(category.id, 0),
                adapter_status=adapter_statuses.get(category.id, "none"),
                on_upload=lambda e, cid=category.id: on_upload(cid),
                on_train=lambda e, cid=category.id: on_train(cid),
            )
        )
    
    return ft.GridView(
        controls=cards,
        max_extent=350,
        child_aspect_ratio=1.2,
        spacing=16,
        run_spacing=16,
        padding=16,
        expand=True,
    )
