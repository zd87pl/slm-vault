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

try:
    from prosumer_components import build_vaults_grid
except ImportError:
    try:
        from .prosumer_components import build_vaults_grid
    except ImportError:
        build_vaults_grid = None

try:
    from shell_components import build_button, ButtonVariant
except ImportError:
    try:
        from .shell_components import build_button, ButtonVariant
    except ImportError:
        build_button = None
        ButtonVariant = None


def show_workspace_view(app: Any, initial_question: Optional[str] = None) -> None:
    """Render the primary private chat workspace."""
    app.current_view = "agent_chat"
    app._ensure_chat_messages_loaded()

    profile = app._ensure_private_model_profile()
    profile_status = app._get_private_model_status()
    local_model_status = app._get_local_private_model_status()
    documents = app._get_private_model_documents(limit=10)
    module_statuses = app._update_module_status_snapshots()

    app.page.clean()

    document_count = int(profile_status.get("document_count", 0) or 0)
    vault_runtime_status = module_statuses.get("vault", {}).get("details", {})
    runtime_document_count = int(vault_runtime_status.get("document_count", document_count) or 0)
    if runtime_document_count > 0:
        document_count = runtime_document_count

    chat_input = ft.TextField(
        hint_text=(
            f"Ask about your {document_count} file(s)..."
            if document_count > 0
            else "Ask about your files..."
        ),
        expand=True,
        border_radius=12,
        border_color="#e0e0e0",
        focused_border_color=LightTheme.ACCENT_PRIMARY,
        content_padding=ft.padding.symmetric(horizontal=16, vertical=14),
        text_size=13,
        cursor_color=LightTheme.ACCENT_PRIMARY,
        bgcolor=LightTheme.BG_ELEVATED,
        on_submit=lambda e: app._send_chat_message(
            e,
            chat_input,
            [],
            mode_override="local",
            allow_cloud_fallback=False,
        ),
    )
    app.chat_input = chat_input

    def _suggestion_chip(label: str, prompt: str) -> ft.Container:
        return ft.Container(
            ink=True,
            on_click=lambda e, question=prompt: app._quick_ask(question, []),
            border=ft.border.all(1, "#e0e0e0"),
            bgcolor="#fafafa",
            border_radius=999,
            padding=ft.padding.symmetric(horizontal=14, vertical=8),
            content=ft.Text(
                label,
                size=12,
                weight=ft.FontWeight.W_500,
                color="#3d3d3d",
            ),
        )

    has_messages = bool(app.chat_messages)
    ready_document_names = ", ".join(doc.get("name", "Untitled") for doc in documents[:3])
    app.workspace_empty_state = ft.Container(
        visible=not has_messages,
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Column(
            [
                ft.Text(
                    "Ask anything about your files",
                    size=22,
                    weight=ft.FontWeight.W_600,
                    color="#1a1a1a",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Your documents stay local. Answers come from your files — not the internet.",
                    size=13,
                    color="#6b6b6b",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Row(
                    [
                        _suggestion_chip("Summarize my files", "Summarize my files"),
                        _suggestion_chip("What's safe to share?", "What's safe to share from my files?"),
                        _suggestion_chip("Find key facts", "Find key facts in my files"),
                    ],
                    spacing=10,
                    wrap=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    run_spacing=10,
                ),
                ft.Text(
                    f"{document_count} file{'s' if document_count != 1 else ''} ready" + (f": {ready_document_names}" if ready_document_names else "") if document_count > 0 else "Add a file or folder to start a private conversation.",
                    size=12,
                    color=LightTheme.TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=14,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
    )

    chat_messages_list = ft.ListView(
        spacing=12,
        auto_scroll=True,
        expand=True,
        visible=has_messages,
        padding=ft.padding.only(right=4),
    )
    for msg in app.chat_messages:
        chat_messages_list.controls.append(
            app._create_chat_bubble(
                msg.get("role", "assistant"),
                msg.get("content", ""),
                msg.get("document"),
                msg.get("sources"),
            )
        )
    app.chat_messages_list = chat_messages_list
    app.trained_adapters = []

    model_setup_card = None
    if not local_model_status.get("available"):
        model_setup_card = ft.Container(
            padding=ft.padding.symmetric(horizontal=16, vertical=14),
            border=ft.border.all(1, LightTheme.BORDER_COLOR),
            border_radius=14,
            bgcolor=LightTheme.BG_ELEVATED,
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                app.tr("local_model.download.title"),
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color="#1a1a1a",
                            ),
                            ft.Text(
                                app.tr("local_model.download.required"),
                                size=12,
                                color="#6b6b6b",
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.ElevatedButton(
                        app.tr("local_model.download.cta"),
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda e: app._setup_local_private_model_with_progress(),
                        style=ft.ButtonStyle(
                            bgcolor=LightTheme.ACCENT_PRIMARY,
                            color="white",
                            shape=ft.RoundedRectangleBorder(radius=12),
                            padding=ft.padding.symmetric(horizontal=14, vertical=12),
                        ),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    send_button = ft.ElevatedButton(
        content=ft.Text("Send", size=13, weight=ft.FontWeight.W_600, color="white"),
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
            padding=ft.padding.symmetric(horizontal=18, vertical=14),
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    top_bar = ft.Container(
        padding=ft.padding.symmetric(horizontal=24, vertical=18),
        border=ft.border.only(bottom=ft.BorderSide(1, "#e0e0e0")),
        content=ft.Row(
            [
                ft.Text(
                    "Chat",
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color="#1a1a1a",
                ),
                ft.Container(expand=True),
                ft.Container(
                    border_radius=999,
                    bgcolor="#e0f8eb",
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    content=ft.Row(
                        [
                            ft.Container(width=8, height=8, border_radius=4, bgcolor=LightTheme.ACCENT_SUCCESS),
                            ft.Text(
                                "Local · Private",
                                size=12,
                                weight=ft.FontWeight.W_500,
                                color=LightTheme.ACCENT_SUCCESS,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    chat_area = ft.Container(
        expand=True,
        alignment=ft.alignment.top_center,
        padding=ft.padding.symmetric(horizontal=24, vertical=24),
        content=ft.Container(
            width=LightTheme.MAX_READING_WIDTH,
            expand=True,
            content=ft.Stack(
                [
                    ft.Container(expand=True, content=app.workspace_empty_state),
                    ft.Container(expand=True, content=chat_messages_list),
                ],
                expand=True,
            ),
        ),
    )

    input_bar = ft.Container(
        padding=ft.padding.only(left=24, top=16, right=24, bottom=24),
        border=ft.border.only(top=ft.BorderSide(1, LightTheme.BORDER_COLOR)),
        alignment=ft.alignment.center,
        content=ft.Container(
            width=LightTheme.MAX_READING_WIDTH,
            content=ft.Row(
                [
                    chat_input,
                    send_button,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )

    centered_setup_card = (
        ft.Container(
            alignment=ft.alignment.center,
            padding=ft.padding.only(left=24, right=24, top=16),
            content=ft.Container(width=LightTheme.MAX_READING_WIDTH, content=model_setup_card),
        )
        if model_setup_card is not None
        else ft.Container()
    )

    content_controls: List[ft.Control] = [
        top_bar,
        centered_setup_card,
        chat_area,
        input_bar,
    ]

    content = ft.Container(
        expand=True,
        bgcolor=LightTheme.BG_PRIMARY,
        content=ft.Column(
            content_controls,
            spacing=0,
            expand=True,
        ),
    )

    app._render_primary_shell(0, content, fill=True)

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
    """Render the Figma-aligned Files view."""
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
                        ft.Text("No personalization layers yet", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        ft.Text(
                            "Custom behavior layers will appear here once you personalize a workspace.",
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
                ft.Text("Files", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Your private knowledge sources and optional personalization layers.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                build_button(
                    "Create Profile",
                    icon=ft.Icons.ADD_ROUNDED,
                    on_click=lambda e: app._open_create_profile_dialog(),
                    variant=ButtonVariant.PRIMARY,
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
                                    ft.Text("Personalization Layers", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
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
                                "Optional private layers that adapt Enclave to your workflow and style without changing the base model.",
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

    app._render_primary_shell(2, content)


def show_vaults_view(app: Any) -> None:
    """Render the prosumer vault categories view."""
    app.current_view = "vaults"
    app.page.clean()

    # Get document counts per category from the app's private model profiles
    category_counts: Dict[str, int] = {}
    adapter_statuses: Dict[str, str] = {}

    try:
        profiles = app._get_private_model_profiles()
        for profile in profiles:
            # Map profile keywords to categories for counting
            docs = app._get_private_model_documents(limit=100)
            for doc in docs:
                # Simple heuristic: use filename to guess category
                name = doc.get("name", "").lower()
                if any(k in name for k in ["medical", "prescription", "lab", "blood", "health"]):
                    category_counts["health"] = category_counts.get("health", 0) + 1
                elif any(k in name for k in ["bank", "tax", "statement", "investment", "finance"]):
                    category_counts["finance"] = category_counts.get("finance", 0) + 1
                elif any(k in name for k in ["contract", "legal", "will", "immigration", "nda"]):
                    category_counts["legal"] = category_counts.get("legal", 0) + 1
                else:
                    category_counts["personal"] = category_counts.get("personal", 0) + 1

    # Determine adapter status from wdva_adapters + vault training status
        for profile in profiles:
            for adapter in profile.wdva_adapters:
                cat = adapter.get("category_id", "personal")
                adapter_statuses[cat] = "ready"
        # Overlay prosumer vault adapter statuses
        if hasattr(app, "_vault_adapter_statuses"):
            for cat, status in app._vault_adapter_statuses.items():
                adapter_statuses[cat] = status
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not load vault stats: {e}")

    # Build vaults grid if components available
    if build_vaults_grid is not None:
        vaults_grid = build_vaults_grid(
            classifier=None,  # Not needed here since we pre-counted
            category_counts=category_counts,
            adapter_statuses=adapter_statuses,
            on_upload=lambda cid: app._open_private_files_picker(),
            on_train=lambda cid: app._start_vault_training(cid),
        )
    else:
        vaults_grid = ft.Text(
            "Prosumer components not available. Install with: pip install -e '.[prosumer]'",
            color=LightTheme.TEXT_SECONDARY,
        )

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("Vaults", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                        ft.Container(expand=True),
                        build_button(
                            "Upload Documents",
                            icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                            on_click=lambda e: app._open_private_files_picker(),
                            variant=ButtonVariant.PRIMARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    "Your documents are automatically organized into encrypted vault categories. "
                    "Train a domain-specific AI for each vault.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Container(height=8),
                vaults_grid,
            ],
            spacing=16,
            expand=True,
        ),
    )

    app._render_primary_shell(1, content)


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
            return app._build_status_badge("Needs setup", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT)
        return app._build_status_badge("Not detected", color=LightTheme.TEXT_MUTED, tint=LightTheme.BG_SUBTLE)

    def _client_setup_state(client_id: str, client: Dict[str, Any]) -> tuple[str, str, str]:
        normalized = (client.get("status") or "offline").lower()
        if normalized == "active":
            return (
                "Connected",
                "Enclave is already between this app and your private context.",
                "Open and ask from private context",
            )
        if normalized == "ready":
            return (
                "Ready on this Mac",
                "The app is available locally. Finish setup so it routes through Enclave instead of touching files directly.",
                "Configure MCP link",
            )
        return (
            "Not detected",
            "Use the MCP config below or install the app first, then reconnect through Enclave.",
            "Install or copy config",
        )

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
        state_title, state_detail, state_cta = _client_setup_state(client_id, client)
        client_cards.append(
            app._build_surface_card(
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(client["name"], size=15, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                ft.Container(expand=True),
                                _client_status_badge(client.get("status", "offline")),
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(state_title, size=12, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                        ft.Text(state_detail, size=12, color=LightTheme.TEXT_SECONDARY),
                        ft.Text(f"Last state: {client.get('last_seen', 'Unknown')}", size=12, color=LightTheme.TEXT_MUTED),
                        ft.Text(
                            "Allowed tools: " + (", ".join(allowed_permissions) if allowed_permissions else "None"),
                            size=12,
                            color=LightTheme.TEXT_SECONDARY,
                        ),
                        ft.Row(
                            [
                                build_button(
                                    state_cta,
                                    on_click=lambda e, action=configure_action: action(),
                                    variant=ButtonVariant.PRIMARY,
                                ),
                                ft.TextButton(
                                    "Revoke Access",
                                    on_click=lambda e, cid=client_id: app._revoke_connection_access(cid),
                                    style=ft.ButtonStyle(color=LightTheme.ACCENT_ERROR),
                                ),
                            ],
                            spacing=12,
                            wrap=True,
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

    exposure_badges = ft.Row(
        [
            app._build_status_badge("Private files stay local", color=LightTheme.ACCENT_SUCCESS, tint=LightTheme.ACCENT_SUCCESS + "12"),
            app._build_status_badge("MCP-ready control layer", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT),
            app._build_status_badge("Approvals for spend + checkout", color=LightTheme.ACCENT_WARNING, tint=LightTheme.ACCENT_WARNING + "12"),
        ],
        spacing=8,
        wrap=True,
    )

    common_pathways = app._build_surface_card(
        ft.Column(
            [
                ft.Text("Common Agent Paths", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Use Enclave as the control layer for desktop copilots, ChatGPT-like and MCP tools, agentic browsers, and higher-risk ecommerce automations.",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(app._build_surface_card(ft.Column([ft.Text("Claude Desktop", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY), ft.Text("Private file Q&A through MCP with approvals, logs, and revocable access.", size=11, color=LightTheme.TEXT_SECONDARY)], spacing=6)), col={"sm": 12, "md": 4}),
                        ft.Container(app._build_surface_card(ft.Column([ft.Text("ChatGPT-like / MCP tools", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY), ft.Text("Let external copilots query scoped context without exposing raw files by default.", size=11, color=LightTheme.TEXT_SECONDARY)], spacing=6)), col={"sm": 12, "md": 4}),
                        ft.Container(app._build_surface_card(ft.Column([ft.Text("Browsers / ecommerce automations", size=13, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY), ft.Text("Keep shopping, travel, and checkout context behind approvals and spending limits.", size=11, color=LightTheme.TEXT_SECONDARY)], spacing=6)), col={"sm": 12, "md": 4}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
            ],
            spacing=12,
        )
    )

    guided_flow = app._build_surface_card(
        ft.Column(
            [
                ft.Text("Investor Demo Flow", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Show the product in this order: import context, ask privately, connect an app, then show approvals and spend controls.",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Row(
                    [
                        app._build_status_badge("1 Import", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT),
                        app._build_status_badge("2 Ask", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT),
                        app._build_status_badge("3 Connect", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT),
                        app._build_status_badge("4 Protect", color=LightTheme.ACCENT_PRIMARY, tint=LightTheme.ACCENT_BLUE_LIGHT),
                    ],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=12,
        )
    )

    content = ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Text("Connect AI Apps", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Route Claude, Cursor, OpenClaw, ChatGPT-like/MCP tools, browsers, and commerce agents through Enclave so file access stays local, controlled, and revocable.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                exposure_badges,
                guided_flow,
                common_pathways,
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Text("Local MCP Server", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            app._build_status_badge("Running", color=LightTheme.ACCENT_SUCCESS, tint=LightTheme.ACCENT_SUCCESS + "12"),
                            ft.Text("Listening on stdio through the local Enclave runtime so AI apps talk to Enclave before they touch your data.", size=13, color=LightTheme.TEXT_SECONDARY),
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
                            ft.Text("Connect a New App", size=16, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                            ft.Text(
                                "Use this MCP configuration to put Enclave between your private files and Claude Desktop, Cursor, ChatGPT-like/MCP tools, or other agentic apps.",
                                size=13,
                                color=LightTheme.TEXT_SECONDARY,
                            ),
                            ft.Text(
                                "First-run flow: connect an app, let it request scoped context, and keep browser or checkout actions behind approvals.",
                                size=12,
                                color=LightTheme.TEXT_MUTED,
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
                                    ft.OutlinedButton("Connect Claude Desktop", on_click=lambda e: app._configure_claude_mcp()),
                                    ft.OutlinedButton("Connect Cursor", on_click=lambda e: app._configure_cursor_mcp()),
                                    ft.OutlinedButton("Copy for OpenClaw / other MCP apps", on_click=lambda e: app._copy_mcp_json()),
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

    app._render_primary_shell(-1, content)


def show_security_view(app: Any) -> None:
    """Render the Figma-aligned Protection view."""
    app.current_view = "security_shell"
    app.page.clean()

    shared_status = app._update_module_status_snapshots()
    vault_snapshot = shared_status.get("vault", {}).get("details", {})
    wallet_snapshot = shared_status.get("wallet", {}).get("details", {})
    connection_clients = app._update_integration_client_statuses()
    connected_client_count = sum(1 for client in connection_clients.values() if client.get("status") in {"active", "ready"})
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
                        border_radius=12,
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
                ft.Text("Protection Controls", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                app._privacy_control_row(
                    "Local-Only Processing",
                    "Private source material stays on this device unless you choose to expose it.",
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
                    "Stops sensitive vault and wallet actions across connected agents.",
                    value=kill_switch.enabled,
                    disabled=False,
                    on_change=lambda e: app._set_global_kill_switch(bool(e.control.value)),
                ),
            ],
            spacing=0,
        )
    )

    exposure_summary = app._build_surface_card(
        ft.Column(
            [
                ft.Text("Exposure Summary", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Use this page to understand what can leave Enclave, which apps are connected, and where approvals will interrupt agentic actions.",
                    size=12,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.Row(
                    [
                        app._simple_metric_card("Connected Apps", str(connected_client_count)),
                        app._simple_metric_card("Recent Events", str(len(recent_events))),
                        app._simple_metric_card("Pending Approvals", str(len(pending_requests))),
                    ],
                    spacing=10,
                    wrap=True,
                ),
                ft.Row(
                    [
                        ft.OutlinedButton("Open Connect Apps", on_click=lambda e: app._show_connections_view()),
                        ft.OutlinedButton("Open Library", on_click=lambda e: app._show_library_view()),
                    ],
                    spacing=10,
                    wrap=True,
                ),
            ],
            spacing=12,
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
                                            ft.Text("Protected Files", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                            ft.Text("Choose which files agents can use and keep sensitive material scoped.", size=12, color=LightTheme.TEXT_SECONDARY),
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
                                            ft.Text("What Left Enclave", size=14, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                            ft.Text("Review recent access decisions and outbound actions.", size=12, color=LightTheme.TEXT_SECONDARY),
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
                ft.Text("Protection", size=24, weight=ft.FontWeight.W_700, color=LightTheme.TEXT_PRIMARY),
                ft.Text(
                    "Keep the upside of the agentic web while controlling what can be exposed, approved, or revoked.",
                    size=13,
                    color=LightTheme.TEXT_SECONDARY,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(status_card(ft.Icons.MEMORY_ROUNDED, "Local AI", "On", "Runs on this Mac.", LightTheme.ACCENT_SUCCESS), col={"sm": 12, "md": 4}),
                        ft.Container(status_card(ft.Icons.LOCK_ROUNDED, "Vault", "Encrypted", "Files stay encrypted at rest.", LightTheme.ACCENT_PRIMARY), col={"sm": 12, "md": 4}),
                        ft.Container(status_card(ft.Icons.HUB_ROUNDED, "Exposure Controls", "On", "Checks private access and spend.", LightTheme.ACCENT_PRIMARY), col={"sm": 12, "md": 4}),
                    ],
                    spacing=12,
                    run_spacing=12,
                ),
                exposure_summary,
                privacy_controls,
                access_cards,
                app._build_surface_card(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("Ecommerce & Spend Guardrails", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
                                    app._build_status_badge(
                                        "Frozen" if wallet_snapshot.get("frozen") else "Ready",
                                        color=(LightTheme.ACCENT_ERROR if wallet_snapshot.get("frozen") else LightTheme.ACCENT_SUCCESS),
                                        tint=((LightTheme.ACCENT_ERROR if wallet_snapshot.get("frozen") else LightTheme.ACCENT_SUCCESS) + "12"),
                                    ),
                                    ft.Container(expand=True),
                                ],
                                spacing=10,
                            ),
                            ft.Text("Prepaid limits for agentic checkout, autonomous purchasing, and higher-risk ecommerce actions.", size=12, color=LightTheme.TEXT_SECONDARY),
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
                                    build_button("Create Wallet", icon=ft.Icons.ADD_CARD_ROUNDED, on_click=lambda e: (app._ensure_demo_wallet_envelope(), app._show_security_view()), variant=ButtonVariant.PRIMARY),
                                    build_button("$19 test", icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=lambda e: app._request_demo_wallet_purchase(19.0, "github.com", "Auto-approved demo spend"), variant=ButtonVariant.OUTLINE),
                                    build_button("$85 approval", icon=ft.Icons.HOURGLASS_TOP_ROUNDED, on_click=lambda e: app._request_demo_wallet_purchase(85.0, "openai.com", "Pending approval demo spend"), variant=ButtonVariant.OUTLINE),
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
                            ft.Text("Recent exposure decisions", size=17, weight=ft.FontWeight.W_600, color=LightTheme.TEXT_PRIMARY),
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

    app._render_primary_shell(3, content)
