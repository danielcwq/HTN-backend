
import os
import asyncio
import json
import struct
import argparse
import time
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
import websockets

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR    = "00002a37-0000-1000-8000-00805f9b34fb"
BAT_SERVICE= "0000180f-0000-1000-8000-00805f9b34fb"
BAT_CHAR   = "00002a19-0000-1000-8000-00805f9b34fb"

def parse_hrm_payload(data: bytes):
    '''Parse BLE Heart Rate Measurement characteristic (2A37).'''
    flags = data[0]
    idx = 1

    hr_16bit = flags & 0x01
    energy_present = (flags >> 3) & 0x01
    rr_present = (flags >> 4) & 0x01

    if hr_16bit:
        hr, = struct.unpack_from("<H", data, idx); idx += 2
    else:
        hr = data[idx]; idx += 1

    energy = None
    if energy_present:
        energy, = struct.unpack_from("<H", data, idx); idx += 2

    rr_intervals = []
    if rr_present:
        while idx + 1 < len(data):
            rr, = struct.unpack_from("<H", data, idx); idx += 2
            rr_intervals.append(rr / 1024.0)  # seconds

    return hr, energy, rr_intervals

async def read_battery_level(client: BleakClient) -> Optional[int]:
    try:
        val = await client.read_gatt_char(BAT_CHAR)
        return int(val[0])
    except Exception:
        return None

async def check_bluetooth_adapter():
    """Check if Bluetooth adapter is available and enabled."""
    try:
        # Try to create a scanner - this will fail if Bluetooth is disabled
        scanner = BleakScanner()
        # Do a quick scan to verify Bluetooth is working
        await scanner.start()
        await scanner.stop()
        return True, None
    except BleakError as e:
        error_msg = str(e).lower()
        if "bluetooth" in error_msg and ("not available" in error_msg or "turned off" in error_msg or "disabled" in error_msg):
            return False, "Bluetooth is disabled"
        return False, f"Bluetooth error: {e}"
    except Exception as e:
        return False, f"Unexpected error checking Bluetooth: {e}"

async def find_device(name_substring: Optional[str], address: Optional[str]):
    if address:
        return address, None
    
    print("Scanning for BLE HR devices...")
    try:
        devices = await BleakScanner.discover(timeout=8.0)
        
        if not devices:
            return None, "No Bluetooth devices found in range"
        
        print(f"Found {len(devices)} Bluetooth device(s)")
        
        # Look for matching device
        hr_devices = []
        for d in devices:
            n = (d.name or "").lower()
            if name_substring and name_substring.lower() in n:
                print(f"  ✓ Found matching device: {d.name} ({d.address})")
                return d.address, None
            
            # Check if it's a HR device
            uuids = getattr(d, "metadata", {}).get("uuids", []) if hasattr(d, "metadata") else []
            if any(HR_SERVICE.lower() in (u or "").lower() for u in uuids):
                hr_devices.append(d)
        
        # If we found HR devices but no name match
        if hr_devices:
            device = hr_devices[0]
            print(f"  ✓ Found HR device: {device.name or 'Unknown'} ({device.address})")
            return device.address, None
        
        # List all found devices for debugging
        print("  Available devices:")
        for d in devices[:10]:  # Limit to first 10 to avoid spam
            print(f"    - {d.name or 'Unknown'} ({d.address})")
        if len(devices) > 10:
            print(f"    ... and {len(devices) - 10} more")
        
        if name_substring:
            return None, f"No device found with name containing '{name_substring}'"
        else:
            return None, "No heart rate devices found"
            
    except BleakError as e:
        error_msg = str(e).lower()
        if "bluetooth" in error_msg and ("not available" in error_msg or "turned off" in error_msg):
            return None, "Bluetooth is disabled - please enable it in System Settings"
        return None, f"Bluetooth error: {e}"
    except Exception as e:
        return None, f"Error during scan: {e}"

async def stream(args):
    ws_url = args.ws
    name_substring = args.name
    address = args.address
    device_id = args.device_id or name_substring or (address or "unknown_device")
    token = args.token or os.environ.get("API_TOKEN", "devtoken")
    
    # Check Bluetooth adapter first
    bt_available, bt_error = await check_bluetooth_adapter()
    if not bt_available:
        print(f"❌ {bt_error}")
        if "disabled" in bt_error.lower():
            print("   Please enable Bluetooth in System Settings and try again.")
            return
        print("   Retrying in 10s...")
        await asyncio.sleep(10)

    while True:
        try:
            target, error_msg = await find_device(name_substring, address)
            if not target:
                if error_msg:
                    print(f"❌ {error_msg}")
                    if "disabled" in error_msg.lower():
                        print("   Waiting 10s before checking again...")
                        await asyncio.sleep(10)
                        # Re-check adapter status
                        bt_available, bt_error = await check_bluetooth_adapter()
                        if not bt_available:
                            print(f"❌ {bt_error}")
                            continue
                    elif "no device" in error_msg.lower() or "not found" in error_msg.lower():
                        print("   Make sure your HRM Pro Plus is:")
                        print("     1. Turned on (wear it - needs skin contact)")
                        print("     2. The strap is moist for better conductivity")
                        print("     3. Not connected to another device (phone/watch)")
                        print("   Retrying in 5s...")
                        await asyncio.sleep(5)
                    else:
                        print("   Retrying in 5s...")
                        await asyncio.sleep(5)
                else:
                    print("No device found. Retrying in 5s...")
                    await asyncio.sleep(5)
                continue

            print(f"Connecting BLE → {target}")
            async with BleakClient(target) as client:
                print("Connected to BLE device")

                battery = await read_battery_level(client)
                if battery is not None:
                    print(f"Battery: {battery}%")

                ws_full = ws_url if ("token=" in ws_url) else (ws_url + (("&" if "?" in ws_url else "?") + f"token={token}"))
                async with websockets.connect(ws_full, ping_interval=20, ping_timeout=20, max_queue=1000) as ws:
                    print(f"Connected to backend WS: {ws_url}")
                    seq = 0
                    last_sent_ts = 0.0

                    def handle(_, payload: bytearray):
                        nonlocal seq, last_sent_ts, battery
                        hr, energy, rr = parse_hrm_payload(bytes(payload))
                        now = time.time()
                        obj = {
                            "source": "ble_hr",
                            "device_id": device_id,
                            "ts_unix_s": now,
                            "seq": seq,
                            "hr_bpm": hr,
                            "rr_s": rr,
                            "energy_j": energy,
                            "battery_pct": battery,
                        }
                        seq += 1
                        if now - last_sent_ts >= 0.2:
                            last_sent_ts = now
                            try:
                                asyncio.create_task(ws.send(json.dumps(obj)))
                            except Exception:
                                pass  # Ignore send errors in callback

                    await client.start_notify(HR_CHAR, handle)
                    print("Subscribed to Heart Rate Measurement notifications")

                    try:
                        while True:
                            await asyncio.sleep(30)
                            try:
                                battery = await read_battery_level(client)
                            except Exception:
                                pass
                            hb = {
                                "source": "ble_hr",
                                "device_id": device_id,
                                "ts_unix_s": time.time(),
                                "seq": seq,
                                "heartbeat": True,
                                "battery_pct": battery,
                            }
                            await ws.send(json.dumps(hb))
                    finally:
                        try:
                            await client.stop_notify(HR_CHAR)
                        except Exception:
                            pass

        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
            print(f"WS disconnected: {e}. Reconnecting in 2s...")
            await asyncio.sleep(2)
            continue
        except BleakError as e:
            error_msg = str(e).lower()
            if "bluetooth" in error_msg and ("not available" in error_msg or "turned off" in error_msg):
                print("❌ Bluetooth has been disabled. Please re-enable it.")
                print("   Waiting 10s before retry...")
                await asyncio.sleep(10)
            else:
                print(f"Bluetooth error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            continue
        except Exception as e:
            print(f"Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
            continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BLE Heart Rate → WebSocket bridge")
    parser.add_argument("--ws", required=True, help="ws://host:8000/ws/ingest")
    parser.add_argument("--name", help="Substring of BLE device name, e.g. 'HRM' or 'Forerunner'")
    parser.add_argument("--address", help="Exact BLE address (optional)")
    parser.add_argument("--device-id", help="Logical device_id to tag frames with")
    parser.add_argument("--token", help="API token (also reads API_TOKEN env var)")
    args = parser.parse_args()

    asyncio.run(stream(args))
