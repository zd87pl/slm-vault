#!/usr/bin/env python3
"""
Generate extension icons for Enclave Vault browser extension.

Creates 16x16, 48x48, and 128x128 PNG icons with a lock/vault design.
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size):
    """Create an icon at the specified size."""
    # Create image with transparent background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Colors: Dark blue/violet theme
    primary_color = (88, 101, 242)  # #5865F2 - Discord-like blue
    secondary_color = (114, 137, 218)  # Lighter blue
    accent_color = (255, 255, 255)  # White
    
    # Calculate dimensions based on size
    padding = size // 8
    center_x = size // 2
    center_y = size // 2
    
    # Draw vault/lock shape
    # Main body (rounded rectangle)
    body_width = size - padding * 2
    body_height = size - padding * 2
    body_x = padding
    body_y = padding + (size // 6)  # Slightly lower for lock shape
    
    # Draw rounded rectangle (vault body)
    corner_radius = size // 8
    draw.rounded_rectangle(
        [body_x, body_y, body_x + body_width, body_y + body_height],
        radius=corner_radius,
        fill=primary_color
    )
    
    # Draw lock shackle (arc on top)
    shackle_width = size // 3
    shackle_height = size // 4
    shackle_x = center_x - shackle_width // 2
    shackle_y = padding
    
    # Draw shackle arc
    draw.arc(
        [shackle_x, shackle_y, shackle_x + shackle_width, shackle_y + shackle_height * 2],
        start=0,
        end=180,
        fill=secondary_color,
        width=max(2, size // 16)
    )
    
    # Draw keyhole (circle in center)
    keyhole_radius = size // 8
    draw.ellipse(
        [center_x - keyhole_radius, center_y - keyhole_radius // 2,
         center_x + keyhole_radius, center_y + keyhole_radius // 2],
        fill=accent_color
    )
    
    # Draw vertical line in keyhole
    draw.rectangle(
        [center_x - size // 32, center_y + keyhole_radius // 2,
         center_x + size // 32, center_y + keyhole_radius],
        fill=accent_color
    )
    
    return img

def main():
    """Generate all icon sizes."""
    sizes = [16, 48, 128]
    icons_dir = os.path.join(os.path.dirname(__file__), '..', 'icons')
    
    # Create icons directory if it doesn't exist
    os.makedirs(icons_dir, exist_ok=True)
    
    print(f"Generating icons in {icons_dir}...")
    
    for size in sizes:
        icon = create_icon(size)
        filename = f'icon-{size}.png'
        filepath = os.path.join(icons_dir, filename)
        icon.save(filepath, 'PNG')
        print(f"✓ Created {filename} ({size}x{size})")
    
    print("\nAll icons generated successfully!")
    print(f"Icons saved to: {icons_dir}")

if __name__ == '__main__':
    main()



