#!/bin/bash
#
# Generate Service JWT Token
#
# Usage: ./generate_jwt.sh
#
# Reads config from backend/.env:
#   CLIENT_ID, CLIENT_NAME, SERVICE_JWT_SECRET, SERVICE_JWT_EXPIRY_HOURS
#

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# Change to backend directory
cd "$BACKEND_DIR" || { echo "Error: Cannot cd to $BACKEND_DIR"; exit 1; }

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Warning: No virtual environment found. Using system Python."
fi

# Run the Python script
python scripts/generate_service_jwt.py
