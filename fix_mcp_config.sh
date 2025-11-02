#!/bin/bash
# Fix MCP Config - Update to use Homebrew Python and better name

CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
PROJECT_ROOT="/Users/0x7d0/git/slm-vault"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi

echo "Fixing MCP config..."
echo "Old config:"
cat "$CONFIG_FILE"
echo ""

# Create backup
cp "$CONFIG_FILE" "$CONFIG_FILE.backup"

# Update config with Homebrew Python and "enclave" name
python3 << 'EOF'
import json
import os

config_path = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")

with open(config_path, 'r') as f:
    config = json.load(f)

# Update Python path to Homebrew
if "mcpServers" in config:
    for server_name in list(config["mcpServers"].keys()):
        server_config = config["mcpServers"][server_name]
        
        # Update to Homebrew Python
        if server_config.get("command", "").endswith("python3"):
            server_config["command"] = "/opt/homebrew/bin/python3"
        
        # Migrate "personal-vault" to "enclave"
        if server_name == "personal-vault":
            config["mcpServers"]["enclave"] = server_config
            del config["mcpServers"]["personal-vault"]
            print(f"Migrated 'personal-vault' to 'enclave'")
        
        # Ensure PYTHONPATH is set
        if "env" not in server_config:
            server_config["env"] = {}
        server_config["env"]["PYTHONPATH"] = "/Users/0x7d0/git/slm-vault"

# Write updated config
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print("Config updated successfully!")
print("\nNew config:")
print(json.dumps(config, indent=2))
EOF

echo ""
echo "✅ Config fixed!"
echo "Please restart Claude Desktop completely (quit and reopen)"
echo ""
echo "To verify, ask Claude: 'What tools do you have access to?'"

