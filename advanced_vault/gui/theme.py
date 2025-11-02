"""
Modern theme system for Enclave GUI.
Provides color palette, design tokens, and reusable styling components.
"""

class ModernTheme:
    """Modern color palette and design tokens."""
    
    # Background colors (gradient-friendly)
    BG_PRIMARY = "#0a0a0f"      # Deep dark blue-black
    BG_SECONDARY = "#14141f"    # Slightly lighter
    BG_ELEVATED = "#1e1e2e"     # Cards, elevated surfaces
    BG_HOVER = "#28283a"        # Hover states
    BG_SURFACE = "#2c2c2c"      # Legacy compatibility
    
    # Accent colors (softer, more sophisticated)
    ACCENT_PRIMARY = "#6366f1"   # Indigo (modern blue)
    ACCENT_PRIMARY_DARK = "#4f46e5"  # Darker indigo
    ACCENT_SECONDARY = "#8b5cf6" # Purple
    ACCENT_SUCCESS = "#10b981"   # Emerald green
    ACCENT_WARNING = "#f59e0b"   # Amber
    ACCENT_ERROR = "#ef4444"     # Red
    
    # Text colors
    TEXT_PRIMARY = "#f8fafc"     # Almost white
    TEXT_SECONDARY = "#cbd5e1"   # Light gray
    TEXT_MUTED = "#64748b"       # Muted gray
    TEXT_DISABLED = "#9e9e9e"    # Legacy compatibility
    
    # Glassmorphism
    GLASS_BG = "rgba(30, 30, 46, 0.85)"
    GLASS_BORDER = "rgba(255, 255, 255, 0.1)"
    
    # Borders
    BORDER_COLOR = "#2d2d3f"
    BORDER_COLOR_HOVER = "#3d3d4f"
    
    # Gradients
    GRADIENT_PRIMARY = ["#6366f1", "#8b5cf6"]  # Indigo to purple
    GRADIENT_SECONDARY = ["#f59e0b", "#f97316"]  # Amber to orange
    GRADIENT_SUCCESS = ["#10b981", "#059669"]  # Emerald shades
    GRADIENT_BG = ["#0a0a0f", "#14141f"]  # Background gradient
    
    # Shadows (for elevation)
    SHADOW_SM = "0 1px 2px rgba(0, 0, 0, 0.3)"
    SHADOW_MD = "0 4px 6px rgba(0, 0, 0, 0.4)"
    SHADOW_LG = "0 10px 15px rgba(0, 0, 0, 0.5)"
    
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
        """Get modern card styling."""
        import flet as ft
        return {
            "elevation": 4,
            "color": ModernTheme.BG_ELEVATED,
            "margin": ft.margin.only(bottom=12),
        }
    
    @staticmethod
    def get_button_style_gradient(colors=None):
        """Get gradient button style."""
        import flet as ft
        
        if colors is None:
            colors = ModernTheme.GRADIENT_PRIMARY
            
        return ft.ButtonStyle(
            bgcolor="transparent",
            elevation=0,
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
        )



