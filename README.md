# SCL Dot Test Server

A minimal Flask server for App Store reviewers to test the **SCL Dot** iOS app.

## Quick Start

### Option 1: One-Line Setup (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/your-org/scl-dot-test-server/main/setup.sh | bash
```

Or clone and run:

```bash
git clone https://github.com/your-org/scl-dot-test-server.git
cd SCL-dot-test-server
./setup.sh
```

### Option 2: Manual Setup

```bash
# Install dependencies
pip install flask flask-cors

# Start the server
python3 scl_dot_test_server.py
```

## Configuration

When the server starts, it will display your computer's local IP address:

```
Server running on port 5001
Local IP: 192.168.1.xxx
```

### In the SCL Dot iOS App:

1. Tap the **gear icon** (top-right) to open Settings
2. Set **Server IP** to the displayed IP (e.g., `192.168.1.xxx`)
3. Set **Server Port** to `5001`
4. Ensure **Use HTTPS** is **OFF** (grey/disabled)
5. Tap **Test Connection**
6. You should see "Connected" in green

## What This Server Does

This minimal server allows the iOS app to:

- **Test connection** - Verify the app can reach the server
- **Send heartbeats** - Confirm device connectivity
- **Receive track data** - Accept insect detection tracks (saved locally)
- **Receive crop images** - Accept and store captured insect frames
- **Receive background images** - Accept scheduled reference captures
- **Receive video clips** - Accept recorded video segments

Received data is stored in the `./received_data/` directory for verification.

## Troubleshooting

### "Cannot connect" errors

1. **Same WiFi**: Ensure iPhone and computer are on the same WiFi network
2. **Firewall**: Allow port 5001 through your firewall:
   - macOS: `sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which python3)`
   - Linux: `sudo ufw allow 5001`
   - Windows: Add Python to Windows Defender Firewall exceptions
3. **IP Address**: Verify you're using the correct local IP (not public IP)

### iOS can't reach server

On macOS, try:
```bash
# Find your local IP
ifconfig | grep "inet " | grep -v 127.0.0.1

# Test from another device on the same network
curl http://YOUR_IP:5001/api/health
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/heartbeat` | GET/POST | Connection test and heartbeat |
| `/api/track` | POST | Receive track telemetry data (JSON) |
| `/upload_crops` | POST | Upload crop images (multipart/form-data) |
| `/upload_background` | POST | Upload background reference image |
| `/upload_video` | POST | Upload video clip (MP4) |
| `/api/health` | GET | Health check |

## Data Storage

### Track Telemetry (JSON)
- **Location**: `./received_data/{DOT_DIRECTORY}/track_{TRACK_ID}.json`
- **Content**: JSON payload with track metadata and detections

### Crop Images (JPEG)
- **Location**: `./received_data/crops/{TRACK_ID}/frame_000000.jpg`
- **Content**: JPEG images from insect detections

### Background Images (JPEG)
- **Location**: `./received_data/backgrounds/bg_YYYYMMDD_HHMMSS.jpg`
- **Content**: Reference background images captured at scheduled times

### Video Clips (MP4)
- **Location**: `./received_data/videos/clip_YYYYMMDD_HHMMSS.mp4`
- **Content**: Recorded video clips (1-minute duration)

## License

MIT License - For App Store reviewer testing purposes only.
