# RunPod-optimized Dockerfile for DoRA WDVA
# Place at repository root for easier RunPod portal builds
# Updated for RTX 5090 support - installs PyTorch from pip for latest GPU kernels

# Use CUDA base image (install PyTorch from pip for RTX 5090 kernel support)
FROM nvidia/cuda:12.4.1-cudnn9-runtime-ubuntu22.04

WORKDIR /workspace

# Install system dependencies and Python 3.10
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-dev \
    git \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create symlinks for python
RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.10 /usr/bin/python

# Upgrade pip
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch with RTX 5090 support (compute capability 8.9)
# Using pip ensures latest build with newest GPU kernels
RUN pip3 install --no-cache-dir \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cu124

# Copy requirements first for better layer caching
COPY docker/requirements.txt /workspace/requirements.txt

# Install remaining Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

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
