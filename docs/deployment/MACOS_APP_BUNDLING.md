# macOS App Bundle Packaging Guide

## Overview

When you build the macOS app bundle using Flet CLI, **all dependencies from `requirements.txt` are automatically bundled** into the app. This means users don't need to install anything manually - the app is self-contained.

## What Gets Bundled

All packages listed in `advanced_vault/gui/requirements.txt` are automatically included:

- ✅ **Flet** - GUI framework
- ✅ **Supabase/GoTrue** - Backend integration
- ✅ **Requests** - HTTP client
- ✅ **MCP** - Model Context Protocol (for Claude Desktop)
- ✅ **PyPDF2** - PDF processing
- ✅ **All transitive dependencies** - Automatically resolved

## Building the App Bundle

### Option 1: Using the Build Script (Recommended)

```bash
cd advanced_vault/gui
./build_macos_app.sh
```

This script:
- Checks dependencies
- Builds the app bundle
- Verifies all packages are included

### Option 2: Using Flet CLI Directly

```bash
cd advanced_vault/gui
flet build macos
```

**Output:**
- Creates `build/macos/Enclave.app`
- Includes all dependencies from `requirements.txt`
- Self-contained bundle (no Python installation needed)

## Verifying Dependencies Are Bundled

After building, you can verify MCP is included:

```bash
# Check the app bundle contents
ls -la build/macos/Enclave.app/Contents/Resources/

# Or check Python site-packages inside the bundle
find build/macos/Enclave.app -name "mcp" -type d
```

## Adding New Dependencies

If you add a new dependency:

1. **Add to `requirements.txt`**:
   ```txt
   new-package>=1.0.0
   ```

2. **Rebuild the app bundle**:
   ```bash
   ./build_macos_app.sh
   ```

3. **The new package will be automatically bundled**

## Current Dependencies

See `advanced_vault/gui/requirements.txt` for the complete list.

**Key packages:**
- `flet>=0.28.3` - GUI framework
- `mcp>=1.0.0` - MCP server support
- `supabase==2.9.0` - Backend integration
- `PyPDF2>=3.0.0` - PDF processing

## Distribution

### For Users

Users receive:
- **Single `.app` bundle** - Double-click to launch
- **No installation needed** - All dependencies included
- **No Python required** - Python runtime bundled
- **No pip install** - Everything is pre-packaged

### Distribution Methods

1. **Direct Download** - Host `.app` or `.dmg` on your website
2. **DMG Creation**:
   ```bash
   hdiutil create -volname "Enclave" \
       -srcfolder build/macos/Enclave.app \
       -ov -format UDZO \
       Enclave.dmg
   ```

## Troubleshooting

### Package Not Found After Build

If a package is missing after building:

1. **Check `requirements.txt`** - Ensure it's listed
2. **Rebuild cleanly**:
   ```bash
   rm -rf build/
   flet build macos
   ```

### MCP Import Error

If MCP is not found in the bundled app:

1. **Verify in requirements.txt**:
   ```bash
   grep mcp requirements.txt
   ```

2. **Rebuild**:
   ```bash
   ./build_macos_app.sh
   ```

3. **Test the bundle**:
   ```bash
   open build/macos/Enclave.app
   ```

## Next Steps

1. ✅ **Dependencies Added** - MCP is in `requirements.txt`
2. ✅ **Build Script Created** - `build_macos_app.sh`
3. ⏳ **Build Test** - Run `./build_macos_app.sh` to verify
4. ⏳ **Distribution** - Create DMG and test on fresh Mac

---

**Note:** Flet CLI automatically resolves and bundles all dependencies. No manual packaging needed!

