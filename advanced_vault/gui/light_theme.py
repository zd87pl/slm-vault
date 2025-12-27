"""
Light Theme System - Hugging Face Inspired
Clean, bright, modern design with light backgrounds and subtle accents.
"""

class LightTheme:
    """Light theme inspired by Hugging Face's clean, bright aesthetic."""
    
    # Background colors (light, airy)
    BG_PRIMARY = "#ffffff"           # Pure white (main background)
    BG_SECONDARY = "#f8f9fa"         # Very light gray (subtle sections)
    BG_ELEVATED = "#ffffff"          # White cards
    BG_HOVER = "#f1f3f5"             # Light gray hover
    BG_SURFACE = "#ffffff"           # Card surfaces
    
    # Subtle background variations
    BG_SUBTLE = "#fafbfc"            # Ultra-light gray (for depth)
    BG_DIVIDER = "#e5e7eb"           # Light divider color
    
    # Accent colors (soft blues and purples like HF)
    ACCENT_PRIMARY = "#007bff"       # Bright blue (primary actions)
    ACCENT_PRIMARY_DARK = "#0056b3"  # Darker blue (hover)
    ACCENT_SECONDARY = "#7c3aed"     # Purple (secondary actions)
    ACCENT_SUCCESS = "#10b981"       # Green (success states)
    ACCENT_WARNING = "#f59e0b"       # Amber (warnings)
    ACCENT_ERROR = "#ef4444"         # Red (errors)
    
    # Accent variations (HF style)
    ACCENT_BLUE_LIGHT = "#e0f2fe"    # Light blue background
    ACCENT_PURPLE_LIGHT = "#f3e8ff"  # Light purple background
    
    # Text colors (dark on light)
    TEXT_PRIMARY = "#1f2937"         # Dark gray (almost black)
    TEXT_SECONDARY = "#4b5563"       # Medium gray
    TEXT_MUTED = "#6b7280"           # Muted gray
    TEXT_DISABLED = "#9ca3af"        # Disabled gray
    TEXT_LINK = "#007bff"            # Link blue
    
    # Borders (subtle, light)
    BORDER_COLOR = "#e5e7eb"         # Light gray border
    BORDER_COLOR_HOVER = "#d1d5db"   # Slightly darker on hover
    BORDER_COLOR_ACTIVE = "#007bff"   # Blue border for active
    
    # Glassmorphism (light theme version)
    GLASS_BG = "rgba(255, 255, 255, 0.95)"
    GLASS_BORDER = "rgba(0, 0, 0, 0.05)"
    
    # Shadows (subtle, light theme)
    SHADOW_XS = "0 1px 2px rgba(0, 0, 0, 0.05)"
    SHADOW_SM = "0 1px 3px rgba(0, 0, 0, 0.1)"
    SHADOW_MD = "0 4px 6px rgba(0, 0, 0, 0.1)"
    SHADOW_LG = "0 10px 15px rgba(0, 0, 0, 0.1)"
    
    # Gradients (light theme)
    GRADIENT_PRIMARY = ["#007bff", "#7c3aed"]  # Blue to purple
    GRADIENT_SECONDARY = ["#f59e0b", "#f97316"]  # Amber to orange
    GRADIENT_SUCCESS = ["#10b981", "#059669"]  # Green shades
    GRADIENT_BG = ["#ffffff", "#f8f9fa"]  # Subtle background gradient
    
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
    CARD_BORDER_RADIUS = 8
    
    SIDEBAR_WIDTH = 240
    
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

