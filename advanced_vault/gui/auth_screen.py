#!/usr/bin/env python3
"""
Authentication screen for Enclave GUI with OAuth support.
"""

import flet as ft
import os
import json
import webbrowser
from pathlib import Path
from typing import Optional, Callable
from supabase import create_client, Client
from gotrue.errors import AuthApiError
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from localization import get_text


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth redirect callback."""

    callback_data = None

    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        # Parse the URL
        parsed = urlparse(self.path)

        # Extract tokens from hash fragment (Supabase sends in hash)
        if '#' in self.path:
            fragment = self.path.split('#')[1]
            params = parse_qs(fragment)
        else:
            params = parse_qs(parsed.query)

        # Store the callback data
        OAuthCallbackHandler.callback_data = params

        # Send success response
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        success_html = """
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                }
                h1 { color: #333; margin-bottom: 10px; }
                p { color: #666; }
                .check { font-size: 48px; color: #4caf50; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="check">✓</div>
                <h1>Authentication Successful!</h1>
                <p>You can close this window and return to Enclave.</p>
            </div>
            <script>window.close();</script>
        </body>
        </html>
        """
        self.wfile.write(success_html.encode())

    def log_message(self, format, *args):
        """Suppress log messages."""
        pass


class AuthScreen:
    """Authentication screen with OAuth and email/password support."""

    def __init__(
        self,
        page: ft.Page,
        backend_url: str,
        on_auth_success: Callable[[dict], None],
        language: str = "en",
        translate: Optional[Callable[..., str]] = None,
    ):
        """Initialize auth screen."""
        self.page = page
        self.backend_url = backend_url
        self.on_auth_success = on_auth_success
        self.language = language or "en"
        self.translate = translate

        # Get Supabase credentials from environment variables
        # Set SUPABASE_URL and SUPABASE_ANON_KEY in launch script or environment
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set")

        # Initialize Supabase client
        self.supabase: Client = create_client(self.supabase_url, self.supabase_anon_key)

        # Auth mode: 'signin' or 'signup'
        self.auth_mode = "signin"

        # Build UI components
        self.build_components()

    def t(self, key: str, **kwargs) -> str:
        """Resolve localized text with fallback."""
        if self.translate:
            try:
                return self.translate(key, **kwargs)
            except Exception:
                try:
                    return self.translate(key)
                except Exception:
                    pass
        return get_text(self.language, key, **kwargs)

    def build_components(self):
        """Build auth UI components."""
        # Email field
        self.email_field = ft.TextField(
            label=self.t("auth.email.label"),
            hint_text=self.t("auth.email.hint"),
            prefix_icon=ft.Icons.EMAIL,
            border_radius=12,
            filled=True,
            bgcolor="#1a1a1a",
            border_color="#333333",
            focused_border_color="#667eea",
            text_size=14,
        )

        # Password field
        self.password_field = ft.TextField(
            label=self.t("auth.password.label"),
            hint_text=self.t("auth.password.hint"),
            prefix_icon=ft.Icons.LOCK,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            filled=True,
            bgcolor="#1a1a1a",
            border_color="#333333",
            focused_border_color="#667eea",
            text_size=14,
        )

        # Full name field (for signup)
        self.fullname_field = ft.TextField(
            label=self.t("auth.full_name.label"),
            hint_text=self.t("auth.full_name.hint"),
            prefix_icon=ft.Icons.PERSON,
            border_radius=12,
            filled=True,
            bgcolor="#1a1a1a",
            border_color="#333333",
            focused_border_color="#667eea",
            text_size=14,
            visible=False,
        )

        # Error message
        self.error_text = ft.Text(
            "",
            color="#f44336",
            size=12,
            visible=False,
        )

        # Submit button
        self.submit_button = ft.ElevatedButton(
            self.t("auth.submit.signin"),
            icon=ft.Icons.LOGIN,
            on_click=self.handle_email_auth,
            width=300,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#667eea",
                color="white",
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
        )

        # Toggle mode link
        self.toggle_mode_btn = ft.TextButton(
            self.t("auth.toggle.to_signup"),
            on_click=self.toggle_auth_mode,
            style=ft.ButtonStyle(
                color="#667eea",
            ),
        )

        # OAuth buttons
        self.google_button = ft.ElevatedButton(
            self.t("auth.oauth.google"),
            icon=ft.Icons.LOGIN,
            on_click=lambda _: self.handle_oauth("google"),
            width=300,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#ffffff",
                color="#333333",
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
        )

        self.github_button = ft.ElevatedButton(
            self.t("auth.oauth.github"),
            icon=ft.Icons.CODE,
            on_click=lambda _: self.handle_oauth("github"),
            width=300,
            height=50,
            style=ft.ButtonStyle(
                bgcolor="#24292e",
                color="#ffffff",
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
        )

        # Loading indicator
        self.loading = ft.ProgressRing(visible=False)

    def get_view(self) -> ft.Container:
        """Get the auth screen view."""
        return ft.Container(
            content=ft.Column(
                [
                    # Logo and title
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(
                                    ft.Icons.LOCK,
                                    size=80,
                                    color="#667eea",
                                ),
                                ft.Text(
                                    "Enclave",
                                    size=36,
                                    weight=ft.FontWeight.BOLD,
                                    color="#ffffff",
                                ),
                                ft.Text(
                                    self.t("auth.subtitle"),
                                    size=14,
                                    color="#999999",
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        margin=ft.margin.only(bottom=40),
                    ),

                    # OAuth buttons
                    ft.Container(
                        content=ft.Column(
                            [
                                self.google_button,
                                self.github_button,
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=12,
                        ),
                        margin=ft.margin.only(bottom=30),
                    ),

                    # Divider
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    height=1,
                                    bgcolor="#333333",
                                    expand=True,
                                ),
                                ft.Text(
                                    self.t("auth.divider.or"),
                                    size=12,
                                    color="#666666",
                                ),
                                ft.Container(
                                    height=1,
                                    bgcolor="#333333",
                                    expand=True,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        width=300,
                        margin=ft.margin.only(bottom=30),
                    ),

                    # Email/password form
                    ft.Container(
                        content=ft.Column(
                            [
                                self.email_field,
                                self.password_field,
                                self.fullname_field,
                                self.error_text,
                                self.submit_button,
                                self.toggle_mode_btn,
                                self.loading,
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=16,
                        ),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            ),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=["#0f0f0f", "#1a1a1a"],
            ),
            padding=40,
            expand=True,
        )

    def toggle_auth_mode(self, e):
        """Toggle between sign in and sign up."""
        if self.auth_mode == "signin":
            self.auth_mode = "signup"
            self.submit_button.text = self.t("auth.submit.signup")
            self.submit_button.icon = ft.Icons.PERSON_ADD
            self.toggle_mode_btn.text = self.t("auth.toggle.to_signin")
            self.fullname_field.visible = True
        else:
            self.auth_mode = "signin"
            self.submit_button.text = self.t("auth.submit.signin")
            self.submit_button.icon = ft.Icons.LOGIN
            self.toggle_mode_btn.text = self.t("auth.toggle.to_signup")
            self.fullname_field.visible = False

        self.page.update()

    def show_error(self, message: str):
        """Show error message."""
        self.error_text.value = message
        self.error_text.visible = True
        self.page.update()

    def hide_error(self):
        """Hide error message."""
        self.error_text.visible = False
        self.page.update()

    def show_loading(self, show: bool = True):
        """Show/hide loading indicator."""
        self.loading.visible = show
        self.submit_button.disabled = show
        self.google_button.disabled = show
        self.github_button.disabled = show
        self.page.update()

    def handle_email_auth(self, e):
        """Handle email/password authentication."""
        self.hide_error()

        email = self.email_field.value
        password = self.password_field.value

        if not email or not password:
            self.show_error(self.t("auth.error.missing_credentials"))
            return

        self.show_loading(True)

        # Run auth in background thread
        def _auth():
            try:
                if self.auth_mode == "signup":
                    # Sign up
                    full_name = self.fullname_field.value or None
                    response = self.supabase.auth.sign_up({
                        "email": email,
                        "password": password,
                        "options": {
                            "data": {
                                "full_name": full_name
                            }
                        }
                    })
                else:
                    # Sign in
                    response = self.supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password,
                    })

                # Success
                if response.user:
                    session_data = {
                        "user": {
                            "id": response.user.id,
                            "email": response.user.email,
                            "full_name": response.user.user_metadata.get("full_name"),
                        },
                        "access_token": response.session.access_token,
                        "refresh_token": response.session.refresh_token,
                    }

                    # Save session
                    self.save_session(session_data)

                    # Callback
                    self.on_auth_success(session_data)
                else:
                    self.show_error(self.t("auth.error.failed"))

            except AuthApiError as ex:
                self.show_error(str(ex))
            except Exception as ex:
                self.show_error(self.t("auth.error.generic", error=str(ex)))

            finally:
                self.show_loading(False)

        thread = threading.Thread(target=_auth, daemon=True)
        thread.start()

    def handle_oauth(self, provider: str):
        """Handle OAuth authentication."""
        self.hide_error()
        self.show_loading(True)

        try:
            # Start OAuth flow
            redirect_url = "http://localhost:54321/auth/callback"

            response = self.supabase.auth.sign_in_with_oauth({
                "provider": provider,
                "options": {
                    "redirect_to": redirect_url
                }
            })

            # Open browser
            webbrowser.open(response.url)

            # Start callback server in background
            def run_callback_server():
                server = HTTPServer(('localhost', 54321), OAuthCallbackHandler)
                server.handle_request()  # Handle one request then stop

                # Process callback
                if OAuthCallbackHandler.callback_data:
                    # Get session from Supabase
                    session = self.supabase.auth.get_session()
                    if session:
                        session_data = {
                            "user": {
                                "id": session.user.id,
                                "email": session.user.email,
                                "full_name": session.user.user_metadata.get("full_name"),
                            },
                            "access_token": session.access_token,
                            "refresh_token": session.refresh_token,
                        }

                        # Save and callback
                        self.save_session(session_data)
                        self.on_auth_success(session_data)

                self.show_loading(False)

            thread = threading.Thread(target=run_callback_server, daemon=True)
            thread.start()

        except Exception as ex:
            self.show_error(self.t("auth.error.oauth", error=str(ex)))
            self.show_loading(False)

    def save_session(self, session_data: dict):
        """Save session to disk."""
        session_path = Path("~/.vault/session.json").expanduser()
        session_path.parent.mkdir(parents=True, exist_ok=True)

        with open(session_path, 'w') as f:
            json.dump(session_data, f)

        os.chmod(session_path, 0o600)

    @staticmethod
    def load_session() -> Optional[dict]:
        """Load saved session."""
        session_path = Path("~/.vault/session.json").expanduser()

        if not session_path.exists():
            return None

        try:
            with open(session_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def clear_session():
        """Clear saved session."""
        session_path = Path("~/.vault/session.json").expanduser()
        if session_path.exists():
            session_path.unlink()
