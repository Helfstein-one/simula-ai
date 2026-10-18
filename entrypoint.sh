#!/bin/bash
set -e

# Simula-AI Container Entrypoint
# Supports "ui" (Streamlit) or "cli" execution modes

if [ "$1" = "ui" ] || [ "$1" = "streamlit" ]; then
    echo "Starting Simula-AI Streamlit Web UI on port 8501..."
    exec streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
elif [ "$1" = "cli" ]; then
    shift
    exec python -m cli.main "$@"
elif [ "$#" -eq 0 ]; then
    # Default to UI when no arguments provided
    echo "No command provided. Defaulting to Streamlit Web UI..."
    exec streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
else
    # Forward all custom arguments to CLI
    exec python -m cli.main "$@"
fi
