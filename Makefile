# Enclave Vault Build System
# ==========================
#
# Build installable packages for macOS, Windows, and Linux
#
# Prerequisites:
#   pip install pyinstaller flet[packaging]
#
# Common commands:
#   make install      - Install package in development mode
#   make build        - Create standalone executable for current platform
#   make build-mac    - Create macOS .app bundle
#   make build-win    - Create Windows .exe
#   make build-linux  - Create Linux binary
#   make dmg          - Create macOS DMG installer
#   make installer    - Create platform-specific installer
#   make clean        - Remove build artifacts

.PHONY: all install dev test lint build build-mac build-win build-linux dmg installer clean help

PYTHON := python3
PIP := pip3
APP_NAME := Enclave
VERSION := 0.1.0

# Detect OS
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    OS := macos
    INSTALLER_EXT := dmg
else ifeq ($(UNAME_S),Linux)
    OS := linux
    INSTALLER_EXT := AppImage
else
    OS := windows
    INSTALLER_EXT := exe
endif

# Default target
all: build

# ============================================================================
# Development
# ============================================================================

# One-command setup for beta users (venv + platform-appropriate extras + doctor)
quickstart:
	./setup.sh

install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev,gui]"

# Install with all optional dependencies (MLX on Apple Silicon)
install-all:
	$(PIP) install -e ".[all]"

test:
	$(PYTHON) -m pytest tests/ advanced_vault/ -v --tb=short

lint:
	$(PYTHON) -m ruff check advanced_vault/
	$(PYTHON) -m mypy advanced_vault/ --ignore-missing-imports

format:
	$(PYTHON) -m black advanced_vault/
	$(PYTHON) -m ruff check --fix advanced_vault/

# ============================================================================
# Build Executables
# ============================================================================

# Build for current platform
build:
ifeq ($(OS),macos)
	@$(MAKE) build-mac
else ifeq ($(OS),linux)
	@$(MAKE) build-linux
else
	@$(MAKE) build-win
endif

# macOS .app bundle
build-mac:
	@echo "Building macOS app..."
	@mkdir -p dist
	flet pack advanced_vault/gui/vault_app.py \
		--name $(APP_NAME) \
		--product-name "Enclave Vault" \
		--product-version $(VERSION) \
		--bundle-id ai.enclave.vault \
		--copyright "Apache 2.0 License" \
		--add-data "advanced_vault:advanced_vault"
	@echo "Built: dist/$(APP_NAME).app"

# Alternative: PyInstaller build (more control)
build-mac-pyinstaller:
	@echo "Building macOS app with PyInstaller..."
	pyinstaller enclave.spec --clean --noconfirm
	@echo "Built: dist/$(APP_NAME).app"

# Windows executable
build-win:
	@echo "Building Windows executable..."
	flet pack advanced_vault/gui/vault_app.py \
		--name $(APP_NAME) \
		--product-name "Enclave Vault" \
		--product-version $(VERSION) \
		--add-data "advanced_vault;advanced_vault"
	@echo "Built: dist/$(APP_NAME).exe"

# Linux binary
build-linux:
	@echo "Building Linux binary..."
	flet pack advanced_vault/gui/vault_app.py \
		--name $(APP_NAME) \
		--product-name "Enclave Vault" \
		--product-version $(VERSION) \
		--add-data "advanced_vault:advanced_vault"
	@echo "Built: dist/$(APP_NAME)"

# ============================================================================
# Create Installers
# ============================================================================

# Platform-specific installer
installer:
ifeq ($(OS),macos)
	@$(MAKE) dmg
else ifeq ($(OS),linux)
	@$(MAKE) appimage
else
	@$(MAKE) msi
endif

# macOS DMG installer
dmg: build-mac
	@echo "Creating DMG installer..."
	@mkdir -p dist/dmg
	@rm -rf dist/dmg/*
	@cp -R dist/$(APP_NAME).app dist/dmg/
	@ln -s /Applications dist/dmg/Applications
	hdiutil create -volname "$(APP_NAME)" \
		-srcfolder dist/dmg \
		-ov -format UDZO \
		dist/$(APP_NAME)-$(VERSION).dmg
	@rm -rf dist/dmg
	@echo "Created: dist/$(APP_NAME)-$(VERSION).dmg"

# Linux AppImage
appimage: build-linux
	@echo "Creating AppImage..."
	@mkdir -p dist/AppDir/usr/bin
	@mkdir -p dist/AppDir/usr/share/applications
	@mkdir -p dist/AppDir/usr/share/icons/hicolor/256x256/apps
	@cp dist/$(APP_NAME) dist/AppDir/usr/bin/
	@echo "[Desktop Entry]" > dist/AppDir/$(APP_NAME).desktop
	@echo "Name=Enclave Vault" >> dist/AppDir/$(APP_NAME).desktop
	@echo "Exec=$(APP_NAME)" >> dist/AppDir/$(APP_NAME).desktop
	@echo "Icon=$(APP_NAME)" >> dist/AppDir/$(APP_NAME).desktop
	@echo "Type=Application" >> dist/AppDir/$(APP_NAME).desktop
	@echo "Categories=Utility;Security;" >> dist/AppDir/$(APP_NAME).desktop
	@cp dist/AppDir/$(APP_NAME).desktop dist/AppDir/usr/share/applications/
	@if [ -f assets/icon.png ]; then cp assets/icon.png dist/AppDir/usr/share/icons/hicolor/256x256/apps/$(APP_NAME).png; fi
	@echo "#!/bin/bash" > dist/AppDir/AppRun
	@echo 'exec "$$APPDIR/usr/bin/$(APP_NAME)" "$$@"' >> dist/AppDir/AppRun
	@chmod +x dist/AppDir/AppRun
	@ARCH=x86_64 appimagetool dist/AppDir dist/$(APP_NAME)-$(VERSION).AppImage || echo "Note: Install appimagetool for AppImage creation"
	@echo "Created: dist/$(APP_NAME)-$(VERSION).AppImage"

# Windows MSI (requires WiX toolset)
msi: build-win
	@echo "Note: MSI creation requires WiX toolset (https://wixtoolset.org)"
	@echo "For simple distribution, use dist/$(APP_NAME).exe directly"
	@echo "Or use NSIS: makensis installer.nsi"

# ============================================================================
# MCP Server
# ============================================================================

# Run MCP server for Claude Desktop integration
mcp-server:
	$(PYTHON) -m advanced_vault.mcp_server

# Install MCP server config for Claude Desktop (merges into the existing
# config at the correct per-platform path — never clobbers other servers)
install-mcp:
	$(PYTHON) -m advanced_vault.cli mcp install

# ============================================================================
# Docker (for self-hosted deployment)
# ============================================================================

docker-build:
	docker build -t enclave-vault:$(VERSION) .

docker-run:
	docker run -p 8080:8080 -v ~/.enclave:/data enclave-vault:$(VERSION)

# ============================================================================
# Release
# ============================================================================

# Create release artifacts for all platforms (run on each platform)
release: clean build installer
	@echo "Release artifacts created in dist/"
	@ls -la dist/

# Build Python packages (wheel and sdist)
dist-python:
	$(PYTHON) -m build
	@echo "Python packages created in dist/"

# ============================================================================
# Cleanup
# ============================================================================

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .eggs/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ============================================================================
# Help
# ============================================================================

help:
	@echo "Enclave Vault Build System"
	@echo "=========================="
	@echo ""
	@echo "Development:"
	@echo "  make install      Install in development mode"
	@echo "  make dev          Install with dev dependencies"
	@echo "  make test         Run tests"
	@echo "  make lint         Run linters"
	@echo ""
	@echo "Build Executables:"
	@echo "  make build        Build for current platform"
	@echo "  make build-mac    Build macOS .app"
	@echo "  make build-win    Build Windows .exe"
	@echo "  make build-linux  Build Linux binary"
	@echo ""
	@echo "Create Installers:"
	@echo "  make installer    Create installer for current platform"
	@echo "  make dmg          Create macOS DMG"
	@echo "  make appimage     Create Linux AppImage"
	@echo ""
	@echo "MCP Server:"
	@echo "  make mcp-server   Run MCP server"
	@echo "  make install-mcp  Install MCP config for Claude Desktop"
	@echo ""
	@echo "Release:"
	@echo "  make release      Create release artifacts"
	@echo "  make dist-python  Build Python wheel/sdist"
	@echo ""
	@echo "Detected OS: $(OS)"
