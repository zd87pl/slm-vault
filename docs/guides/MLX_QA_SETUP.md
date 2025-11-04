# MLX Q&A Generation Setup Guide

## Quick Start

MLX Q&A generation uses Qwen2.5-3B-Instruct-4bit model for guaranteed JSON output and 3 Q&A pairs per chunk.

### Automatic Setup

1. Open Settings → Component Status
2. Find "Q&A Generation" 
3. Click the download button (⬇️) if status shows "Setup required"
4. Wait for download (~1.7GB, 10-30 minutes first time)

### Faster Downloads (Optional)

**Using HuggingFace Token (Recommended):**

HuggingFace API token is **NOT required** but helps with:
- Faster downloads (no rate limiting)
- Higher download speed
- More reliable connections

**Setup:**

1. Get free token: https://huggingface.co/settings/tokens
2. Set environment variable:
   ```bash
   export HF_TOKEN=your_token_here
   ```
3. Restart app or run:
   ```bash
   HF_TOKEN=your_token_here ./launch_enclave_gui.sh
   ```

**Alternative: Using HF Transfer (Faster Protocol)**

Install `hf_transfer` for faster downloads:
```bash
pip install hf_transfer
```

The app will automatically use it if available.

### Troubleshooting

**Slow Download Speed:**
- Default speed: ~100-200 kB/s (can take 2-3 hours)
- With HF token: Often 1-5 MB/s (10-30 minutes)
- Check internet connection
- Try setting `HF_TOKEN` environment variable

**Download Cancelled/Interrupted:**
- Can retry - will resume from cache
- Partial downloads are saved in `~/.cache/huggingface/hub/`
- No need to restart from beginning

**Out of Memory:**
- Model requires ~3GB RAM (4-bit quantization)
- Close other applications
- Requires 16GB+ total RAM for smooth operation

**Download Stuck:**
- Check terminal for actual progress (GUI shows heartbeat updates)
- Terminal shows real progress bars from huggingface_hub
- If stuck >30 minutes, cancel and retry

### Manual Installation

If automatic setup fails:

```bash
# Install dependencies
pip install mlx-lm outlines langchain-text-splitters pydantic huggingface_hub

# Download model manually
python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-3B-Instruct-4bit')"
```

### Fallback Options

If MLX setup fails, the app automatically uses:
1. **Ollama TinyLlama** (local, already downloaded)
2. **RunPod** (cloud, requires backend config)

MLX is preferred but not required - app works with Ollama fallback.

