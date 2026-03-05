# FlashTransfer

Fast cross-platform file transfer application between Linux and Windows with a modern GUI.

## Features

⚡ **Fast Transfer** - Optimized 8KB chunks for large files  
🖥️ **Modern GUI** - Dark theme with intuitive interface  
🔒 **Integrity Check** - MD5 hash verification for each transfer  
📊 **Progress Tracking** - Real-time speed and progress display  
📱 **Cross-Platform** - Works on Linux, Windows, and macOS  
📋 **Transfer History** - Keep track of all transfers  

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python flashtransfer.py
```

## Usage

### Sending a File
1. Click "Browse" to select a file
2. Enter the target IP address (shown on receiver's screen)
3. Click "Start Transfer"

### Receiving a File
1. Click "Start Listening"
2. Share your IP address with the sender
3. File will be saved to your Downloads folder

## Building Executable

### Windows (.exe)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico flashtransfer.py
```

### Linux (AppImage)
```bash
pip install pyinstaller
pyinstaller --onefile flashtransfer.py
```

## Default Settings

- **Port**: 55432
- **Chunk Size**: 8KB (optimal for large files)
- **Save Location**: ~/Downloads

## Network Requirements

- Both devices must be on the same network (or accessible via IP)
- Firewall must allow port 55432 (TCP)

## License

MIT License
