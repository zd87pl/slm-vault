"""
Light Theme System
Warm-neutral, investor-demo theme aligned to the current Enclave desktop design.
"""

class LightTheme:
    """Warm neutral light theme with teal privacy accents."""
    
    # Background colors
    BG_PRIMARY = "#ffffff"           # App background
    BG_SECONDARY = "#fbfbfb"         # Section surfaces
    BG_ELEVATED = "#ffffff"          # Cards
    BG_HOVER = "#f4f4f4"             # Hovered cards and nav
    BG_SURFACE = "#ffffff"           # Primary surface
    
    # Subtle background variations
    BG_SUBTLE = "#fafafa"
    BG_DIVIDER = "rgba(0, 0, 0, 0.08)"
    SURFACE_TINT = "rgba(13, 124, 140, 0.04)"
    
    # Accent colors
    ACCENT_PRIMARY = "#0d7c8c"       # Rich teal
    ACCENT_PRIMARY_DARK = "#0a6271"
    ACCENT_SECONDARY = "#2a9aac"
    ACCENT_SUCCESS = "#10b981"
    ACCENT_WARNING = "#f59e0b"
    ACCENT_ERROR = "#ef4444"
    
    # Accent variations (HF style)
    ACCENT_BLUE_LIGHT = "#e6f4f6"    # Accent tint surface
    ACCENT_PURPLE_LIGHT = "#eef7f8"
    
    # Text colors (dark on light)
    TEXT_PRIMARY = "#1a1a1a"
    TEXT_SECONDARY = "#3d3d3d"
    TEXT_MUTED = "#6b6b6b"
    TEXT_DISABLED = "#9ca3af"
    TEXT_LINK = "#0d7c8c"
    
    # Borders (subtle, light).
    # NOTE: these MUST be solid hex, not rgba() strings. Flet's BorderSide does
    # not parse rgba() and silently falls back to the theme accent (teal), and
    # the `BORDER_COLOR + "12"` tint pattern used across the app only produces a
    # valid 8-digit hex when the base is hex.
    BORDER_COLOR = "#e6e7eb"
    BORDER_COLOR_HOVER = "#d7d9df"
    BORDER_COLOR_ACTIVE = "#0d7c8c"
    
    # Glassmorphism (light theme version)
    GLASS_BG = "rgba(255, 255, 255, 0.92)"
    GLASS_BORDER = "rgba(0, 0, 0, 0.06)"
    
    # Shadows (subtle, light theme)
    SHADOW_XS = "0 1px 2px rgba(0, 0, 0, 0.04)"
    SHADOW_SM = "0 2px 8px rgba(0, 0, 0, 0.06)"
    SHADOW_MD = "0 4px 16px rgba(0, 0, 0, 0.08)"
    SHADOW_LG = "0 8px 32px rgba(0, 0, 0, 0.10)"
    
    # Gradients (light theme)
    GRADIENT_PRIMARY = ["#0d7c8c", "#2a9aac"]
    GRADIENT_SECONDARY = ["#fbfbfb", "#ffffff"]
    GRADIENT_SUCCESS = ["#10b981", "#059669"]
    GRADIENT_BG = ["#ffffff", "#fbfbfb"]
    
    # Design Tokens - Spacing (spacious like HF)
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 12
    SPACING_LG = 16
    SPACING_XL = 24
    SPACING_2XL = 32
    
    # Padding
    PADDING_XS = 8
    PADDING_SM = 12
    PADDING_MD = 16
    PADDING_LG = 24
    PADDING_XL = 32
    
    # Typography
    FONT_SIZE_XS = 11
    FONT_SIZE_SM = 12
    FONT_SIZE_BASE = 14
    FONT_SIZE_MD = 16
    FONT_SIZE_LG = 18
    FONT_SIZE_XL = 20
    FONT_SIZE_2XL = 24
    
    # Component Sizes
    ICON_SIZE_XS = 14
    ICON_SIZE_SM = 16
    ICON_SIZE_MD = 18
    ICON_SIZE_LG = 20
    
    BUTTON_HEIGHT_SM = 32
    BUTTON_HEIGHT_MD = 36
    BUTTON_HEIGHT_LG = 40
    
    INPUT_HEIGHT = 36
    INPUT_HEIGHT_SM = 32
    
    CARD_PADDING = 16
    CARD_BORDER_RADIUS = 12

    SIDEBAR_WIDTH = 240

    # Max width for centered page content on wide windows (keeps dashboards
    # readable instead of stretching edge-to-edge).
    MAX_CONTENT_WIDTH = 1120
    # Narrower cap for reading/conversation columns (chat).
    MAX_READING_WIDTH = 760
    
    @staticmethod
    def get_gradient(colors, begin="top_left", end="bottom_right"):
        """Create a LinearGradient from colors."""
        import flet as ft
        
        begin_map = {
            "top_left": ft.alignment.top_left,
            "top_right": ft.alignment.top_right,
            "bottom_left": ft.alignment.bottom_left,
            "bottom_right": ft.alignment.bottom_right,
            "center": ft.alignment.center,
        }
        
        return ft.LinearGradient(
            begin=begin_map.get(begin, ft.alignment.top_left),
            end=begin_map.get(end, ft.alignment.bottom_right),
            colors=colors
        )
    
    @staticmethod
    def get_card_style():
        """Get light theme card styling."""
        import flet as ft
        return {
            "bgcolor": LightTheme.BG_ELEVATED,
            "border_radius": ft.border_radius.all(LightTheme.CARD_BORDER_RADIUS),
            "border": ft.border.all(1, LightTheme.BORDER_COLOR),
            "padding": ft.padding.all(LightTheme.CARD_PADDING),
            "shadow": ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color=ft.colors.with_opacity(0.1, ft.colors.BLACK),
                offset=ft.Offset(0, 2)
            ),
        }
    
    @staticmethod
    def get_button_style(variant="primary", size="md"):
        """Get light theme button style."""
        import flet as ft
        
        heights = {
            "sm": LightTheme.BUTTON_HEIGHT_SM,
            "md": LightTheme.BUTTON_HEIGHT_MD,
            "lg": LightTheme.BUTTON_HEIGHT_LG,
        }
        
        colors = {
            "primary": LightTheme.ACCENT_PRIMARY,
            "secondary": LightTheme.BG_SECONDARY,
            "success": LightTheme.ACCENT_SUCCESS,
            "error": LightTheme.ACCENT_ERROR,
            "outline": "transparent",
        }
        
        text_colors = {
            "primary": "#ffffff",
            "secondary": LightTheme.TEXT_PRIMARY,
            "success": "#ffffff",
            "error": "#ffffff",
            "outline": LightTheme.ACCENT_PRIMARY,
        }
        
        return ft.ButtonStyle(
            bgcolor=colors.get(variant, LightTheme.ACCENT_PRIMARY),
            color=text_colors.get(variant, "#ffffff"),
            padding=ft.padding.symmetric(
                horizontal=LightTheme.PADDING_LG,
                vertical=LightTheme.PADDING_SM
            ),
            shape=ft.RoundedRectangleBorder(radius=LightTheme.CARD_BORDER_RADIUS),
            elevation=0 if variant == "outline" else 1,
        )
    
    @staticmethod
    def get_text_style(size: int, weight=None, color=None):
        """Get text style with consistent sizing."""
        import flet as ft
        return ft.TextStyle(
            size=size,
            weight=weight or ft.FontWeight.NORMAL,
            color=color or LightTheme.TEXT_PRIMARY
        )
    
    @staticmethod
    def get_input_style():
        """Get light theme input field style."""
        import flet as ft
        return {
            "bgcolor": LightTheme.BG_PRIMARY,
            "border_color": LightTheme.BORDER_COLOR,
            "border_radius": ft.border_radius.all(LightTheme.CARD_BORDER_RADIUS),
            "height": LightTheme.INPUT_HEIGHT,
            "content_padding": ft.padding.symmetric(
                horizontal=LightTheme.PADDING_MD,
                vertical=LightTheme.PADDING_SM
            ),
        }
