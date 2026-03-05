@echo off
REM Build script for FlashTransfer on Windows

echo Building FlashTransfer for Windows...

REM Check for PyInstaller
pyinstaller --version > nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building executable...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name FlashTransfer ^
    --clean ^
    flashtransfer.py

if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo Build complete!
echo Executable: dist\FlashTransfer.exe
pause
