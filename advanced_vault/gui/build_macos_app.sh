#!/bin/bash
# Build macOS App Bundle with all dependencies

set -e

echo "🔨 Building Enclave macOS App Bundle..."
echo ""

# Check if we're in the right directory
if [ ! -f "vault_app.py" ]; then
    echo "❌ Error: vault_app.py not found. Run this script from advanced_vault/gui/ directory"
    exit 1
fi

# Check if flet is installed
if ! command -v flet &> /dev/null; then
    echo "❌ Error: flet CLI not found. Install with: pip install flet"
    exit 1
fi

echo "📦 Checking dependencies..."
echo ""

# Verify all required packages are in requirements.txt
echo "Required packages:"
cat requirements.txt | grep -v "^#" | grep -v "^$" || true
echo ""

# Build the app bundle
echo "🔨 Building macOS app bundle..."
echo "This will bundle all dependencies including MCP package..."
echo ""

cd "$(dirname "$0")"

# Build with Flet CLI
flet build macos

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "📦 App bundle location:"
    echo "   build/macos/Enclave.app"
    echo ""
    echo "🧪 To test:"
    echo "   open build/macos/Enclave.app"
    echo ""
    echo "📝 Note: All dependencies (including MCP) are bundled in the app."
    echo "   Users don't need to install anything manually."
else
    echo ""
    echo "❌ Build failed. Check the error messages above."
    exit 1
fi

