# Personal Vault - macOS Menu Bar App

A native macOS menu bar application for managing your personal vault.

## Features

- **Menu Bar Integration**: Always accessible from your macOS menu bar
- **Quick Add**: Add secrets and notes with simple dialogs
- **View Secrets**: Browse all stored secrets
- **Smart Search**: Query vault using natural language
- **Statistics**: View vault stats at a glance
- **Secure**: Uses same encryption as CLI (ChaCha20-Poly1305)

## Installation

### Requirements
- macOS 10.13 or later
- Python 3.8+
- rumps library

### Install

```bash
# Install dependencies
pip install rumps

# Run the app
python -m advanced_vault.macos_app.vault_app
```

## Usage

### Starting the App

```bash
python advanced_vault/macos_app/vault_app.py
```

The vault icon (🔐) will appear in your menu bar.

### Menu Options

**Add Secret**
1. Click "Add Secret"
2. Enter service name (e.g., "stripe", "github")
3. Enter the secret value
4. Done! Secret is encrypted and stored

**Add Note**
1. Click "Add Note"
2. Enter your knowledge note
3. Done! Note is stored for later retrieval

**View Secrets**
- Click "View Secrets" to see all stored entries
- Click on a service name to view its details

**Search**
- Click "Search..."
- Enter natural language query
- Uses Smart Router for automatic routing

**Statistics**
- Click "Statistics" to view vault stats
- Shows total entries, services, encryption info

**Settings**
- View vault path, encryption details

**Quit**
- Cleanly closes vault and exits app

## Screenshots

### Menu Bar
```
🔐 Vault
  ├─ Add Secret
  ├─ Add Note
  ├─────────────
  ├─ View Secrets
  ├─ Search...
  ├─────────────
  ├─ Statistics
  ├─ Settings
  ├─────────────
  └─ Quit
```

### Add Secret Dialog
```
┌────────────────────────────────┐
│  Add Secret - Step 1/2         │
├────────────────────────────────┤
│  Service name (e.g., stripe):  │
│  ┌──────────────────────────┐  │
│  │ stripe                   │  │
│  └──────────────────────────┘  │
│                                │
│          [Cancel]  [Next]      │
└────────────────────────────────┘
```

### View Secrets
```
┌────────────────────────────────┐
│  Vault Secrets (3)             │
├────────────────────────────────┤
│  • stripe                      │
│  • github                      │
│  • aws                         │
│                                │
│               [OK]             │
└────────────────────────────────┘
```

## Advanced

### Running at Startup

To have the app start automatically on login:

1. Save this as a script:
```bash
#!/bin/bash
cd /path/to/slm-vault
python advanced_vault/macos_app/vault_app.py
```

2. Make it executable:
```bash
chmod +x run_vault_app.sh
```

3. Add to Login Items:
   - System Settings → Users & Groups → Login Items
   - Click "+" and add the script

### Building as Standalone App

To create a standalone `.app` bundle:

```bash
# Install py2app
pip install py2app

# Create setup.py for app
python setup_macos_app.py py2app

# App will be in dist/VaultApp.app
```

## Security

- Master key stored at `~/.vault/master.key` (600 permissions)
- All secrets encrypted with ChaCha20-Poly1305
- Database at `~/.vault/vault.db`
- No secrets ever sent over network
- No cloud storage - all local

## Troubleshooting

### App doesn't start
```bash
# Check rumps is installed
pip list | grep rumps

# Run with verbose output
python -v advanced_vault/macos_app/vault_app.py
```

### Can't see menu bar icon
- Check if icon appears in menu bar
- Try quitting and restarting
- Check System Settings → Control Center → Menu Bar Only

### Secrets not saving
- Check permissions on `~/.vault/` directory
- Verify master key exists: `ls -la ~/.vault/master.key`
- Should show `-rw-------` (600)

## Integration

The macOS app shares the same vault as:
- CLI tool (`vault` command)
- MCP Server (Claude Desktop integration)

All three can be used interchangeably!

## Roadmap

- [ ] Copy to clipboard button for secrets
- [ ] Drag & drop import
- [ ] Touch ID integration
- [ ] Backup/restore
- [ ] Multi-vault support
- [ ] Hotkey for quick add

## License

Part of the Personal Vault project.
