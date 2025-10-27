#!/bin/bash
# Launch Enclave GUI with authentication

# Set Supabase environment variables
export SUPABASE_URL="https://ibiapabkyskoazpgcymo.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImliamFwYWJreXNrb2F6cGdjeW1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzUzNzUxNjksImV4cCI6MjA1MDk1MTE2OX0.yKxLCsKU2EEq6m-Cad7W1k3OgGhZqaDKLTgSX8qUNt0"

# Set backend URL
export ENCLAVE_BACKEND_URL="https://keen-curiosity-production-1288.up.railway.app"

# RunPod configuration (optional)
# export RUNPOD_ENDPOINT_ID="your_endpoint_id"
# export RUNPOD_API_KEY="your_api_key"

cd "$(dirname "$0")/advanced_vault/gui"

echo "🔐 Launching Enclave GUI..."
echo "Backend: $ENCLAVE_BACKEND_URL"
echo ""

python3 vault_app.py
