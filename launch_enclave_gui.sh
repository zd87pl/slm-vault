#!/bin/bash

echo "🔐 Launching Enclave GUI..."
echo "Backend: https://keen-curiosity-production-1288.up.railway.app"
echo ""

# Check if flet is installed
if ! python3 -c "import flet" 2>/dev/null; then
    echo "Installing flet..."
    pip install flet
fi

# Launch the GUI
python3 /workspace/enclave_gui.py
