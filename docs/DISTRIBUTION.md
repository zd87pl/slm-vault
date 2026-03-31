# Enclave MVP Distribution Guide

## Overview

This guide explains how to package and distribute the Enclave application for MVP testing.

## System Requirements

### For Building
- macOS 10.13 or later
- Python 3.11+ (for building only)
- Flet CLI installed (`pip install flet`)
- Xcode Command Line Tools

### For End Users
- macOS 10.13 or later
- Apple Silicon (M1/M2/M3) or Intel Mac
- 2GB free disk space
- No Python installation required (all bundled)
- For Apple Silicon local AI, expect a one-time MLX model download on first use unless you pre-seed the cache

## Building the Distribution Package

### Quick Build

```bash
# From project root
cd scripts
./package_for_distribution.sh [version]
```

Example:
```bash
./package_for_distribution.sh 0.1.0
```

This will:
1. Build the macOS app bundle using Flet
2. Create a distribution directory
3. Package everything into a ZIP file
4. Generate checksums

### Manual Build Steps

1. **Build the app bundle:**
   ```bash
   cd advanced_vault/gui
   ./build_macos_app.sh
   ```

2. **Create distribution package:**
   ```bash
   cd ../../scripts
   ./package_for_distribution.sh
   ```

3. **Find the package:**
   ```bash
   ls -lh dist/Enclave-MVP-v*.zip
   ```

## Distribution Package Contents

```
Enclave-MVP-v0.1.0.zip
├── Enclave.app/              # Main application bundle
├── install_enclave.sh        # Optional installer script
├── INSTALLER_README.txt      # Quick start guide for testers
└── CHANGELOG.md              # Release notes
```

## Testing the Package

### Before Distribution

1. **Test on clean system:**
   - Extract ZIP on a clean macOS system (or VM)
   - Launch app without Python installed
   - Verify all features work

2. **Test installation:**
   ```bash
   cd dist/Enclave-MVP-v0.1.0
   ./install_enclave.sh
   ```

3. **Verify app launches:**
   ```bash
   open /Applications/Enclave.app
   ```

### Testing Checklist

- [ ] App launches without Python installed
- [ ] All dependencies bundled correctly
- [ ] First-run local model download works and finishes into the shared app cache
- [ ] Environment variables load properly
- [ ] PDF processing works (MLX dependencies)
- [ ] Cloud sync works (Supabase connection)
- [ ] File permissions set correctly
- [ ] App can be moved to Applications folder
- [ ] No console errors on launch
- [ ] All UI components render correctly

## Distribution Methods

## Local Model Handling

- Bundle the MLX runtime inside `Enclave.app`, but do not bundle model weights inside the app.
- On first use, the app downloads the selected MLX model into `~/Library/Application Support/Enclave/models` by default.
- If you need a fully offline demo machine, pre-seed that cache directory before distributing the app.
- You can override the cache root with `ENCLAVE_MODEL_CACHE_DIR`.

### Direct Download (MVP)

1. Upload ZIP to file sharing service (Dropbox, Google Drive, etc.)
2. Share download link with testers
3. Include `INSTALLER_README.txt` in email/instructions

### Internal Distribution

1. Host on internal file server
2. Share link via Slack/email
3. Provide installation instructions

### Future: DMG Installer

For production releases, consider creating a DMG installer:
- More professional appearance
- Drag-and-drop installation
- Requires code signing for Gatekeeper

## Configuration

### Default Environment Variables

The app includes default configuration for:
- `SUPABASE_URL`: Backend database URL
- `ENCLAVE_BACKEND_URL`: API endpoint URL

### User Override

Users can override defaults by creating `~/.enclave/config.env`:

```bash
mkdir -p ~/.enclave
cat > ~/.enclave/config.env << EOF
SUPABASE_URL=https://custom.supabase.co
SUPABASE_ANON_KEY=your_key_here
ENCLAVE_BACKEND_URL=https://custom.backend.com
EOF
```

## Troubleshooting

### Build Issues

**Error: flet CLI not found**
```bash
pip install flet
```

**Error: Python version mismatch**
- Ensure Python 3.11+ is installed
- Check `python3 --version`

**Error: Build fails**
- Check `advanced_vault/gui/requirements.txt` exists
- Verify all dependencies are installable
- Check Flet version compatibility

### Distribution Issues

**App won't launch on tester's Mac**
- Check macOS version compatibility
- Verify architecture (Intel vs Apple Silicon)
- Check Gatekeeper settings (may need to right-click → Open)

**Missing dependencies**
- Rebuild app bundle
- Verify `requirements.txt` includes all packages
- Check Flet build logs

## Security Considerations

### Code Signing (Future)

For production releases:
1. Obtain Apple Developer certificate
2. Sign the app bundle
3. Notarize with Apple
4. Enables Gatekeeper compatibility

### For MVP Testing

- App is unsigned (normal for testing)
- Testers may need to right-click → Open on first launch
- Include instructions in `INSTALLER_README.txt`

## Version Management

### Versioning Scheme

Use semantic versioning: `MAJOR.MINOR.PATCH`

- MVP releases: `0.1.0`, `0.1.1`, etc.
- Production: `1.0.0`, `1.1.0`, etc.

### Release Notes

Include in `CHANGELOG.md`:
- Version number
- What's new
- Known issues
- Installation instructions

## Support for Testers

### Common Issues

1. **"App is damaged" error**
   - Solution: Right-click → Open (first time only)

2. **App won't start**
   - Check macOS version (10.13+)
   - Check disk space (2GB+)
   - Check Console.app for errors

3. **Features not working**
   - Verify internet connection (for cloud sync)
   - Check `~/.vault/` directory permissions
   - Review logs in Console.app

### Reporting Issues

Testers should provide:
- macOS version (`sw_vers`)
- Mac model and architecture
- Steps to reproduce
- Error messages (if any)
- Screenshots (if applicable)

## Next Steps

After MVP testing:
1. Collect feedback
2. Fix critical issues
3. Add code signing
4. Create DMG installer
5. Prepare for wider distribution
