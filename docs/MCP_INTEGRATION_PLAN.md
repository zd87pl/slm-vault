# MCP Server Integration Plan

## Current State

### ✅ Multitenancy Status: FULLY ENABLED
- **Database Level**: RLS policies on all tables
- **API Level**: All endpoints require `user_id` and validate ownership
- **Storage Level**: User-specific paths (`/workspace/adapters/{user_id}/`)
- **Backend**: Middleware extracts `user_id` from JWT tokens

### ✅ MCP Server Status: IMPLEMENTED BUT MANUAL SETUP
- **Server**: Fully functional (`advanced_vault/mcp_server/server.py`)
- **Tools**: vault_store, vault_recall, vault_list_entries, vault_delete, vault_stats
- **Consent**: ConsentManager with OS notifications
- **Setup**: Manual - requires editing Claude Desktop config file

---

## Proposed Improvements

### 1. GUI Integration for MCP Setup
**Add to Settings page:**
- **MCP Server Section** with:
  - Status indicator (Connected/Not Connected)
  - Auto-detect Claude Desktop installation
  - One-click config generation
  - Copy-to-clipboard config
  - Test connection button
  - Instructions for manual setup

### 2. Auto-Configuration Generator
- Detect Claude Desktop config location
- Generate config JSON automatically
- Merge with existing config (if present)
- Validate Python path
- Detect vault path automatically

### 3. Connection Testing
- Test MCP server startup
- Verify tools are accessible
- Show connection status in GUI
- Display available tools

### 4. ChatGPT Integration Guide
- Note: MCP is primarily for Claude Desktop
- Add instructions for ChatGPT integration (if possible)
- Document alternative integration methods

---

## Implementation Plan

### Phase 1: MCP Setup UI (High Priority)
1. Add MCP section to Settings page
2. Create config generator utility
3. Add test connection functionality
4. Implement auto-detection

### Phase 2: Enhanced Integration (Medium Priority)
1. Live connection status
2. MCP server management
3. Permission management UI
4. Connection logs

### Phase 3: Testing Tools (Low Priority)
1. MCP tool tester
2. Connection diagnostics
3. Performance monitoring

---

## Files to Create/Modify

### New Files
- `advanced_vault/gui/mcp_setup.py` - MCP setup utilities
- `advanced_vault/gui/mcp_status.py` - MCP status checker

### Modified Files
- `advanced_vault/gui/vault_app.py` - Add MCP section to Settings
- `advanced_vault/mcp_server/README.md` - Update with GUI setup instructions

