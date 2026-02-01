#!/bin/bash
# Start script for cache proxy service
# This script activates the conda environment and starts the cache proxy

set -e  # Exit on error

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate sglang-embedding-cache

# Change to cache_proxy directory
cd "$PROJECT_DIR/cache_proxy"

# Start the cache proxy
echo "Starting cache proxy service..."
exec uvicorn main:app --host 0.0.0.0 --port 8081
