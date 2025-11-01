# Flet App Distribution on macOS

## Current Status

**Your app is a Flet app** - a Python-based desktop application that uses Flutter for the UI.

**Current setup:** Users run it via `launch_enclave_gui.sh` script, which:
- Sets environment variables
- Runs `python3 vault_app.py` directly
- Requires Python 3 installed on the Mac

**This is NOT a standard macOS app** - it's a development/script-based launch.

---

## Standard macOS App Distribution

### What Users Expect

On macOS, users expect:
- **`.app` bundle** - Double-clickable application
- **Installed in `/Applications`** - Standard location
- **No terminal required** - Just double-click to launch
- **Code signing** - For security and Gatekeeper
- **Notarization** - For distribution outside Mac App Store

### Current vs. Standard

| Current | Standard macOS App |
|---------|-------------------|
| Run via shell script | Double-click `.app` bundle |
| Requires Python installed | Self-contained (includes Python) |
| Requires manual env vars | Bundled configuration |
| Terminal-based launch | GUI launch from Finder |
| Development setup | Production-ready |

---

## How to Package Flet App for macOS

### Option 1: Flet CLI (Recommended)

Flet provides native macOS packaging:

```bash
# Install Flet CLI (if not already installed)
pip install flet

# Build macOS app bundle
cd advanced_vault/gui
flet build macos
```

**Requirements:**
- **Rosetta 2** (for Apple Silicon): `sudo softwareupdate --install-rosetta --agree-to-license`
- **Xcode 15+**: For compiling native code
- **CocoaPods 1.16+**: For Flutter plugins

**Output:**
- Creates `.app` bundle in `build/macos/`
- Universal binary (Apple Silicon + Intel)
- Ready to distribute

### Option 2: PyInstaller (Alternative)

If Flet CLI doesn't work, use PyInstaller:

```bash
# Install PyInstaller
pip install pyinstaller

# Create spec file
pyinstaller --name="Enclave" \
    --windowed \
    --onefile \
    --icon=icon.icns \
    --add-data "advanced_vault/gui:advanced_vault/gui" \
    advanced_vault/gui/vault_app.py
```

**Output:**
- Creates standalone executable
- Requires wrapping in `.app` bundle manually

---

## Recommended Distribution Setup

### For Alpha Launch:

**Option A: Flet CLI (Simplest)**
```bash
flet build macos
# Creates: build/macos/Enclave.app
```

**Option B: Manual `.app` Bundle**
1. Create `Enclave.app/Contents/` structure
2. Bundle Python + dependencies
3. Create `Info.plist` with app metadata
4. Create launcher script

---

## Distribution Checklist

### Before Distribution:

- [ ] **Code Signing** - Sign app with Apple Developer certificate
- [ ] **Notarization** - Submit to Apple for notarization
- [ ] **Gatekeeper** - Ensure app passes Gatekeeper checks
- [ ] **Environment Variables** - Bundle securely (not in script)
- [ ] **Icon** - Create `.icns` file for app icon
- [ ] **Bundle ID** - Set unique bundle identifier
- [ ] **Permissions** - Request necessary macOS permissions

### Distribution Methods:

1. **Direct Download** - Host `.app` or `.dmg` on your website
2. **Mac App Store** - Requires App Store Connect account ($99/year)
3. **Homebrew Cask** - For technical users

---

## Environment Variables Issue

**Current Problem:**
Your `launch_enclave_gui.sh` has hardcoded credentials in plaintext.

**Solution for Packaged App:**
1. **Store in app bundle** - `Enclave.app/Contents/Resources/config.json`
2. **Keychain** - Store sensitive data in macOS Keychain
3. **Backend-only** - Remove from client (already done for RunPod)

Since you're moving to SaaS model, you should:
- ✅ Remove all env vars from client
- ✅ Fetch config from backend `/api/config` endpoint
- ✅ Store only user session locally

---

## Quick Start: Create macOS App

### Step 1: Install Prerequisites

```bash
# Install Rosetta 2 (if on Apple Silicon)
sudo softwareupdate --install-rosetta --agree-to-license

# Install Xcode from App Store (if not installed)
# Install CocoaPods
sudo gem install cocoapods
```

### Step 2: Build with Flet

```bash
cd advanced_vault/gui

# Build macOS app
flet build macos

# Output: build/macos/Enclave.app
```

### Step 3: Test Locally

```bash
# Run the app bundle
open build/macos/Enclave.app
```

### Step 4: Create DMG (Optional)

```bash
# Create disk image for distribution
hdiutil create -volname "Enclave" \
    -srcfolder build/macos/Enclave.app \
    -ov -format UDZO \
    Enclave.dmg
```

---

## Recommended Architecture Changes

### For SaaS Model:

1. **Remove launch script** - No longer needed
2. **Fetch config from backend** - `/api/config` endpoint
3. **Store session locally** - In macOS Keychain
4. **Auto-update** - Optional: Implement Sparkle or similar

### Updated Flow:

```
User downloads Enclave.app
    ↓
Double-clicks to launch
    ↓
App fetches config from backend
    ↓
User logs in
    ↓
Session stored in Keychain
    ↓
App works (no env vars needed)
```

---

## Next Steps

1. **Test Flet CLI build** - See if it works with your app
2. **Create app icon** - Design `.icns` file
3. **Remove env vars** - Move to backend config endpoint
4. **Code signing** - Get Apple Developer account ($99/year)
5. **Test distribution** - Create DMG and test on fresh Mac

---

## References

- [Flet macOS Packaging Docs](https://flet.dev/docs/publish/macos/)
- [macOS App Distribution Guide](https://developer.apple.com/distribute/)
- [Code Signing Guide](https://developer.apple.com/documentation/security/code_signing_services)

