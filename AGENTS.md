# Agent Notes: SCL Dot Test Server

## Project Purpose

Minimal Flask HTTP server that simulates the edge26 receiver for App Store
reviewers. The SCL Dot iOS app (found at
`/Users/asehatveit/Desktop/Developer/SCL-apps/dot`) connects to this server over
WiFi to demonstrate and test insect detection functionality during App Store
review.

The reference production receiver is at
`/Users/asehatveit/Desktop/Developer/SCL-apps/edge26_receiver.py`. This test
server shares the same helper functions (`parse_track_id`, `find_track_folder`,
`convert_labels_to_frames_format`) and directory structure, but omits
Pi-specific features like `PendingTrackTracker`, `load_bugcam_config()`, and
mount safety checks.

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
| `/api/track` | `POST` | Receives track telemetry JSON, converts to frames/bbox format, accumulates across batches. Saves to `./received_data/{dot_dir}/labels/{track_id}.json`. |
| `/upload_crops` | `POST` | Receives multipart JPEG crops. Merges batches for same track with frame offset. Saves to `./received_data/{dot_dir}/crops/{track_id}_{HHMMSS}/`. |
| `/upload_done` | `POST` | Completion marker. Creates `done.txt` in the track's crop folder. |
| `/upload_background` | `POST` | Receives a background reference JPEG. Saves timestamped copy + `current_background.jpg` to `./received_data/{dot_dir}/`. |
| `/upload_video` | `POST` | Receives an MP4 video clip. Saves to `./received_data/{dot_dir}/videos/{filename}`. |
| `/api/health` | `GET` | Health check returning server status, port, and data directory. |

## Expected HTTP Headers

All endpoints (except `/api/health`) expect these headers from the iOS app:

- `X-Device-ID` – Persistent device UUID
- `X-Device-Name` – `UIDevice.current.name`

Additionally:

| Endpoint | X-Track-ID | X-DOT-ID | X-DOT-Directory | X-Video-Timestamp |
|----------|:----------:|:--------:|:---------------:|:-----------------:|
| `/api/heartbeat` | — | — | — | — |
| `/api/track` | `{hex_id}_{HHMMSS}` | Short 8-char DOT ID | Ignored | — |
| `/upload_crops` | `{hex_id}_{HHMMSS}` | — | Ignored | — |
| `/upload_done` | `{hex_id}_{HHMMSS}` | — | — | — |
| `/upload_background` | — | — | — | — |
| `/upload_video` | — | — | — | Optional clip timestamp |

## Track ID Format

The X-Track-ID header uses the format `{hex_id}_{HHMMSS}` (e.g.,
`00000048_132539`). The hex portion is a zero-padded 8-char lowercase hex track
identifier from the C++ processing pipeline. The time portion is `HHmmss`
captured when the first crop for that track enters the buffer. The same
`trackIdString` is used across all three endpoints (`/api/track`,
`/upload_crops`, `/upload_done`) for a given track, including across batch
uploads.

## Data Directory Layout

```
received_data/
└── {dot_id}_{YYYYMMDD}/              (date-only, no time)
    ├── crops/{track_id}_{HHMMSS}/
    │   ├── frame_000000.jpg
    │   ├── frame_000060.jpg
    │   ├── ...
    │   └── done.txt                   (created by /upload_done)
    ├── labels/{track_id}.json
    ├── {HHMMSS}_background.jpg
    ├── current_background.jpg         (always latest background)
    └── videos/
        └── {dotId}_{yyyyMMdd_HHmmss}.mp4
```

The dot_id is derived from the `X-DOT-ID` header (on `/api/track`) or the first
8 characters of `X-Device-ID` (all other endpoints).

## iOS App ↔ Server Contract

- **Heartbeat**: App POSTs JSON with `deviceId`, `deviceName`, `appStatus`,
  `batteryLevel`, `batteryState`, `thermalState`, `timestamp` every 10 seconds.
  GET is used from Settings UI for connection tests.
- **Track Telemetry**: App POSTs `InsectTelemetryPayload` JSON to `/api/track`
  when a track terminates or the crop buffer reaches 150 crops. The server
  converts `points` to `frames`/`bbox` format and saves to `labels/{track_id}.json`.
- **Crops**: App POSTs multipart `files[]` array of JPEGs with sequential
  filenames (`frame_000000.jpg`, `frame_000060.jpg`, etc.) to `/upload_crops`.
  Multiple batches for the same track are merged into one folder with frame
  numbering offset.
- **Done Marker**: App POSTs to `/upload_done` after all crops are uploaded.
  The server creates `done.txt` in the crop folder. The server must return
  `200 OK` or the app logs an error (but currently does not retry).
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
- The test server constructs its own dot directory name (`{dot_id}_{YYYYMMDD}`)
  rather than using the app's `X-DOT-Directory` header. This matches the
  production edge26 receiver behavior.

## Dependencies

- `flask>=2.0.0`
- `flask-cors>=3.0.0`

Both are installed by `setup.sh` or `requirements.txt`.

## Reference: Production Receiver

The production receiver at `/Users/asehatveit/Desktop/Developer/SCL-apps/edge26_receiver.py`
adds these features not present in the test server:

- `PendingTrackTracker` – background thread that finalizes orphaned tracks
  after an idle timeout (60s), creating `done.txt` as a safety fallback
- `recover_orphaned_tracks()` – scans for tracks missing `done.txt` at startup
- `load_bugcam_config()` – loads allowed DOT IDs from `~/.config/bugcam/config.json`
- `get_or_assign_dot_id()` – first-come-first-served DOT slot assignment from config
- Mount safety check – halts startup if external drive not mounted (Pi-specific)
