#!/bin/bash
# Quick launch script for FlashTransfer

cd "$(dirname "$0")"

echo "🚀 Starting FlashTransfer..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python ./dev/null; then
    echo "❌ Python not found! Please install Python 3.8+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Install dependencies if needed
if ! $PYTHON -c "import PyQt6" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    $PYTHON -m pip install -r requirements.txt
fi

# Run
echo "✅ Starting FlashTransfer..."
$PYTHON flashtransfer.py
