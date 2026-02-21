#!/usr/bin/env bash
# Force CPU-only PyTorch so Render free tier (512 MB) doesn't OOM.
# Run as: cd backend && bash render-build.sh
set -e
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
