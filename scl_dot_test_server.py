#!/usr/bin/env python3
"""
SCL Dot Test Server - Minimal Flask server for App Store reviewer testing.

This server simulates the edge26 receiver for testing the iOS app during 
App Store review. It accepts connections from the iOS app and saves
received data in edge26-compatible format.

Directory structure:
    received_data/
    └── {dot_id}_{YYYYMMDD}/
        ├── crops/{track_id}_{HHMMSS}/
        │   ├── frame_NNNNNN.jpg
        │   └── done.txt
        ├── labels/{track_id}.json
        ├── {HHMMSS}_background.jpg
        ├── current_background.jpg
        └── videos/{filename}.mp4

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
import re
import shutil

# Enable CORS for local network testing
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
PORT = 5001
DATA_DIR = Path(__file__).parent / "received_data"

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
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_dot_id(device_id, dot_id_header=None):
    """Get DOT ID from header or device UUID prefix."""
    if dot_id_header:
        return dot_id_header
    return device_id[:8] if len(device_id) >= 8 else device_id


def parse_track_id(track_id_with_time):
    """Parse track ID with embedded time format: {track_id}_{HHMMSS}
    
    Returns:
        tuple: (track_id, time_str) or (None, None)
    """
    if not track_id_with_time:
        return None, None
    match = re.match(r'^([a-zA-Z0-9]+)_(\d{6})$', track_id_with_time)
    if match:
        return match.group(1), match.group(2)
    return None, None


def find_track_folder(crops_dir_path, track_id):
    """Find existing crop folder for a track_id (ignoring timestamp suffix)."""
    if not crops_dir_path or not crops_dir_path.exists():
        return None
    prefix = f"{track_id}_"
    for entry in crops_dir_path.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            return entry.name
    return None


def extract_frame_number(filename):
    """Extract frame number from filename like 'frame_000000.jpg' -> 0"""
    match = re.match(r'frame_(\d+)\.jpg', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def convert_labels_to_frames_format(labels_data):
    """Convert iOS DOT label format to frames/bbox format.
    
    Input:  {"points": [{"frameIndex": 755, "x": 1110, ...}]}
    Output: {"frames": [{"frame_number": 0, "bbox": [1110, ...]}]}
    
    Frame numbers are sequential (0-based) to match crop filenames.
    Bboxes are auto-scaled to 4K from 1080p if needed.
    """
    if "points" not in labels_data:
        return labels_data
    
    resolution = labels_data.get("resolution", {})
    res_width = resolution.get("width", 3840) if isinstance(resolution, dict) else 3840
    scale = 2.0 if res_width <= 2400 else 1.0
    
    frames = []
    for seq_idx, point in enumerate(labels_data.get("points", [])):
        if point.get("frameIndex") is not None:
            frames.append({
                "frame_number": seq_idx,
                "bbox": [
                    point.get("x", 0) * scale,
                    point.get("y", 0) * scale,
                    point.get("width", 0) * scale,
                    point.get("height", 0) * scale
                ]
            })
    
    return {"frames": frames}


@app.route('/api/heartbeat', methods=['GET', 'POST'])
def heartbeat():
    """
    Handle heartbeat from iOS app.
    
    GET: Simple connection test from Settings UI (also accepts query params)
    POST: Regular heartbeat with device status
    
    Returns:
        200 OK with status
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown')
    
    if request.method == 'GET':
        device_id = request.args.get('device_id', device_id)
        device_name = request.args.get('device_name', device_name)
        logger.info(f"[HEARTBEAT] GET from {device_name} ({device_id[:8]}...)")
    else:
        data = request.get_json(silent=True) or {}
        logger.info(f"[HEARTBEAT] POST from {device_name} ({device_id[:8]}...)")
        logger.debug(f"  Battery: {data.get('batteryLevel', 'N/A')}, "
                    f"State: {data.get('batteryState', 'N/A')}, "
                    f"App: {data.get('appStatus', 'N/A')}")
    
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
        X-Track-ID: Track ID in {hex}_{HHMMSS} format
        X-DOT-ID: Short 8-char DOT session ID
        X-DOT-Directory: DOT directory name (ignored)
    
    Body:
        InsectTelemetryPayload JSON with points array
    
    Saves to:
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/labels/{track_id}.json
        (accumulates frames across batches, renumbers sequentially)
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    track_id_with_time = request.headers.get('X-Track-ID', '')
    dot_id = request.headers.get('X-DOT-ID')
    
    assigned_dot_id = get_dot_id(device_id, dot_id)
    today = datetime.now().strftime('%Y%m%d')
    dot_directory = f"{assigned_dot_id}_{today}"
    
    track_data = request.get_json(silent=True) or {}
    if not track_data:
        logger.error("No JSON data received")
        return jsonify({"error": "No JSON data received"}), 400
    
    track_id, _ = parse_track_id(track_id_with_time)
    if not track_id:
        track_id = str(track_data.get('trackId', track_id_with_time))
    
    if not track_id:
        logger.error("Missing track_id in header or data")
        return jsonify({"error": "Missing track_id"}), 400
    
    # Clean inputs
    dot_directory = Path(dot_directory).name
    track_id = Path(track_id).name
    
    # Convert to frames format
    converted = convert_labels_to_frames_format(track_data)
    
    logger.info(f"[TRACK] Received from {device_name} ({device_id[:8]}...)")
    logger.info(f"  Track: {track_id}, DOT: {dot_directory}")
    logger.info(f"  Frames: {len(converted.get('frames', []))}")
    
    try:
        dot_dir_path = DATA_DIR / dot_directory
        labels_dir_path = dot_dir_path / "labels"
        labels_dir_path.mkdir(parents=True, exist_ok=True)
        
        labels_path = labels_dir_path / f"{track_id}.json"
        
        # Accumulate labels across batches
        existing_frames = []
        if labels_path.exists():
            with open(labels_path, 'r') as f:
                existing_data = json.load(f)
            existing_frames = existing_data.get("frames", [])
        
        new_frames = converted.get("frames", [])
        merged_frames = existing_frames + new_frames
        for i, frame in enumerate(merged_frames):
            frame["frame_number"] = i
        
        merged_data = {"frames": merged_frames}
        
        with open(labels_path, 'w') as f:
            json.dump(merged_data, f, indent=2)
        
        logger.info(f"  Saved to: {labels_path} (total frames: {len(merged_frames)})")
        
        return jsonify({
            "status": "success",
            "dot_directory": dot_directory,
            "track_id": track_id,
            "frames": len(merged_frames)
        }), 200
        
    except Exception as e:
        logger.error(f"Error saving track: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/upload_crops', methods=['POST'])
def upload_crops():
    """
    Receive crop images from iOS app (multipart/form-data).
    
    Headers:
        X-Device-ID: Device UUID
        X-Device-Name: Device name
        X-Track-ID: Track ID in {hex}_{HHMMSS} format
    
    Form Data:
        files: JPEG files with filenames like "frame_000000.jpg"
    
    Saves to:
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/crops/{track_id}_{HHMMSS}/
        (merges multiple batches for the same track with frame offset)
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    track_id_with_time = request.headers.get('X-Track-ID', '')
    
    assigned_dot_id = get_dot_id(device_id)
    today = datetime.now().strftime('%Y%m%d')
    dot_directory = f"{assigned_dot_id}_{today}"
    
    if not track_id_with_time:
        logger.error("Missing X-Track-ID header")
        return jsonify({"error": "Missing X-Track-ID header"}), 400
    
    track_id, time_str = parse_track_id(track_id_with_time)
    if not track_id:
        logger.error(f"Invalid X-Track-ID format: {track_id_with_time}")
        return jsonify({"error": "Invalid X-Track-ID format. Expected: {track_id}_{HHMMSS}"}), 400
    
    if not time_str:
        time_str = datetime.now().strftime('%H%M%S')
    
    # Clean inputs
    dot_directory = Path(dot_directory).name
    track_id = Path(track_id).name
    
    logger.info(f"[CROPS] Upload from {device_name} ({device_id[:8]}...)")
    logger.info(f"  DOT: {dot_directory}, Track: {track_id}")
    
    try:
        dot_dir_path = DATA_DIR / dot_directory
        crops_dir_path = dot_dir_path / "crops"
        
        # Find existing folder for batch merging
        existing = find_track_folder(crops_dir_path, track_id)
        if existing:
            track_folder = existing
            track_dir_path = crops_dir_path / track_folder
            logger.info(f"  Merging into existing folder: {track_folder}")
        else:
            track_folder = f"{track_id}_{time_str}"
            track_dir_path = crops_dir_path / track_folder
            track_dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"  Creating new folder: {track_folder}")
        
        files = request.files.getlist('files')
        if not files:
            logger.warning("No files received in upload")
            return jsonify({"error": "No files uploaded"}), 400
        
        frame_offset = len([f for f in track_dir_path.iterdir()
                           if f.is_file() and f.name.startswith("frame_")])
        
        saved_count = 0
        for file in files:
            if not file.filename:
                continue
            
            filename = Path(file.filename).name
            frame_num = extract_frame_number(filename)
            
            if frame_num is None:
                logger.warning(f"  Skipping invalid filename: {filename}")
                continue
            
            target_filename = f"frame_{frame_offset + frame_num:06d}.jpg"
            file.save(track_dir_path / target_filename)
            saved_count += 1
        
        total_frames = len([f for f in track_dir_path.iterdir()
                           if f.is_file() and f.name.startswith("frame_")])
        logger.info(f"  Saved {saved_count} frames (total: {total_frames})")
        
        return jsonify({
            "status": "success",
            "dot_directory": dot_directory,
            "track_folder": track_folder,
            "frames_saved": saved_count
        }), 200
        
    except Exception as e:
        logger.error(f"Error saving crops: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/upload_done', methods=['POST'])
def upload_done():
    """
    Receive track completion marker from iOS app.
    Creates done.txt in the crop directory.
    
    Headers:
        X-Device-ID: Device UUID
        X-Device-Name: Device name
        X-Track-ID: Track ID in {hex}_{HHMMSS} format
    
    Creates:
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/crops/{track_id}_{HHMMSS}/done.txt
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    track_id_with_time = request.headers.get('X-Track-ID', '')
    
    assigned_dot_id = get_dot_id(device_id)
    today = datetime.now().strftime('%Y%m%d')
    dot_directory = f"{assigned_dot_id}_{today}"
    
    if not track_id_with_time:
        logger.error("Missing X-Track-ID header")
        return jsonify({"error": "Missing X-Track-ID header"}), 400
    
    track_id, _ = parse_track_id(track_id_with_time)
    if not track_id:
        logger.error(f"Invalid X-Track-ID format: {track_id_with_time}")
        return jsonify({"error": "Invalid X-Track-ID format"}), 400
    
    dot_directory = Path(dot_directory).name
    track_id = Path(track_id).name
    
    logger.info(f"[DONE] Marker from {device_name} ({device_id[:8]}...)")
    logger.info(f"  Track: {track_id}")
    
    try:
        dot_dir_path = DATA_DIR / dot_directory
        crops_dir_path = dot_dir_path / "crops"
        
        existing = find_track_folder(crops_dir_path, track_id)
        if not existing:
            logger.error(f"No crop folder found for track {track_id}")
            return jsonify({"error": "Track directory not found"}), 400
        
        track_dir_path = crops_dir_path / existing
        done_file = track_dir_path / "done.txt"
        
        if done_file.exists():
            logger.info(f"  done.txt already exists for {existing}")
            return jsonify({
                "status": "success",
                "track_folder": existing,
                "note": "already existed"
            }), 200
        
        done_file.write_text(f"Track completed at {datetime.now().isoformat()}\n")
        logger.info(f"  Created done.txt for {existing}")
        
        return jsonify({
            "status": "success",
            "track_folder": existing
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating done marker: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/upload_background', methods=['POST'])
def upload_background():
    """
    Receive background reference image from iOS app.
    
    Headers:
        X-Device-ID: Device UUID
        X-Device-Name: Device name
    
    Form Data:
        image: JPEG image file
    
    Saves to:
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/{HHMMSS}_background.jpg
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/current_background.jpg (latest copy)
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    
    assigned_dot_id = get_dot_id(device_id)
    today = datetime.now().strftime('%Y%m%d')
    dot_directory = f"{assigned_dot_id}_{today}"
    
    file = request.files.get('image')
    if not file:
        logger.warning("No image file in background upload")
        return jsonify({"error": "No file uploaded"}), 400
    
    dot_directory = Path(dot_directory).name
    timestamp = datetime.now().strftime('%H%M%S')
    filename = f"{timestamp}_background.jpg"
    
    logger.info(f"[BG] Upload from {device_name} ({device_id[:8]}...)")
    
    try:
        dot_dir_path = DATA_DIR / dot_directory
        dot_dir_path.mkdir(parents=True, exist_ok=True)
        
        image_path = dot_dir_path / filename
        file.save(image_path)
        
        current_path = dot_dir_path / "current_background.jpg"
        shutil.copy2(image_path, current_path)
        
        file_size = image_path.stat().st_size
        logger.info(f"  Saved: {filename} ({file_size / 1024 / 1024:.1f} MB)")
        
        return jsonify({
            "status": "success",
            "dot_directory": dot_directory,
            "filename": filename,
            "size_bytes": file_size
        }), 200
        
    except Exception as e:
        logger.error(f"Error saving background: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/upload_video', methods=['POST'])
def upload_video():
    """
    Receive video clip from iOS app.
    
    Headers:
        X-Device-ID: Device UUID
        X-Device-Name: Device name
        X-Video-Timestamp: Optional clip timestamp
    
    Form Data:
        video: MP4 video file
    
    Saves to:
        {DATA_DIR}/{dot_id}_{YYYYMMDD}/videos/{filename}.mp4
    
    Returns:
        200 OK on success
    """
    device_id = request.headers.get('X-Device-ID', 'unknown')
    device_name = request.headers.get('X-Device-Name', 'Unknown Device')
    
    assigned_dot_id = get_dot_id(device_id)
    today = datetime.now().strftime('%Y%m%d')
    dot_directory = f"{assigned_dot_id}_{today}"
    
    file = request.files.get('video')
    if not file:
        logger.warning("No video file in upload")
        return jsonify({"error": "No file uploaded"}), 400
    
    dot_directory = Path(dot_directory).name
    filename = Path(file.filename).name
    
    if not filename.lower().endswith('.mp4'):
        logger.error(f"Invalid file format: {filename}")
        return jsonify({"error": "Invalid file format. Expected: .mp4"}), 400
    
    logger.info(f"[VIDEO] Upload from {device_name} ({device_id[:8]}...)")
    
    try:
        dot_dir_path = DATA_DIR / dot_directory
        videos_dir_path = dot_dir_path / "videos"
        videos_dir_path.mkdir(parents=True, exist_ok=True)
        
        video_path = videos_dir_path / filename
        file.save(video_path)
        
        file_size = video_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"  Saved: {filename} ({file_size_mb:.1f} MB)")
        
        return jsonify({
            "status": "success",
            "dot_directory": dot_directory,
            "filename": filename,
            "size_bytes": file_size,
            "size_mb": round(file_size_mb, 2)
        }), 200
        
    except Exception as e:
        logger.error(f"Error saving video: {e}")
        return jsonify({"error": str(e)}), 500


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
    print("  App Store Review Testing Server (edge26-compatible)")
    print("=" * 70)
    print()
    print(f"  HTTP Port:     {PORT}")
    print(f"  Local IP:      {local_ip}")
    print(f"  Data Storage:  {DATA_DIR.absolute()}")
    print()
    print("  Directory Structure:")
    print("    {dot_id}_{YYYYMMDD}/")
    print("      crops/{track_id}_{HHMMSS}/")
    print("        frame_NNNNNN.jpg")
    print("        done.txt")
    print("      labels/{track_id}.json")
    print("      {HHMMSS}_background.jpg")
    print("      current_background.jpg")
    print("      videos/{filename}.mp4")
    print()
    print("  Endpoints:")
    print(f"    GET/POST /api/heartbeat   - Connection test / heartbeat")
    print(f"    POST     /api/track       - Receive track telemetry (labels)")
    print(f"    POST     /upload_crops    - Upload crop images")
    print(f"    POST     /upload_done     - Create track completion marker")
    print(f"    POST     /upload_background - Upload background image")
    print(f"    POST     /upload_video    - Upload video clip")
    print(f"    GET      /api/health      - Health check")
    print()
    print("  Track ID Format: {hex_id}_{HHMMSS} (e.g., '00000048_132539')")
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
    
    app.run(host='0.0.0.0', port=PORT, threaded=True)
