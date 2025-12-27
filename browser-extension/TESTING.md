# Browser Extension Testing Guide

## Quick Start Testing

### 1. Load Extension in Chrome/Comet

1. **Open Chrome/Comet** and navigate to:
   - Chrome: `chrome://extensions/`
   - Comet: `comet://extensions/`

2. **Enable Developer Mode**:
   - Toggle "Developer mode" in top-right corner

3. **Load Unpacked Extension**:
   - Click "Load unpacked"
   - Select the `browser-extension/` directory
   - Extension should appear in the list

4. **Verify Installation**:
   - Extension icon should appear in toolbar
   - Click icon to open popup
   - Should see "Enclave Vault" popup

### 2. Initial Setup

1. **Open Settings**:
   - Click extension icon
   - Click "Settings" link in footer
   - Settings page opens in new tab

2. **Set Master Password**:
   - In Settings, go to "Master Password" section
   - Enter a new password (min 8 characters)
   - Confirm password
   - Click "Change Password"
   - Should see success message

3. **Configure Backend** (if needed):
   - In Settings, go to "Backend Configuration"
   - Update URL if different from default
   - Click "Test Connection"
   - Should see "Connection successful"

4. **Login** (optional, for syncing):
   - In Settings, go to "Authentication"
   - Enter email and password
   - Click "Login"
   - Should see "Authenticated" status

### 3. Test Secret Storage

1. **Add Secret**:
   - Click extension icon
   - Click "Add Secret" button
   - Enter:
     - Service: `openai`
     - Secret: `sk-test123...`
     - Tags: `api-key, production`
   - Click "Save"
   - Secret should appear in list

2. **View Secret**:
   - Secret should be visible in popup
   - Shows service name, tags, and date

3. **Copy Secret**:
   - Click copy button (📋) on secret
   - Secret should be copied to clipboard
   - Paste to verify

4. **Delete Secret**:
   - Click delete button (🗑) on secret
   - Confirm deletion
   - Secret should disappear

### 4. Test Consent Flow

1. **Trigger Consent Request**:
   - From MCP server or via test script
   - Consent dialog should appear
   - Shows agent identifier, service, and preview

2. **Test Consent Decisions**:
   - Click "Allow" - should grant access once
   - Click "Deny" - should deny access
   - Click "Allow Always" - should create policy
   - Click "Deny Always" - should create deny policy

3. **Verify Consent Persistence**:
   - Close and reopen extension
   - Consent decisions should persist
   - "Allow Always" should auto-grant on next request

### 5. Test Settings

1. **Master Password**:
   - Change password
   - Verify password strength indicator works
   - Test with weak/medium/strong passwords

2. **Backend Configuration**:
   - Change backend URL
   - Test connection
   - Verify URL persists after reload

3. **Authentication**:
   - Login
   - Verify token persists
   - Logout
   - Verify token cleared

4. **Data Management**:
   - Export data
   - Verify JSON file downloads
   - Clear data (careful!)
   - Verify all data removed

### 6. Test MCP Integration

1. **Start MCP Server**:
   ```bash
   python -m advanced_vault.mcp_server
   ```

2. **Request Secret via MCP**:
   - From Claude Desktop or Cursor
   - Ask: "What's my OpenAI API key?"
   - Consent dialog should appear in extension

3. **Verify Consent**:
   - Grant consent
   - Secret should be returned to MCP
   - Check activity log in extension

### 7. Test Activity Logging

1. **View Activity**:
   - Click extension icon
   - Click "Activity" link
   - Should see list of access attempts

2. **Verify Logging**:
   - Each secret access should be logged
   - Shows agent, service, decision, timestamp

## Common Issues & Solutions

### Extension Not Loading

**Issue**: Extension doesn't appear after loading

**Solutions**:
- Check for errors in `chrome://extensions/` → Developer mode → Errors
- Verify `manifest.json` is valid JSON
- Check all referenced files exist
- Ensure icons are in correct location

### Master Password Not Working

**Issue**: Can't set or verify master password

**Solutions**:
- Check browser console for errors
- Verify storage permissions in manifest
- Clear extension data and retry
- Check password meets minimum requirements (8 chars)

### Secrets Not Saving

**Issue**: Secrets disappear after adding

**Solutions**:
- Check IndexedDB in DevTools → Application → IndexedDB
- Verify storage permissions
- Check for errors in console
- Ensure master password is set

### Consent Dialog Not Appearing

**Issue**: Consent requests don't show dialog

**Solutions**:
- Verify consent.html is accessible
- Check web_accessible_resources in manifest
- Test consent manager directly
- Check for JavaScript errors

### Backend Connection Fails

**Issue**: Can't connect to backend

**Solutions**:
- Verify backend URL is correct
- Check CORS settings on backend
- Verify backend is running
- Check network tab for errors

## Testing Checklist

- [ ] Extension loads without errors
- [ ] Icons display correctly
- [ ] Popup opens and displays correctly
- [ ] Settings page opens and works
- [ ] Master password can be set
- [ ] Master password can be changed
- [ ] Secrets can be added
- [ ] Secrets can be viewed
- [ ] Secrets can be copied
- [ ] Secrets can be deleted
- [ ] Consent dialog appears
- [ ] Consent decisions work (Allow/Deny/Always)
- [ ] Activity log displays correctly
- [ ] Backend connection works
- [ ] Authentication works
- [ ] Data export works
- [ ] MCP integration works (if configured)

## Performance Testing

1. **Load Time**:
   - Extension should load popup in <500ms
   - Settings page should load in <1s

2. **Storage**:
   - Test with 100+ secrets
   - Verify performance doesn't degrade
   - Check memory usage

3. **Consent**:
   - Consent dialog should appear in <200ms
   - Multiple rapid requests should queue properly

## Browser Compatibility

Test on:
- [ ] Chrome (latest)
- [ ] Chrome (previous version)
- [ ] Comet (if available)
- [ ] Edge Chromium (if needed)
- [ ] Brave (if needed)

## Security Testing

- [ ] Secrets encrypted in storage
- [ ] Master password not logged
- [ ] No secrets in console logs
- [ ] Consent decisions properly enforced
- [ ] No XSS vulnerabilities
- [ ] CSP headers respected

## Next Steps After Testing

1. **Fix any bugs** found during testing
2. **Document issues** in GitHub issues
3. **Create screenshots** for Chrome Web Store
4. **Prepare store listing** description
5. **Submit for review**



