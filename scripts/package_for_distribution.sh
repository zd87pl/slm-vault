#!/bin/bash
# Package Enclave app for distribution to testers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUI_DIR="$PROJECT_ROOT/advanced_vault/gui"
DIST_DIR="$PROJECT_ROOT/dist"
VERSION="${1:-0.1.0}"

echo "📦 Packaging Enclave for Distribution (v$VERSION)"
echo ""

# Check if GUI directory exists
if [ ! -d "$GUI_DIR" ]; then
    echo "❌ Error: GUI directory not found at $GUI_DIR"
    exit 1
fi

# Build the app first
echo "🔨 Step 1: Building app bundle..."
cd "$GUI_DIR"
if [ ! -f "build_macos_app.sh" ]; then
    echo "❌ Error: build_macos_app.sh not found"
    exit 1
fi

chmod +x build_macos_app.sh
./build_macos_app.sh

if [ ! -d "build/macos/Enclave.app" ]; then
    echo "❌ Error: App bundle not found after build"
    exit 1
fi

echo ""
echo "📋 Step 2: Creating distribution package..."

# Create distribution directory
mkdir -p "$DIST_DIR"
DIST_NAME="Enclave-MVP-v$VERSION"
DIST_PATH="$DIST_DIR/$DIST_NAME"

# Clean previous distribution if exists
if [ -d "$DIST_PATH" ]; then
    echo "🧹 Cleaning previous distribution..."
    rm -rf "$DIST_PATH"
fi

if [ -f "${DIST_PATH}.zip" ]; then
    rm -f "${DIST_PATH}.zip"
fi

mkdir -p "$DIST_PATH"

# Copy app bundle
echo "   Copying app bundle..."
cp -R "$GUI_DIR/build/macos/Enclave.app" "$DIST_PATH/"

# Copy installer script
if [ -f "$PROJECT_ROOT/install_enclave.sh" ]; then
    echo "   Copying installer script..."
    cp "$PROJECT_ROOT/install_enclave.sh" "$DIST_PATH/"
    chmod +x "$DIST_PATH/install_enclave.sh"
fi

# Copy README
if [ -f "$PROJECT_ROOT/INSTALLER_README.txt" ]; then
    echo "   Copying README..."
    cp "$PROJECT_ROOT/INSTALLER_README.txt" "$DIST_PATH/"
fi

# Create CHANGELOG if it doesn't exist
if [ ! -f "$DIST_PATH/CHANGELOG.md" ]; then
    echo "   Creating CHANGELOG..."
    cat > "$DIST_PATH/CHANGELOG.md" << EOF
# Enclave MVP v$VERSION

## What's New

- Initial MVP release
- Standalone macOS application bundle
- All dependencies bundled - no Python installation required
- Works out-of-the-box with default configuration

## Installation

1. Extract the ZIP file
2. Double-click \`Enclave.app\` to launch, or
3. Run \`./install_enclave.sh\` to install to Applications folder

## System Requirements

- macOS 10.13 or later
- Apple Silicon (M1/M2/M3) or Intel Mac
- 2GB free disk space

## First Launch

On first launch, macOS may show a security warning. This is normal for unsigned apps.

To allow the app to run:
1. Right-click \`Enclave.app\`
2. Select "Open"
3. Click "Open" in the security dialog

## Support

For issues or questions, please contact the development team.
EOF
fi

echo ""
echo "📝 Step 3: Generating checksums..."

cd "$DIST_DIR"
# Create checksums
if command -v shasum &> /dev/null; then
    shasum -a 256 "$DIST_NAME.zip" > "${DIST_NAME}.sha256" 2>/dev/null || true
fi

echo ""
echo "🗜️  Step 4: Creating ZIP archive..."

cd "$DIST_DIR"
zip -r "${DIST_NAME}.zip" "$DIST_NAME" -x "*.DS_Store" "*.git*" "*.pyc" "__pycache__/*"

# Generate checksum for ZIP
if command -v shasum &> /dev/null; then
    shasum -a 256 "${DIST_NAME}.zip" > "${DIST_NAME}.sha256"
    echo "   Checksum saved to ${DIST_NAME}.sha256"
fi

ZIP_SIZE=$(du -sh "${DIST_NAME}.zip" | cut -f1)
echo ""
echo "✅ Distribution package created successfully!"
echo ""
echo "📦 Package location:"
echo "   ${DIST_NAME}.zip ($ZIP_SIZE)"
echo ""
echo "📋 Package contents:"
ls -lh "$DIST_PATH" | tail -n +2 | awk '{print "   " $9 " (" $5 ")"}'
echo ""
echo "🚀 Ready for distribution!"
echo "   Share the ZIP file with testers along with INSTALLER_README.txt"

