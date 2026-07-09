#!/bin/bash
# Install Enclave.app to Applications folder
#
# NOTE: this script ships INSIDE the packaged distribution ZIP (see
# scripts/package_for_distribution.sh) and expects a pre-built Enclave.app
# next to it. Installing from source? Use ./setup.sh instead.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Enclave.app"
APP_SOURCE="$SCRIPT_DIR/$APP_NAME"
APP_DEST="/Applications/$APP_NAME"

echo "🔐 Enclave Installer"
echo ""

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ Error: This installer is for macOS only"
    exit 1
fi

# Check macOS version
MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(echo $MACOS_VERSION | cut -d. -f1)
MACOS_MINOR=$(echo $MACOS_VERSION | cut -d. -f2)

if [ "$MACOS_MAJOR" -lt 10 ] || ([ "$MACOS_MAJOR" -eq 10 ] && [ "$MACOS_MINOR" -lt 13 ]); then
    echo "❌ Error: macOS 10.13 or later is required"
    echo "   Your version: $MACOS_VERSION"
    exit 1
fi

echo "✓ macOS version: $MACOS_VERSION"
echo ""

# Check if app exists in current directory
if [ ! -d "$APP_SOURCE" ]; then
    echo "❌ Error: $APP_NAME not found in current directory"
    echo "   Expected location: $APP_SOURCE"
    echo ""
    echo "   Please run this script from the directory containing $APP_NAME"
    exit 1
fi

echo "📦 Found: $APP_SOURCE"
echo ""

# Check if app already exists in Applications
if [ -d "$APP_DEST" ]; then
    echo "⚠️  Warning: $APP_NAME already exists in Applications folder"
    echo ""
    read -p "   Replace existing installation? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Installation cancelled"
        exit 0
    fi
    echo "   Removing existing installation..."
    rm -rf "$APP_DEST"
fi

# Copy app to Applications folder
echo "📥 Installing to Applications folder..."
echo "   Source: $APP_SOURCE"
echo "   Destination: $APP_DEST"
echo ""

cp -R "$APP_SOURCE" "$APP_DEST"

# Set permissions
chmod -R 755 "$APP_DEST"

echo "✅ Installation complete!"
echo ""
echo "📱 You can now launch Enclave from:"
echo "   • Applications folder"
echo "   • Spotlight (Cmd+Space, type 'Enclave')"
echo "   • Launchpad"
echo ""
echo "🚀 To launch now, run:"
echo "   open /Applications/$APP_NAME"
echo ""

# Ask if user wants to launch now
read -p "   Launch Enclave now? (Y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "   Launching Enclave..."
    open "$APP_DEST"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  First Launch Note"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "On first launch, macOS may show a security warning."
echo "This is normal for unsigned apps (MVP testing)."
echo ""
echo "To allow Enclave to run:"
echo "  1. Right-click the app in Applications"
echo "  2. Select 'Open'"
echo "  3. Click 'Open' in the security dialog"
echo ""
echo "After the first launch, you can double-click normally."
echo ""

