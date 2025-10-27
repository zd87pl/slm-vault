# Enclave - Updated Branding & RunPod Connectivity

## What's New

### 1. Rebranded as "Enclave"
- App title changed from "Personal Vault" to "🔐 Enclave"
- Window title updated
- Reflects the secure, isolated nature of the encrypted vault

### 2. RunPod Connectivity Indicator

**New cloud status icon** in the app bar shows real-time RunPod inference pipeline connectivity:

#### Status Indicators

| Icon | Color | Status | Meaning |
|------|-------|--------|---------|
| ☁️✓ | Green | Connected | RunPod endpoint healthy |
| ☁️✗ | Red | Disconnected | Cannot reach RunPod |
| ☁️? | Gray | Not Configured | No RunPod credentials set |
| ☁️↻ | Amber | Checking | Currently testing connection |

#### How It Works

1. **Automatic Check**: On app startup, checks RunPod endpoint
2. **Manual Refresh**: Click the cloud icon to re-check
3. **Background Thread**: Non-blocking connectivity test
4. **5s Timeout**: Fast feedback without hanging UI

#### Configuration

Set environment variables:

```bash
export RUNPOD_ENDPOINT_ID="your-endpoint-id"
export RUNPOD_API_KEY="your-api-key"
```

Then launch the app:

```bash
./launch_gui.sh
```

The connectivity indicator will show:
- **Green** ✓ if RunPod is reachable
- **Gray** ? if not configured
- **Red** ✗ if configured but unreachable

#### API Endpoint Checked

```
GET https://api.runpod.io/v2/{ENDPOINT_ID}/health
Authorization: Bearer {API_KEY}
```

## Technical Details

### Implementation

- **Threading**: Connectivity check runs in background daemon thread
- **Non-blocking**: UI remains responsive during check
- **Requests**: Uses `requests` library (sync) instead of async
- **Flet Integration**: Updates UI via `page.update()`

### Files Changed

- `advanced_vault/gui/vault_app.py`:
  - Added RunPod connectivity check method
  - Added status update logic
  - Added cloud icon to app bar
  - Changed title to "Enclave"

### Dependencies

- `requests` - HTTP client for connectivity checks
- `threading` - Background connectivity tests

## Usage

### Launch App

```bash
# Without RunPod (will show "Not Configured")
python3 advanced_vault/gui/vault_app.py

# With RunPod credentials
export RUNPOD_ENDPOINT_ID="abc123"
export RUNPOD_API_KEY="xyz789"
python3 advanced_vault/gui/vault_app.py
```

### Check Connectivity Manually

Click the **cloud icon** in the app bar to trigger a fresh connectivity check.

### Tooltip Info

Hover over the cloud icon to see:
- Current status
- Last check time (future enhancement)
- Connection details

## Future Enhancements

- [ ] Show last check timestamp in tooltip
- [ ] Periodic auto-refresh (every 60s)
- [ ] Show latency/response time
- [ ] Multiple endpoint support
- [ ] Connection history log
- [ ] Notification on disconnect
- [ ] Retry logic with exponential backoff

## Screenshots

### Not Configured (Gray)
```
🔐 Enclave                                [☁️?] [+] [↻]
```

### Connected (Green)
```
🔐 Enclave                                [☁️✓] [+] [↻]
```

### Disconnected (Red)
```
🔐 Enclave                                [☁️✗] [+] [↻]
```

## Integration with WDVA Pipeline

The connectivity indicator monitors the **Layer 2 (DoRA) inference pipeline**:

1. **Encrypted Adapter Storage**: Local vault stores encrypted DoRA weights
2. **RunPod Serverless**: Inference endpoint for decryption + generation
3. **Connectivity Check**: Ensures pipeline is ready before queries
4. **Fallback**: If disconnected, app uses Layer 1 (KV) only

This gives users **real-time visibility** into their AI inference pipeline status.

---

**Enclave v2.0** - Secure. Intelligent. Connected.
