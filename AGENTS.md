# Agent Notes: SCL Dot Test Server

## Project Purpose

Minimal Flask HTTP server that simulates the edge26 receiver for App Store
reviewers. The SCL Dot iOS app (found at
`/Users/asehatveit/Desktop/Developer/SCL-apps/dot`) connects to this server over
WiFi to demonstrate and test insect detection functionality during App Store
review.

## Quick Start

```bash
./setup.sh
```

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 scl_dot_test_server.py
```

The server listens on `0.0.0.0:5001`. Data is written to `./received_data/`.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/heartbeat` | `GET` / `POST` | Connection test / device heartbeat. Returns `{"status": "ok"}`. |
| `/api/track` | `POST` | Receives track telemetry JSON. Saves to `./received_data/{dot_directory}/track_{track_id}.json`. |
| `/upload_crops` | `POST` | Receives multipart JPEG crops. Saves to `./received_data/{dot_directory}/{dot_directory}_crops/{track_id}/frame_000000.jpg`. |
| `/upload_done` | `POST` | Completion marker sent after all crops for a track are uploaded. |
| `/upload_background` | `POST` | Receives a background reference JPEG. Saves to `./received_data/backgrounds/bg_YYYYMMDD_HHMMSS.jpg`. |
| `/upload_video` | `POST` | Receives an MP4 video clip. Saves to `./received_data/videos/{filename}`. |
| `/api/health` | `GET` | Health check returning server status, port, and data directory. |

## Expected HTTP Headers

All endpoints (except `/api/health`) expect these headers from the iOS app:

- `X-Device-ID` – Persistent device UUID
- `X-Device-Name` – `UIDevice.current.name`

Additionally:

- `/api/track`, `/upload_crops`, `/upload_done` also send:
  - `X-Track-ID` – Track identifier
  - `X-DOT-ID` – Short 8-char device session ID
  - `X-DOT-Directory` – Session directory name (`{dotId}_{yyyyMMdd_HHmmss}`)

- `/upload_video` also sends:
  - `X-Video-Timestamp` – Clip timestamp

## Data Directory Layout

```
received_data/
├── {dot_directory}/
│   ├── track_{track_id}.json
│   └── {dot_directory}_crops/
│       └── {track_id}/
│           ├── frame_000000.jpg
│           ├── frame_000060.jpg
│           └── ...
├── backgrounds/
│   └── bg_YYYYMMDD_HHMMSS.jpg
└── videos/
    └── {filename}.mp4
```

## iOS App ↔ Server Contract

- **Heartbeat**: App POSTs JSON with `deviceId`, `deviceName`, `appStatus`,
  `batteryLevel`, `batteryState`, `thermalState`, `timestamp` every 10 seconds.
- **Track Telemetry**: App POSTs `InsectTelemetryPayload` JSON when a track
  terminates or the crop buffer reaches 150 crops.
- **Crops**: App POSTs multipart `files[]` array of JPEGs with sequential
  filenames (`frame_000000.jpg`, `frame_000060.jpg`, etc.).
- **Done Marker**: App POSTs to `/upload_done` after all crops are uploaded.
  The server must return `200 OK` or the app logs an error (but currently does
  not retry).
- **Background**: App POSTs multipart `image` field at scheduled times
  (default 7:25 AM and 12:05 PM).
- **Video**: App POSTs multipart `video` field at scheduled times (default
  8:00 AM and 2:00 PM). Files can be large (1-minute 4K MP4).

## Important Notes

- The server does **not** perform automated tests; it is a passive receiver.
- The iPhone and the computer running this server must be on the **same WiFi
  network**.
- The app disables HTTPS for this test server; ensure the reviewer knows to
  turn **Use HTTPS OFF** in the app settings.
- No external configuration files exist; `PORT` and `DATA_DIR` are set in
  `scl_dot_test_server.py`.
- The `./received_data/` directory is committed with sample data; new uploads
  from reviewers will be mixed with existing sample data unless the directory
  is cleaned before a review session.

## Dependencies

- `flask>=2.0.0`
- `flask-cors>=3.0.0`

Both are installed by `setup.sh` or `requirements.txt`.
