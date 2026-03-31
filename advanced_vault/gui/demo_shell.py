"""Figma-inspired Enclave shell views extracted from the main app module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import flet as ft

try:
    from light_theme import LightTheme
except ImportError:  # pragma: no cover - package import fallback
    from .light_theme import LightTheme


def show_workspace_view(app: Any, initial_question: Optional[str] = None) -> None:
    """Render the primary Private Model workspace."""
    app.current_view = "agent_chat"
    app._ensure_chat_messages_loaded()

    profile = app._ensure_private_model_profile()
    profile_status = app._get_private_model_status()
    local_model_status = app._get_local_private_model_status()
    documents = app._get_private_model_documents(limit=10)
    module_statuses = app._update_module_status_snapshots()

    app.page.clean()
    chat_input = ft.TextField(
        hint_text=(
            f"Ask about your {profile_status.get('document_count', 0)} file(s)..."
            if profile_status.get("document_count", 0) > 0
            else "Ask about your files..."
        ),
        expand=True,
        border_radius=14,
        border_color=LightTheme.BORDER_COLOR,
        focused_border_color=LightTheme.ACCENT_PRIMARY,
        content_padding=ft.padding.symmetric(horizontal=16, vertical=14),
        on_submit=lambda e: app._send_chat_message(
            e,
            chat_input,
            [],
            mode_override="local",
            allow_cloud_fallback=False,
        ),
    )
    app.chat_input = chat_input

    vault_runtime_status = module_statuses.get("vault", {}).get("details", {})
    wallet_runtime_status = module_statuses.get("wallet", {}).get("details", {})
    _parser_backend = vault_runtime_status.get("parser_backend", app._current_parser_backend())

    stats_chips = ft.Row(
        [
            app._simple_metric_card(
                "Files",
                str(vault_runtime_status.get("document_count", profile_status.get("document_count", 0))),
            ),
            app._simple_metric_card(
                "Approvals",
                str(wallet_runtime_status.get("pending_count", 0)),
            ),
        ],
        spacing=12,
        wrap=True,
    )

    app.workspace_empty_state = ft.Container(
        visible=not bool(app.chat_messages),
        padding=ft.padding.only(bottom=8),
        content=ft.Column(
            [
                ft.Text(
                    "Add a file to start",
                    size=24,
                    weight=ft.FontWeight.W_600,
                    color=LightTheme.TEXT_PRIMARY,
                ),
                ft.Text(
                    ("Ready to answer from " + ", ".join(doc.get("name", "Untitled") for doc in documents[:3]))
                    if documents
                    else "PDFs, notes, and folders stay on this Mac.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Row(
                    [
                        ft.ElevatedButton(
                            "Add Files",
                            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                            on_click=app._open_private_files_picker,
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                padding=ft.padding.symmetric(horizontal=16, vertical=14),
                                shape=ft.RoundedRectangleBorder(radius=12),
                            ),
                        ),
                        ft.OutlinedButton(
                            "Add Folder",
                            icon=ft.Icons.DRIVE_FOLDER_UPLOAD_ROUNDED,
                            on_click=app._open_private_folder_picker,
                            style=ft.ButtonStyle(
                                color=LightTheme.TEXT_PRIMARY,
                                side=ft.BorderSide(1, LightTheme.BORDER_COLOR),
                                padding=ft.padding.symmetric(horizontal=16, vertical=14),
                                shape=ft.RoundedRectangleBorder(radius=12),
                            ),
                        ),
                    ],
                    spacing=12,
                    wrap=True,
                ),
            ],
            spacing=12,
        ),
    )

    chat_messages_list = ft.ListView(
        spacing=12,
        auto_scroll=True,
        height=320,
    )
    for msg in app.chat_messages[-8:]:
        chat_messages_list.controls.append(
            app._create_chat_bubble(
                msg.get("role", "assistant"),
                msg.get("content", ""),
                msg.get("document"),
                msg.get("sources"),
            )
        )
    if not app.chat_messages:
        chat_messages_list.controls.append(
            ft.Container(
                content=ft.Text(
                    "Ready for your first prompt.",
                    size=13,
                    color=LightTheme.TEXT_MUTED,
                ),
                padding=ft.padding.symmetric(horizontal=4, vertical=2),
            )
        )

    app.chat_messages_list = chat_messages_list
    app.trained_adapters = []
    quick_actions: List[ft.Control] = [
        ft.OutlinedButton(
            "Summarize files",
            on_click=lambda e: app._quick_ask("Summarize my files", []),
        ),
        ft.OutlinedButton(
            "Find key facts",
            on_click=lambda e: app._quick_ask("Find key facts in my files", []),
        ),
    ]
    if wallet_runtime_status.get("pending_count", 0):
        quick_actions.append(
            ft.OutlinedButton(
                "Review approvals",
                on_click=lambda e: app._quick_ask("What payments are waiting for approval?", []),
            )
        )

    model_setup_card = None
    if not local_model_status.get("available"):
        model_setup_card = app._build_surface_card(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                app.tr("local_model.download.title"),
                                size=16,
                                weight=ft.FontWeight.W_600,
                                color=LightTheme.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                app.tr("local_model.download.required"),
                                size=12,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Text(
                                local_model_status.get("display_name", profile_status.get("model_name", "Local Model")),
                                size=11,
                                color=LightTheme.TEXT_MUTED,
                            ),
                        ],
                        spacing=6,
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        app.tr("local_model.download.cta"),
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda e: app._setup_local_private_model_with_progress(),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            padding=ft.padding.symmetric(horizontal=16, vertical=14),
                            shape=ft.RoundedRectangleBorder(radius=12),
                        ),
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Text("Private Chat", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Ask questions about files stored on this Mac.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                model_setup_card if model_setup_card is not None else ft.Container(),
                stats_chips,
                ft.Container(
                    bgcolor=LightTheme.BG_ELEVATED,
                    border=ft.border.all(1, LightTheme.BORDER_COLOR),
                    border_radius=18,
                    padding=20,
                    content=ft.Column(
                        [
                            app.workspace_empty_state,
                            chat_messages_list,
                        ],
                        spacing=16,
                    ),
                ),
                ft.Row(
                    quick_actions,
                    spacing=8,
                    wrap=True,
                ),
                ft.Row(
                    [
                        chat_input,
                        ft.ElevatedButton(
                            "Send",
                            on_click=lambda e: app._send_chat_message(
                                e,
                                chat_input,
                                [],
                                mode_override="local",
                                allow_cloud_fallback=False,
                            ),
                            style=ft.ButtonStyle(
                                bgcolor=LightTheme.ACCENT_PRIMARY,
                                color="white",
                                padding=ft.padding.symmetric(horizontal=18, vertical=16),
                                shape=ft.RoundedRectangleBorder(radius=12),
                            ),
                        ),
                    ],
                    spacing=12,
                ),
            ],
            spacing=12,
        ),
    )

    app._render_primary_shell(-1, content)

    if initial_question:
        chat_input.value = initial_question
        app.page.update()
        app._send_chat_message(
            None,
            chat_input,
            [],
            mode_override="local",
            allow_cloud_fallback=False,
        )


def show_library_view(app: Any) -> None:
    """Render the Figma-aligned Library view."""
    app.current_view = "library_shell"
    app.page.clean()

    profile = app._ensure_private_model_profile()
    profiles = app._get_private_model_profiles()
    documents = app._get_private_model_documents(limit=100)

    adapter_rows: List[ft.Control] = []
    for current_profile in profiles:
        for adapter in current_profile.wdva_adapters[:4]:
            adapter_name = (
                adapter.get("name")
                or adapter.get("adapter_name")
                or adapter.get("adapter_id")
                or "WDVA Adapter"
            )
            adapter_rows.append(
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                        width=40,
                                        height=40,
                                        border_radius=12,
                                        bgcolor=LightTheme.ACCENT_BLUE_LIGHT,
                                        alignment=ft.alignment.center,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(adapter_name, size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                            app._build_status_badge("Active", color=LightTheme.ACCENT_SUCCESS, tint=LightTheme.ACCENT_SUCCESS + "12"),
                                        ],
                                        spacing=6,
                                        expand=True,
                                    ),
                                ],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            ft.Text(
                                adapter.get("description") or f"Private adaptive layer attached to {current_profile.name}.",
                                size=12,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Row(
                                [
                                    ft.Text(current_profile.name, size=11, color=LightTheme.TEXT_MUTED),
                                    ft.Text("·", size=11, color=LightTheme.TEXT_MUTED),
                                    ft.Text("MLX DoRA layer", size=11, color=LightTheme.TEXT_MUTED),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=12,
                    )
                )
            )

    if not adapter_rows:
        adapter_rows.append(
            app._build_surface_card(
                ft.Column(
                    [
                        ft.Text("No WDVA adapters yet", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        ft.Text(
                            "Adapters will appear here once you add personalization layers to a profile.",
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                    ],
                    spacing=8,
                )
            )
        )

    document_summaries: List[ft.Control] = []

    for doc in documents[:12]:
        source_path = doc.get("source_path") or ""
        source_label = Path(source_path).parent.name if source_path else "Local import"
        doc_type = Path(doc.get("name", "")).suffix.lstrip(".").upper() or "FILE"
        document_summaries.append(
            ft.Text(
                f"{doc.get('name', 'Unknown')}  •  {doc_type}  •  {doc.get('chunk_count', 0)} chunks  •  {source_label or 'Local import'}",
                size=12,
                color=LightTheme.TEXT_SECONDARY,
            )
        )

    if not document_summaries:
        document_summaries.append(
            ft.Text("No documents indexed. Add files or a folder to populate your library.", size=12, color=LightTheme.TEXT_SECONDARY)
        )

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Text("Library", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Your knowledge sources and adaptive personalization layers.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.ElevatedButton(
                    "Create Profile",
                    icon=ft.Icons.ADD_ROUNDED,
                    on_click=lambda e: app._open_create_profile_dialog(),
                    style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white"),
                ),
                ft.TextField(
                    hint_text="Search documents, adapters...",
                    prefix_icon=ft.Icons.SEARCH_ROUNDED,
                    bgcolor=LightTheme.BG_ELEVATED,
                    border_color=LightTheme.BORDER_COLOR,
                    focused_border_color=LightTheme.ACCENT_PRIMARY,
                    border_radius=12,
                    content_padding=ft.padding.symmetric(horizontal=12, vertical=12),
                    width=360,
                ),
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.LAYERS_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                    ft.Text("WDVA Adapters (MLX DoRA)", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                    app._build_status_badge(
                                        f"{sum(len(item.wdva_adapters) for item in profiles)} Active",
                                        color=LightTheme.ACCENT_PRIMARY,
                                        tint=LightTheme.ACCENT_BLUE_LIGHT,
                                    ),
                                    ft.Container(expand=True),
                                ],
                                spacing=10,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                "Private personalization layers that adapt to your knowledge and style without modifying the base model.",
                                size=13,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.ResponsiveRow(
                                [ft.Container(control, col={"sm": 12, "md": 6}) for control in adapter_rows],
                                run_spacing=12,
                                spacing=12,
                            ),
                        ],
                        spacing=16,
                    )
                ),
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Text("Documents & Folders", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(f"{len(documents)} indexed items in {profile.name}. Use Workspace to add more files or folders.", size=12, color=LightTheme.TEXT_SECONDARY),
                            ft.Column(document_summaries, spacing=10),
                        ],
                        spacing=16,
                    )
                ),
            ],
            spacing=20,
        ),
    )

    app._render_primary_shell(0, content)


def show_connections_view(app: Any) -> None:
    """Render the Figma-aligned Connections view."""
    app.current_view = "connections_shell"
    app.page.clean()

    connection_clients = app._update_integration_client_statuses()
    config = app.mcp_setup.generate_mcp_config() if app.mcp_setup else {
        "mcpServers": {
            "enclave": {
                "command": "python",
                "args": ["-m", "advanced_vault.mcp_server"],
                "env": {"VAULT_PATH": str(app.vault_path)},
            }
        }
    }
    servers = config.get("mcpServers") if isinstance(config, dict) else None
    if not isinstance(servers, dict) or not servers:
        servers = {
            "enclave": {
                "command": "python",
                "args": ["-m", "advanced_vault.mcp_server"],
                "env": {"VAULT_PATH": str(app.vault_path)},
            }
        }
    server_name, server_config = next(iter(servers.items()))
    command = server_config.get("command", "python")
    args = server_config.get("args", ["-m", "advanced_vault.mcp_server"])
    env_payload = server_config.get("env", {"VAULT_PATH": str(app.vault_path)})

    def _client_status_badge(status: str) -> ft.Container:
        normalized = (status or "offline").lower()
        if normalized == "active":
            return app._build_status_badge("Connected", color=LightTheme.ACCENT_SUCCESS, tint=LightTheme.ACCENT_SUCCESS + "12")
        if normalized == "ready":
            return app._build_status_badge("Ready", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT)
        return app._build_status_badge("Offline", color=LightTheme.TEXT_MUTED, tint=LightTheme.BG_SUBTLE)

    client_cards: List[ft.Control] = []
    for client_id, client in connection_clients.items():
        configure_action = {
            "claude": app._configure_claude_mcp,
            "cursor": app._configure_cursor_mcp,
            "openclaw": app._copy_mcp_json,
        }.get(client_id, app._copy_mcp_json)
        allowed_permissions = [
            permission
            for permission, enabled in client.get("permissions", {}).items()
            if enabled
        ]
        client_cards.append(
            app._build_surface_card(
                ft.Column(
                    [
                        ft.Text(client["name"], size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        _client_status_badge(client.get("status", "offline")),
                        ft.Text(f"Last active: {client.get('last_seen', 'Unknown')}", size=12, color=LightTheme.TEXT_MUTED),
                        ft.Text(
                            "Allowed tools: " + (", ".join(allowed_permissions) if allowed_permissions else "None"),
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Row(
                            [
                                ft.TextButton(
                                    "Revoke Access",
                                    on_click=lambda e, cid=client_id: app._revoke_connection_access(cid),
                                    style=ft.ButtonStyle(color=LightTheme.ACCENT_ERROR),
                                ),
                                ft.TextButton(
                                    "Configure",
                                    on_click=lambda e, action=configure_action: action(),
                                    style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                                ),
                            ],
                            spacing=12,
                        ),
                    ],
                    spacing=10,
                ),
                padding=16,
            )
        )

    config_lines = [
        "{",
        '  "mcpServers": {',
        f'    "{server_name}": {{',
        f'      "command": "{command}",',
        f'      "args": {json.dumps(args)},',
        f'      "env": {json.dumps(env_payload)}',
        "    }",
        "  }",
        "}",
    ]

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Text("MCP Integrations", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Manage which external AI agents can connect to your local Enclave instance.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Text("Local MCP Server", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            app._build_status_badge("Running", color=LightTheme.ACCENT_SUCCESS, tint=LightTheme.ACCENT_SUCCESS + "12"),
                            ft.Text("Listening on stdio through the local Enclave runtime.", size=13, color=LightTheme.TEXT_SECONDARY),
                            ft.Row(
                                [
                                    app._simple_metric_card("Server", server_name),
                                    app._simple_metric_card("Command", Path(command).name),
                                    app._simple_metric_card("Args", str(len(args))),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                        ],
                        spacing=12,
                    )
                ),
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Text("Connect a New Client", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(
                                "Copy this MCP configuration into Claude Desktop, Cursor, or OpenClaw to attach them to Enclave.",
                                size=13,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        ft.Text(line, size=12, color=LightTheme.TEXT_PRIMARY, font_family="monospace")
                                        for line in config_lines
                                    ],
                                    spacing=4,
                                    tight=True,
                                ),
                                padding=ft.padding.all(14),
                                bgcolor=LightTheme.BG_SUBTLE,
                                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                                border_radius=12,
                            ),
                            ft.Row(
                                [
                                    ft.OutlinedButton("Copy Config", on_click=lambda e: app._copy_mcp_json()),
                                    ft.OutlinedButton("Claude Desktop", on_click=lambda e: app._configure_claude_mcp()),
                                    ft.OutlinedButton("Cursor", on_click=lambda e: app._configure_cursor_mcp()),
                                    ft.OutlinedButton("OpenClaw", on_click=lambda e: app._copy_mcp_json()),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                        ],
                        spacing=14,
                    )
                ),
                ft.Text("Connected Clients", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_MUTED),
                ft.Column(client_cards, spacing=16),
            ],
            spacing=16,
        ),
    )

    app._render_primary_shell(1, content)


def show_security_view(app: Any) -> None:
    """Render the Figma-aligned Security view."""
    app.current_view = "security_shell"
    app.page.clean()

    shared_status = app._update_module_status_snapshots()
    vault_snapshot = shared_status.get("vault", {}).get("details", {})
    wallet_snapshot = shared_status.get("wallet", {}).get("details", {})
    kill_switch = app.enclave_runtime.get_kill_switch()
    recent_events = app.enclave_runtime.list_events(limit=8)
    pending_requests = app.wallet_service.list_pending_requests()

    def status_card(icon: str, title: str, badge: str, description: str, icon_color: str) -> ft.Container:
        return app._build_surface_card(
            ft.Column(
                [
                    ft.Container(
                        content=ft.Icon(icon, size=24, color=icon_color),
                        width=52,
                        height=52,
                        border_radius=16,
                        bgcolor=LightTheme.ACCENT_BLUE_LIGHT if icon_color != LightTheme.ACCENT_SUCCESS else LightTheme.ACCENT_SUCCESS + "12",
                        alignment=ft.alignment.center,
                    ),
                    ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                    app._build_status_badge(
                        badge,
                        color=icon_color,
                        tint=(LightTheme.ACCENT_BLUE_LIGHT if icon_color != LightTheme.ACCENT_SUCCESS else LightTheme.ACCENT_SUCCESS + "12"),
                    ),
                    ft.Text(description, size=12, color=LightTheme.TEXT_SECONDARY),
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    privacy_controls = app._build_surface_card(
        ft.Column(
            [
                ft.Text("Privacy Controls", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                app._privacy_control_row(
                    "Local-Only Processing",
                    "Private data stays on this device.",
                    value=True,
                    disabled=True,
                ),
                app._privacy_control_row(
                    "Encrypted Vault Storage",
                    "Files and context stay encrypted at rest.",
                    value=True,
                    disabled=True,
                ),
                app._privacy_control_row(
                    "Global Kill Switch",
                    "Stops sensitive vault and wallet actions.",
                    value=kill_switch.enabled,
                    disabled=False,
                    on_change=lambda e: app._set_global_kill_switch(bool(e.control.value)),
                ),
            ],
            spacing=0,
        )
    )

    access_cards = ft.ResponsiveRow(
        [
            ft.Container(
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                        width=40,
                                        height=40,
                                        border_radius=12,
                                        bgcolor=LightTheme.ACCENT_BLUE_LIGHT,
                                        alignment=ft.alignment.center,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text("Document Permissions", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                            ft.Text("Choose which files agents can use.", size=12, color=LightTheme.TEXT_SECONDARY),
                                        ],
                                        spacing=4,
                                        expand=True,
                                    ),
                                ],
                                spacing=12,
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        f"{vault_snapshot.get('document_count', 0)} documents · {vault_snapshot.get('profile_count', 0)} profiles",
                                        size=12,
                                        color=LightTheme.TEXT_MUTED,
                                    ),
                                    ft.Container(expand=True),
                                    ft.TextButton("Open Files", on_click=lambda e: app._show_library_view(), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=14,
                    )
                ),
                col={"sm": 12, "md": 6},
            ),
            ft.Container(
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Icon(ft.Icons.HISTORY_ROUNDED, size=18, color=LightTheme.ACCENT_PRIMARY),
                                        width=40,
                                        height=40,
                                        border_radius=12,
                                        bgcolor=LightTheme.ACCENT_BLUE_LIGHT,
                                        alignment=ft.alignment.center,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text("Audit Logging", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                            ft.Text("Review recent access decisions.", size=12, color=LightTheme.TEXT_SECONDARY),
                                        ],
                                        spacing=4,
                                        expand=True,
                                    ),
                                ],
                                spacing=12,
                            ),
                            ft.Row(
                                [
                                    ft.Text(f"{len(recent_events)} recent events loaded", size=12, color=LightTheme.TEXT_MUTED),
                                    ft.Container(expand=True),
                                    ft.TextButton("View Log", on_click=lambda e: app.show_settings_hub(active_tab="sheriff"), style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY)),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=14,
                    )
                ),
                col={"sm": 12, "md": 6},
            ),
        ],
        spacing=12,
        run_spacing=12,
    )

    activity_rows: List[ft.Control] = [
        ft.Container(
            content=ft.Row(
                [
                    ft.Text("Action", size=11, color=LightTheme.TEXT_MUTED, expand=4),
                    ft.Text("Resource", size=11, color=LightTheme.TEXT_MUTED, expand=5),
                    ft.Text("Status", size=11, color=LightTheme.TEXT_MUTED, expand=2),
                ],
                spacing=16,
            ),
            padding=ft.padding.symmetric(horizontal=18, vertical=12),
            bgcolor=LightTheme.BG_SUBTLE,
            border_radius=12,
        )
    ]

    for event in recent_events:
        decision = str(event.get("decision", "ALLOW"))
        status_color = (
            LightTheme.ACCENT_SUCCESS
            if decision in {"ALLOW", "ALLOW_WITH_LEASE", "APPROVED"}
            else (LightTheme.ACCENT_WARNING if decision == "PENDING" else LightTheme.ACCENT_ERROR)
        )
        activity_rows.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(
                            f"{event.get('module', 'system')} · {event.get('tool', 'event')}",
                            size=12,
                            color=LightTheme.TEXT_PRIMARY,
                            expand=4,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            str(event.get("summary") or event.get("resource") or "Local event"),
                            size=12,
                            color=LightTheme.TEXT_MUTED,
                            expand=5,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(decision.title(), size=12, color=status_color, expand=2),
                    ],
                    spacing=16,
                ),
                padding=ft.padding.symmetric(horizontal=18, vertical=14),
                border=ft.border.only(bottom=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
            )
        )

    pending_rows: List[ft.Control] = []
    for request in pending_requests[:6]:
        pending_rows.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text(request.merchant, size=12, color=LightTheme.TEXT_PRIMARY, expand=True),
                        ft.Text(f"${request.amount:.2f}", size=12, color=LightTheme.TEXT_SECONDARY),
                        ft.TextButton("Approve", on_click=lambda e, request_id=request.request_id: app._approve_wallet_request(request_id), style=ft.ButtonStyle(color=LightTheme.ACCENT_SUCCESS)),
                    ],
                    spacing=12,
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                border_radius=12,
            )
        )

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Text("Privacy", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Local by default. Sensitive actions need your approval.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(status_card(ft.Icons.MEMORY_ROUNDED, "Local AI", "On", "Runs on this Mac.", LightTheme.ACCENT_SUCCESS), col={"sm": 12, "md": 4}),
                        ft.Container(status_card(ft.Icons.LOCK_ROUNDED, "Vault", "Encrypted", "Files stay encrypted at rest.", LightTheme.ACCENT_PRIMARY), col={"sm": 12, "md": 4}),
                        ft.Container(status_card(ft.Icons.HUB_ROUNDED, "Guardrails", "On", "Checks private access and spend.", LightTheme.ACCENT_PRIMARY), col={"sm": 12, "md": 4}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                privacy_controls,
                access_cards,
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Payments Guardrails", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                    app._build_status_badge(
                                        "Frozen" if wallet_snapshot.get("frozen") else "Ready",
                                        color=(LightTheme.ACCENT_ERROR if wallet_snapshot.get("frozen") else LightTheme.ACCENT_SUCCESS),
                                        tint=((LightTheme.ACCENT_ERROR if wallet_snapshot.get("frozen") else LightTheme.ACCENT_SUCCESS) + "12"),
                                    ),
                                    ft.Container(expand=True),
                                ],
                                spacing=10,
                            ),
                            ft.Text("Prepaid limits for agent spend.", size=12, color=LightTheme.TEXT_SECONDARY),
                            ft.Row(
                                [
                                    app._stat_card("Envelopes", wallet_snapshot.get("envelope_count", 0), ft.Icons.ACCOUNT_BALANCE_WALLET_ROUNDED, LightTheme.ACCENT_PRIMARY),
                                    app._stat_card("Pending", wallet_snapshot.get("pending_count", 0), ft.Icons.SCHEDULE_ROUNDED, LightTheme.ACCENT_WARNING),
                                    app._stat_card("Transactions", wallet_snapshot.get("transaction_count", 0), ft.Icons.RECEIPT_LONG_ROUNDED, LightTheme.ACCENT_SUCCESS),
                                ],
                                spacing=16,
                            ),
                            ft.Row(
                                [
                                    ft.ElevatedButton("Create Wallet", icon=ft.Icons.ADD_CARD_ROUNDED, on_click=lambda e: (app._ensure_demo_wallet_envelope(), app._show_security_view()), style=ft.ButtonStyle(bgcolor=LightTheme.ACCENT_PRIMARY, color="white")),
                                    ft.OutlinedButton("$19 test", icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=lambda e: app._request_demo_wallet_purchase(19.0, "github.com", "Auto-approved demo spend")),
                                    ft.OutlinedButton("$85 approval", icon=ft.Icons.HOURGLASS_TOP_ROUNDED, on_click=lambda e: app._request_demo_wallet_purchase(85.0, "openai.com", "Pending approval demo spend")),
                                ],
                                spacing=10,
                                wrap=True,
                            ),
                            *(pending_rows or [ft.Text("No pending approvals.", size=12, color=LightTheme.TEXT_MUTED)]),
                        ],
                        spacing=14,
                    )
                ),
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Text("Recent decisions", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Container(
                                content=ft.Column(activity_rows, spacing=0),
                                border=ft.border.all(1, LightTheme.BORDER_COLOR),
                                border_radius=14,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            ),
                            ft.Row(
                                [
                                    ft.Container(expand=True),
                                    ft.TextButton(
                                        "View log",
                                        on_click=lambda e: app.show_settings_hub(active_tab="sheriff"),
                                        style=ft.ButtonStyle(color=LightTheme.ACCENT_PRIMARY),
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=16,
                    )
                ),
            ],
            spacing=20,
        ),
    )

    app._render_primary_shell(2, content)
