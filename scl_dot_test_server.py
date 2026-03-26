#!/usr/bin/env python3
"""
SCL Dot Test Server - Minimal Flask server for App Store reviewer testing.

This server simulates the edge26 receiver for testing the iOS app during 
App Store review. It accepts connections from the iOS app and logs/track
received data for demonstration purposes.

Usage:
    python3 scl_dot_test_server.py
    
The server will start on port 5001 and accept connections from any device
on the local network.
"""

from flask import Flask, request, jsonify
from pathlib import Path
from datetime import datetime
import logging
import os
import json

# Enable CORS for local network testing
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
PORT = 5001
DATA_DIR = Path("./received_data")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create data directory
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_local_ip():
    """Get the local IP address for display."""
    import socket
    try:
        # Try to get the IP that would be used to connect to the internet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route('/api/heartbeat', methods=['GET', 'POST'])
def heartbeat():
    """
    Handle heartbeat from iOS app.
    
    GET: Simple connection test from Settings UI
    POST: Regular heartbeat with device status
    
    Returns:
        200 OK with status
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown')
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        logger.info(f"[HEARTBEAT] POST from {device_name} ({device_id[:8]}...)")
        logger.debug(f"  Battery: {data.get('batteryLevel', 'N/A')}, "
                    f"State: {data.get('batteryState', 'N/A')}, "
                    f"App: {data.get('appStatus', 'N/A')}")
    else:
        logger.info(f"[HEARTBEAT] GET from {device_name} ({device_id[:8]}...)")
    
    return jsonify({
        "status": "ok",
        "server": "scl_dot_test_server",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/track', methods=['POST'])
def receive_track():
    """
    Receive track telemetry data from iOS app.
    
    Headers:
        X-Device-ID: Device UUID
        X-Device-Name: Device name
        X-Track-ID: Track UUID
        X-DOT-ID: DOT session ID
        X-DOT-Directory: DOT directory name
    
    Body:
        JSON payload with track metadata and detections
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    track_id = request.headers.get('X-Track-ID', 'unknown')
    dot_id = request.headers.get('X-DOT-ID', 'unknown')
    dot_directory = request.headers.get('X-DOT-Directory', 'unknown')
    
    # Get JSON data
    data = request.get_json(silent=True) or {}
    
    # Create directory for this DOT session
    session_dir = DATA_DIR / dot_directory
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save track data as JSON
    track_file = session_dir / f"track_{track_id}.json"
    with open(track_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"[TRACK] Received from {device_name} ({device_id[:8]}...)")
    logger.info(f"  Track: {track_id}")
    logger.info(f"  DOT: {dot_directory}")
    logger.info(f"  Detections: {len(data.get('detections', []))}")
    logger.info(f"  Saved to: {track_file}")
    
    return jsonify({
        "status": "success",
        "track_id": track_id,
        "received": True
    }), 200


@app.route('/api/health', methods=['GET'])
def health():
    """
    Health check endpoint.
    
    Returns:
        200 OK with service status
    """
    return jsonify({
        "status": "ok",
        "service": "scl_dot_test_server",
        "port": PORT,
        "data_dir": str(DATA_DIR),
        "timestamp": datetime.now().isoformat()
    }), 200


if __name__ == '__main__':
    local_ip = get_local_ip()
    
    print("=" * 70)
    print("  SCL Dot Test Server")
    print("  App Store Review Testing Server")
    print("=" * 70)
    print()
    print(f"  HTTP Port:     {PORT}")
    print(f"  Local IP:      {local_ip}")
    print(f"  Data Storage:  {DATA_DIR.absolute()}")
    print()
    print("  Endpoints:")
    print(f"    GET/POST /api/heartbeat  - Connection test / heartbeat")
    print(f"    POST     /api/track      - Receive track telemetry")
    print(f"    GET      /api/health     - Health check")
    print()
    print("=" * 70)
    print()
    print(f"  To test from iOS app:")
    print(f"    1. Open Settings (gear icon)")
    print(f"    2. Set Server IP to: {local_ip}")
    print(f"    3. Set Server Port to: {PORT}")
    print(f"    4. Tap 'Test Connection'")
    print()
    print("=" * 70)
    print()
    
    # Run Flask server
    app.run(host='0.0.0.0', port=PORT, threaded=True)
