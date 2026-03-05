#!/bin/bash
# Build script for FlashTransfer

echo "🏗️ Building FlashTransfer..."

# Check for PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

# Detect OS
OS=$(uname -s)

cd "$(dirname "$0")"

if [ "$OS" = "Linux" ]; then
    echo "🐧 Building for Linux..."
    pyinstaller \
        --onefile \
        --name flashtransfer \
        --clean \
        flashtransfer.py
    
    echo "✅ Build complete! Executable: dist/flashtransfer"
    
elif [ "$OS" = "MINGW64_NT" ] || [ "$OS" = "CYGWIN" ] || [ "$OS" = "Windows_NT" ]; then
    echo "🪟 Building for Windows..."
    pyinstaller \
        --onefile \
        --windowed \
        --name FlashTransfer \
        --clean \
        flashtransfer.py
    
    echo "✅ Build complete! Executable: dist/FlashTransfer.exe"
else
    echo "Building for $OS..."
    pyinstaller --onefile --name flashtransfer flashtransfer.py
fi

echo ""
echo "To run: ./dist/flashtransfer (or FlashTransfer.exe on Windows)"
