# Flet Compatibility Notes

## Version Compatibility

The Personal Vault GUI is tested with **Flet 0.28.3**.

## API Differences Across Versions

### Colors
- ❌ **Don't use**: `ft.colors.BLUE`, `ft.colors.ERROR`, etc.
- ✅ **Use instead**: Hex color strings `"#2196f3"`, `"#f44336"`

**Why**: The `ft.colors` module structure varies across Flet versions.

### Icons
- ❌ **Don't use**: `ft.icons.ADD_CIRCLE` (lowercase)
- ✅ **Use instead**: `ft.Icons.ADD_CIRCLE` (capital I)

**Why**: Flet uses `ft.Icons` (capital I) not `ft.icons`.

## Fixes Applied

The following changes were made to ensure compatibility:

1. **Color Constants** → **Hex Values**
   ```python
   # Before
   bgcolor=ft.colors.SURFACE_VARIANT

   # After
   bgcolor="#2c2c2c"
   ```

2. **Icon References** → **Capital Icons**
   ```python
   # Before
   ft.icons.ADD_CIRCLE

   # After
   ft.Icons.ADD_CIRCLE
   ```

## Color Palette

```python
# Material Design colors used in the app
SURFACE_VARIANT = "#2c2c2c"      # Dark surface
ON_SURFACE_VARIANT = "#9e9e9e"   # Gray text
BLUE = "#2196f3"                  # Primary blue
AMBER = "#ffc107"                 # Warning amber
ERROR = "#f44336"                 # Error red
GREEN = "#4caf50"                 # Success green
```

## Troubleshooting

### Error: "module 'flet' has no attribute 'colors'"
**Fix**: Replace `ft.colors.X` with hex colors (see palette above)

### Error: "module 'flet' has no attribute 'icons'"
**Fix**: Replace `ft.icons.X` with `ft.Icons.X` (capital I)

### App won't start
```bash
# Reinstall Flet
pip install --upgrade flet

# Clear cache
rm -rf ~/.flet
```

## Testing

To verify compatibility:
```bash
python3 -c "import flet as ft; print('Icons:', hasattr(ft, 'Icons')); print('Version OK')"
```

Expected output:
```
Icons: True
Version OK
```
