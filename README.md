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

## License

This project is for personal/educational use.
