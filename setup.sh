#!/bin/bash
#
# SCL Dot Test Server - Quick Setup Script
# One-line setup for App Store reviewers
#

set -e

echo "=========================================="
echo "  SCL Dot Test Server Setup"
echo "=========================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3 from https://python.org"
    exit 1
fi

echo "Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q flask flask-cors

echo ""
echo "=========================================="
echo "  Dependencies installed successfully!"
echo "=========================================="
echo ""

# Start the server
echo "Starting SCL Dot Test Server..."
echo ""
python3 scl_dot_test_server.py
