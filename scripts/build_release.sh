#!/bin/bash
# Build release package for distribution
# This script automates the entire build and packaging process

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Get version from argument or use default
VERSION="${1:-0.1.0}"

echo "═══════════════════════════════════════════════════════════════"
echo "  Enclave Release Builder v$VERSION"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✓ $PYTHON_VERSION"

# Check Flet
if ! command -v flet &> /dev/null; then
    echo "❌ Error: flet CLI not found"
    echo "   Install with: pip install flet"
    exit 1
fi
FLET_VERSION=$(flet --version 2>/dev/null || echo "unknown")
echo "✓ Flet $FLET_VERSION"

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "⚠️  Warning: Not running on macOS. Build may not work correctly."
else
    MACOS_VERSION=$(sw_vers -productVersion)
    echo "✓ macOS $MACOS_VERSION"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1: Clean Previous Builds"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Clean build directories
GUI_DIR="$PROJECT_ROOT/advanced_vault/gui"
DIST_DIR="$PROJECT_ROOT/dist"

if [ -d "$GUI_DIR/build" ]; then
    echo "🧹 Cleaning GUI build directory..."
    rm -rf "$GUI_DIR/build"
fi

if [ -d "$DIST_DIR" ]; then
    echo "🧹 Cleaning distribution directory..."
    rm -rf "$DIST_DIR"
fi

mkdir -p "$DIST_DIR"

echo "✅ Clean complete"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2: Build App Bundle"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$GUI_DIR"

if [ ! -f "build_macos_app.sh" ]; then
    echo "❌ Error: build_macos_app.sh not found"
    exit 1
fi

chmod +x build_macos_app.sh
./build_macos_app.sh

if [ ! -d "build/macos/Enclave.app" ]; then
    echo "❌ Error: App bundle build failed"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3: Create Distribution Package"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_ROOT/scripts"

if [ ! -f "package_for_distribution.sh" ]; then
    echo "❌ Error: package_for_distribution.sh not found"
    exit 1
fi

chmod +x package_for_distribution.sh
./package_for_distribution.sh "$VERSION"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4: Generate Release Notes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

DIST_NAME="Enclave-MVP-v$VERSION"
RELEASE_NOTES="$DIST_DIR/$DIST_NAME/RELEASE_NOTES.md"

cat > "$RELEASE_NOTES" << EOF
# Enclave MVP Release v$VERSION

**Release Date:** $(date +"%Y-%m-%d")
**Build Platform:** $(uname -s) $(uname -m)

## What's Included

- Standalone macOS application bundle
- All Python dependencies bundled
- Default configuration for backend services
- Installer script for easy setup

## Installation

1. Extract \`${DIST_NAME}.zip\`
2. Double-click \`Enclave.app\` to launch, or
3. Run \`./install_enclave.sh\` to install to Applications folder

## System Requirements

- macOS 10.13 or later
- Apple Silicon (M1/M2/M3) or Intel Mac
- 2GB free disk space
- Internet connection (for cloud sync)

## Changes in This Release

- Initial MVP release
- Standalone packaging (no Python required)
- Default backend configuration
- PDF processing support
- Cloud sync functionality

## Known Issues

- App is unsigned (requires right-click → Open on first launch)
- Some features may be incomplete (MVP stage)

## Support

For issues or questions, please contact the development team.

## Build Information

- Python: $PYTHON_VERSION
- Flet: $FLET_VERSION
- macOS: ${MACOS_VERSION:-N/A}
- Build Date: $(date)
EOF

echo "✅ Release notes generated: $RELEASE_NOTES"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 5: Final Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ZIP_FILE="$DIST_DIR/${DIST_NAME}.zip"

if [ ! -f "$ZIP_FILE" ]; then
    echo "❌ Error: Distribution ZIP not found"
    exit 1
fi

ZIP_SIZE=$(du -sh "$ZIP_FILE" | cut -f1)
echo "✓ Distribution package: $ZIP_FILE ($ZIP_SIZE)"

if [ -f "${ZIP_FILE}.sha256" ]; then
    echo "✓ Checksum file: ${ZIP_FILE}.sha256"
    echo "   $(cat ${ZIP_FILE}.sha256)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Build Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📦 Distribution package ready:"
echo "   $ZIP_FILE"
echo ""
echo "📋 Package contents:"
ls -lh "$DIST_DIR/$DIST_NAME" | tail -n +2 | awk '{print "   " $9 " (" $5 ")"}'
echo ""
echo "🚀 Next steps:"
echo "   1. Test the package on a clean macOS system"
echo "   2. Verify all features work correctly"
echo "   3. Share with testers"
echo ""
echo "📝 Distribution checklist:"
echo "   [ ] Tested on clean macOS system"
echo "   [ ] Verified app launches correctly"
echo "   [ ] Tested all major features"
echo "   [ ] Updated CHANGELOG.md"
echo "   [ ] Ready for distribution"
echo ""

