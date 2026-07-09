# Personal Vault GUI - Quick Start

## 🚀 Fastest Way to Start

```bash
# From the project root (after ./setup.sh)
source .venv/bin/activate
enclave-gui
```

That's it! The GUI will open in a new window.

## 📱 What You'll See

When the app opens, you'll see:

1. **Left sidebar** with navigation:
   - 🔑 Secrets
   - 💡 Knowledge
   - 📊 Statistics
   - ⚙️ Settings

2. **Top bar** with:
   - ➕ Add button (add new secret/knowledge)
   - 🔄 Refresh button

3. **Search bar** to filter entries

4. **Main area** showing your vault entries

## 🎯 Common Tasks

### Add a Secret

1. Click **➕** button in top-right
2. Select "Secret" or "Knowledge"
3. Enter:
   - **Service**: e.g., "stripe", "github", "aws"
   - **Content**: Your secret or knowledge
   - **Tags**: Comma-separated (e.g., "payment, production")
   - **Description**: Optional
4. Click **Add**

### View a Secret

1. Find the secret in the list
2. Click the **👁** (eye) button
3. View the content
4. Click **Copy** to copy to clipboard
5. Click **Close** when done

### Delete a Secret

1. Find the secret in the list
2. Click the **🗑** (trash) button
3. Confirm deletion

### Search/Filter

1. Use the **search bar** at the top to search by service name or tags
2. Use the **dropdown** to filter by type (All, Secrets, Knowledge)

### View Statistics

1. Click **📊 Statistics** in left sidebar
2. See:
   - Total entries
   - Services count
   - Layer 1/2 status

## 🎨 Features

✨ **Beautiful UI**
- Dark theme (easy on the eyes)
- Material Design
- Smooth animations

🔐 **Secure**
- All data encrypted with ChaCha20-Poly1305
- Master key at `~/.vault/master.key`
- No network access (all local)

⚡ **Fast**
- Instant search
- Real-time filtering
- Smooth scrolling

📋 **Convenient**
- One-click copy to clipboard
- Visual feedback (success/error messages)
- Easy navigation

## 🔧 Advanced Usage

### Package as Standalone App

```bash
# Package as .app bundle (from the project root)
make build-mac

# Result: dist/Enclave.app — move it to Applications:
mv dist/Enclave.app /Applications/
```

Now you can:
- Launch from Applications folder
- Add to Dock
- Add to Login Items for auto-start

### Run from Python Directly

```bash
python -m advanced_vault.gui.vault_app
```

### Use with CLI

The GUI shares the same vault as the CLI:

```bash
# Add via CLI
enclave add-secret github ghp_abc123

# View in GUI - it will appear immediately!
enclave-gui
```

## 🐛 Troubleshooting

### App won't start

```bash
# Check flet is installed
pip list | grep flet

# Reinstall if needed
pip install --upgrade flet
```

### Can't see my secrets

Make sure you're using the same vault:
```bash
# Check vault exists
ls -la ~/.vault/

# Should see:
# - master.key
# - vault.db
```

### Errors when adding secrets

- Make sure to fill in **Service** and **Content** (required fields)
- Check terminal for error messages

## 💡 Tips

1. **Tags are powerful**: Use tags like "production", "staging", "payment" to organize
2. **Search is fast**: Type partial service names or tags
3. **Copy is quick**: Click the eye 👁, then Copy 📋
4. **Use keyboard**: Click in search bar and start typing

## 📚 Next Steps

- Add your first secret
- Try the search/filter
- View statistics
- Package as standalone .app

## 🔗 Integration

The GUI integrates with:
- ✅ CLI tool (`enclave` command)
- ✅ MCP Server (Claude Desktop integration)
- 🚧 Web UI (coming soon)
- 🚧 Multi-tenant backend (coming soon)

All use the same vault at `~/.vault/`!

## 📖 Full Documentation

See [README.md](README.md) for complete documentation.

---

**Enjoy your encrypted vault! 🔐**
