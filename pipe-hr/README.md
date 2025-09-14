# HR Data Streamer

Real-time heart rate data streaming from local SQLite3 database to Supabase.

## Overview

This service continuously monitors your local HRM SQLite database and streams new heart rate measurements to Supabase's `physio_measurements` table in near real-time.

## Data Flow

```
SQLite3 (/HRM/localDB/hrm_data.db)
    ↓ (poll every 2s)
HR Sync Module
    ↓ (transform & batch)
Supabase physio_measurements table
```

## Setup

1. Make sure your parent `.env` file contains:
   ```
   SUPABASE_URL=your_supabase_url
   SERVICE_ROLE_KEY=your_service_role_key
   ```

2. Install dependencies (if not already installed globally):
   ```bash
   pip install supabase python-dotenv tenacity
   ```

## Usage

### Run the Streamer
```bash
cd pipe-hr
python hr_streamer.py
```

The service will:
- Connect to your local HRM database at `../HRM/localDB/hrm_data.db`
- Poll for new records every 2 seconds
- Transform and batch upload to Supabase
- Track sync state in `.hr_sync_state.json`
- Log activity to console and `hr_sync.log`

### Test the Sync Module
```bash
python hr_sync.py
```

## Configuration

Environment variables (optional):
- `HR_SYNC_INTERVAL_SECONDS` - Polling interval (default: 2.0)
- `HR_SYNC_BATCH_SIZE` - Records per batch (default: 10)

## Data Transformation

Local SQLite record → Supabase physio_measurements:
- `hr_bpm` → `value` (float)
- `timestamp` (Unix) → `ts` (ISO timestamptz)
- `session_id` → `source_id` (UUID)
- `"heart_rate"` → `metric`
- Local `id` → `source_seq`

## State Management

- Tracks last synced timestamp in `.hr_sync_state.json`
- Resumable - won't re-sync old data after restart
- Uses simple insert (no duplicate handling since no unique constraints on physio_measurements)

## Error Handling

- Automatic retry with exponential backoff
- Graceful shutdown on Ctrl+C
- Continues running despite temporary failures
- Full logging for debugging