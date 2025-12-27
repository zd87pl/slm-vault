#!/bin/bash
# Build macOS App Bundle with all dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

# Check Flet version
FLET_VERSION=$(flet --version 2>/dev/null || echo "unknown")
echo "📋 Flet version: $FLET_VERSION"
echo ""

# Check if flet.json exists
if [ ! -f "flet.json" ]; then
    echo "⚠️  Warning: flet.json not found. Using default configuration."
    echo "   Consider creating flet.json for better control."
    echo ""
fi

echo "📦 Checking dependencies..."
echo ""

# Verify requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found"
    exit 1
fi

# Verify all required packages are in requirements.txt
echo "Required packages:"
cat requirements.txt | grep -v "^#" | grep -v "^$" || true
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "🐍 Python version: $PYTHON_VERSION"
echo ""

# Clean previous builds
if [ -d "build" ]; then
    echo "🧹 Cleaning previous builds..."
    rm -rf build
    echo ""
fi

# Build the app bundle
echo "🔨 Building macOS app bundle..."
echo "This will bundle all dependencies including MCP package..."
echo "   This may take several minutes..."
echo ""

# Build with Flet CLI
flet build macos

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    
    # Verify app bundle exists
    if [ -d "build/macos/Enclave.app" ]; then
        APP_SIZE=$(du -sh "build/macos/Enclave.app" | cut -f1)
        echo "📦 App bundle location:"
        echo "   $(pwd)/build/macos/Enclave.app"
        echo "   Size: $APP_SIZE"
        echo ""
        
        # Validate bundle structure
        echo "🔍 Validating app bundle..."
        if [ -f "build/macos/Enclave.app/Contents/MacOS/Enclave" ]; then
            echo "   ✓ Executable found"
        else
            echo "   ⚠️  Warning: Executable not found in expected location"
        fi
        
        if [ -d "build/macos/Enclave.app/Contents/Resources" ]; then
            echo "   ✓ Resources directory found"
        else
            echo "   ⚠️  Warning: Resources directory not found"
        fi
        
        echo ""
        echo "🧪 To test:"
        echo "   open build/macos/Enclave.app"
        echo ""
        echo "📝 Note: All dependencies (including MCP) are bundled in the app."
        echo "   Users don't need to install anything manually."
    else
        echo "⚠️  Warning: App bundle not found at expected location"
        echo "   Check build output above for errors"
    fi
else
    echo ""
    echo "❌ Build failed. Check the error messages above."
    exit 1
fi

