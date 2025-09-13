# Endurance Tool Exploration

This project contains tools for connecting to and monitoring Garmin HRM Pro Plus and other Bluetooth heart rate monitors.

## BLE Bridge Setup

The BLE bridge connects to your heart rate monitor via Bluetooth and streams data to a WebSocket endpoint.

### Prerequisites

- macOS with Bluetooth enabled
- Python 3.8+ with uv virtual environment
- Garmin HRM Pro Plus or compatible BLE heart rate monitor

### Installation

If you haven't already installed the dependencies in your uv environment:

```bash
# Activate your uv virtual environment first
# Then install dependencies if needed:
pip install bleak websockets
```

### Testing the BLE Bridge

#### Step 1: Prepare Your HRM Pro Plus

1. **Wear the heart rate monitor** - It needs skin contact to activate
2. **Moisten the electrode areas** on the strap for better conductivity
3. **Ensure it's not connected** to your phone, watch, or other devices


#### Step 2: Run the BLE Bridge

```bash
# Terminal 2: Run the BLE bridge
cd exploratory

# Option 1: Auto-detect HRM devices (looks for "HRM" in device name)
python ble_bridge.py --ws ws://localhost:8000/ws/ingest --name "HRM"

# Option 2: Search for any heart rate device
python ble_bridge.py --ws ws://localhost:8000/ws/ingest

# Option 3: Specify exact device address (if known)
python ble_bridge.py --ws ws://localhost:8000/ws/ingest --address "XX:XX:XX:XX:XX:XX"

# Option 4: With custom device ID for logging
python ble_bridge.py --ws ws://localhost:8000/ws/ingest --name "HRM" --device-id "garmin_hrm_pro"
```

### Command Line Arguments

- `--ws` (required): WebSocket endpoint URL (e.g., `ws://localhost:8000/ws/ingest`)
- `--name`: Substring to search for in device name (e.g., "HRM", "Garmin", "Forerunner")
- `--address`: Exact Bluetooth MAC address of the device
- `--device-id`: Custom identifier for the device in logged data
- `--token`: API token for authentication (also reads from `API_TOKEN` env var)

### Troubleshooting

#### Bluetooth Issues

If you see "❌ Bluetooth is disabled":
1. Open **System Settings > Bluetooth**
2. Turn on Bluetooth
3. Run the script again

#### Device Not Found

If you see "❌ No device found" or device list without your HRM:
1. **Check the strap** - Ensure it's worn properly with good skin contact
2. **Moisten electrodes** - Use water or electrode gel on the contact pads
3. **Check battery** - Replace CR2032 battery if device doesn't appear
4. **Disconnect from other devices** - Turn off Bluetooth on paired phones/watches
5. **Try without --name flag** - This will detect any HR device

The script will show all discovered Bluetooth devices to help identify your HRM.

#### Connection Issues

If connection drops frequently:
- Move closer to your Mac (within 10 feet)
- Check for interference from other 2.4GHz devices
- Ensure good skin contact for consistent signal

### Data Format

The BLE bridge sends JSON data to the WebSocket endpoint:

```json
{
  "source": "ble_hr",
  "device_id": "HRM",
  "ts_unix_s": 1694574123.456,
  "seq": 0,
  "hr_bpm": 72,
  "rr_s": [0.833, 0.825],
  "energy_j": null,
  "battery_pct": 85
}
```

- `hr_bpm`: Heart rate in beats per minute
- `rr_s`: RR intervals in seconds (for HRV calculation)
- `battery_pct`: Device battery percentage
- `seq`: Sequence number for ordering

### Files

- `exploratory/ble_bridge.py` - Main BLE to WebSocket bridge
- `exploratory/test_ws_server.py` - Test WebSocket server for development
- `exploratory/intervals.py` - Intervals.icu integration (if needed)
- `exploratory/proplus.py` - Additional HRM Pro Plus utilities

## Supabase Integration

This project uses Supabase Functions to ingest data from external services like Google Calendar and Gmail. These functions are written in TypeScript and run on Deno.

### Structure

The Supabase functions are located in the `supabase/functions` directory:

-   `ingest-gcal/`: Ingests events from a specified Google Calendar.
-   `ingest-gmail/`: Ingests email metadata from a Gmail account.
-   `_shared/`: Contains shared code, such as Google OAuth token refresh logic.

### How it Works

1.  **Authentication**: The functions use a long-lived Google OAuth refresh token to generate new access tokens for each run.
2.  **Data Fetching**: They connect to the Google Calendar and Gmail APIs to fetch recent events and emails.
3.  **Data Storage**: The fetched data is then transformed and `upserted` into an `events` table in your Supabase database. Each event is linked to a `source` (e.g., `gcal`, `gmail`).

### Environment Variables

To run these functions, you must set the following environment variables in your Supabase project (or in a local `.env` file for local development):

-   `SUPABASE_URL`: Your project's Supabase URL.
-   `SERVICE_ROLE_KEY`: Your project's service role key for admin-level access.
-   `GOOGLE_CLIENT_ID`: Your Google Cloud project's client ID.
-   `GOOGLE_CLIENT_SECRET`: Your Google Cloud project's client secret.
-   `GOOGLE_REFRESH_TOKEN`: A valid Google OAuth refresh token with access to the required scopes (Gmail and/or Calendar).

### Database Schema

The functions expect the following tables to exist:

-   `sources`: A table to define the data sources. It should have at least `source_id` (UUID), `kind` (text, e.g., 'gcal', 'gmail'), and `last_token` (text, for sync tokens).
-   `events`: The main table for storing ingested data. Key columns include:
    -   `kind`: The type of event (e.g., 'email', 'calendar_event').
    -   `ts_range`: A `tstzrange` representing the event's time.
    -   `source_id`: A foreign key to the `sources` table.
    -   `source_ref`: The original ID from the source system (e.g., Gmail message ID).
    -   `details`: A JSONB column for storing raw metadata.

To ensure `upserts` work correctly, you need a unique constraint on the `events` table:

```sql
ALTER TABLE events
ADD CONSTRAINT events_source_id_source_ref_key UNIQUE (source_id, source_ref);
```

### Deployment

To deploy a function, use the Supabase CLI:

```bash
# Deploy the Gmail ingestion function
supabase functions deploy ingest-gmail

# Deploy the Google Calendar ingestion function
supabase functions deploy ingest-gcal
```

## License

This project is for personal/educational use.
