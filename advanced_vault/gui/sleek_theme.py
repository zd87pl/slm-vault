"""
Sleek Modern Theme System - Apple/Uber/Palantir Style
Compact, refined design tokens for professional desktop apps.
"""

class SleekTheme:
    """Sleek, compact design system inspired by Apple, Uber, Palantir."""
    
    # Background colors (refined, subtle)
    BG_PRIMARY = "#0a0a0f"      # Deep dark blue-black
    BG_SECONDARY = "#14141f"    # Slightly lighter
    BG_ELEVATED = "#1a1a24"     # Cards (subtle elevation)
    BG_HOVER = "#202030"        # Hover states (very subtle)
    
    # Accent colors (more muted, professional)
    ACCENT_PRIMARY = "#5b5fde"   # Softer indigo
    ACCENT_PRIMARY_DARK = "#4a4eb8"
    ACCENT_SECONDARY = "#7c7d9f" # Muted purple-gray
    ACCENT_SUCCESS = "#0ea571"  # Subtle green
    ACCENT_WARNING = "#d97706"  # Muted amber
    ACCENT_ERROR = "#dc2626"    # Refined red
    
    # Text colors (refined hierarchy)
    TEXT_PRIMARY = "#f5f5f7"    # Almost white (Apple-style)
    TEXT_SECONDARY = "#a1a1aa"  # Muted gray
    TEXT_MUTED = "#71717a"      # Very muted gray
    TEXT_DISABLED = "#52525b"   # Disabled state
    
    # Borders (subtle, thin)
    BORDER_COLOR = "#27272a"    # Very subtle border
    BORDER_COLOR_HOVER = "#3f3f46"  # Slightly more visible
    
    # Design Tokens - Compact Sizes
    # Typography
    FONT_SIZE_XS = 11           # Captions, labels
    FONT_SIZE_SM = 12           # Small text
    FONT_SIZE_BASE = 13         # Body text
    FONT_SIZE_MD = 14           # Medium emphasis
    FONT_SIZE_LG = 16           # Headings
    FONT_SIZE_XL = 18           # Large headings
    FONT_SIZE_2XL = 20           # Page titles
    
    # Spacing (tight, professional)
    SPACING_XS = 4              # Tight spacing
    SPACING_SM = 6              # Small spacing
    SPACING_MD = 8              # Medium spacing
    SPACING_LG = 12             # Large spacing
    SPACING_XL = 16             # Extra large
    SPACING_2XL = 20            # Section spacing
    
    # Padding (compact)
    PADDING_XS = 6              # Tight padding
    PADDING_SM = 8              # Small padding
    PADDING_MD = 12             # Medium padding
    PADDING_LG = 16             # Large padding
    PADDING_XL = 20             # Extra large
    
    # Component Sizes
    ICON_SIZE_XS = 14           # Small icons
    ICON_SIZE_SM = 16           # Regular icons
    ICON_SIZE_MD = 18           # Medium icons
    ICON_SIZE_LG = 20           # Large icons
    
    BUTTON_HEIGHT_SM = 28       # Small buttons
    BUTTON_HEIGHT_MD = 32       # Regular buttons
    BUTTON_HEIGHT_LG = 36       # Large buttons
    
    INPUT_HEIGHT = 32           # Input fields
    INPUT_HEIGHT_SM = 28        # Small inputs
    
    CARD_PADDING = 12           # Card padding
    CARD_BORDER_RADIUS = 8      # Subtle rounding
    
    SIDEBAR_WIDTH = 200         # Compact sidebar
    
    # Shadows (subtle)
    SHADOW_XS = "0 1px 1px rgba(0, 0, 0, 0.15)"
    SHADOW_SM = "0 1px 2px rgba(0, 0, 0, 0.2)"
    SHADOW_MD = "0 2px 4px rgba(0, 0, 0, 0.25)"
    
    @staticmethod
    def get_text_style(size: int, weight=None, color=None):
        """Get text style with consistent sizing."""
        import flet as ft
        return ft.TextStyle(
            size=size,
            weight=weight or ft.FontWeight.NORMAL,
            color=color or SleekTheme.TEXT_PRIMARY
        )
    
    @staticmethod
    def get_button_style(size="md", variant="primary"):
        """Get compact button style."""
        import flet as ft
        
        heights = {
            "sm": SleekTheme.BUTTON_HEIGHT_SM,
            "md": SleekTheme.BUTTON_HEIGHT_MD,
            "lg": SleekTheme.BUTTON_HEIGHT_LG,
        }
        
        colors = {
            "primary": SleekTheme.ACCENT_PRIMARY,
            "secondary": SleekTheme.BG_ELEVATED,
            "success": SleekTheme.ACCENT_SUCCESS,
            "error": SleekTheme.ACCENT_ERROR,
        }
        
        return ft.ButtonStyle(
            bgcolor=colors.get(variant, SleekTheme.ACCENT_PRIMARY),
            color=SleekTheme.TEXT_PRIMARY,
            padding=ft.padding.symmetric(
                horizontal=SleekTheme.PADDING_LG,
                vertical=SleekTheme.PADDING_SM
            ),
            shape=ft.RoundedRectangleBorder(radius=SleekTheme.CARD_BORDER_RADIUS),
        )

