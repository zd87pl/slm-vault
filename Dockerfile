# RunPod-optimized Dockerfile for DoRA WDVA
# Place at repository root for easier RunPod portal builds

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY docker/requirements.txt /workspace/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /workspace/src/
COPY config/ /workspace/config/
COPY examples/ /workspace/examples/

# Environment variables for optimization
ENV TOKENIZERS_PARALLELISM=false
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
ENV TRANSFORMERS_CACHE=/workspace/.cache/huggingface
ENV HF_HOME=/workspace/.cache/huggingface

# Create necessary directories
RUN mkdir -p /workspace/outputs /workspace/.cache

# Health check for RunPod
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import runpod; import torch; print('OK')" || exit 1

# For RunPod deployment, start handler
CMD ["python3", "-u", "src/rp_handler.py"]
