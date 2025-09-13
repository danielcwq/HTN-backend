#!/usr/bin/env python3
"""
Stable BLE Bridge for HRM Pro Plus - Optimized for demos
Includes connection stability improvements and retry logic
"""

import os
import asyncio
import json
import struct
import argparse
import time
from typing import Optional
from collections import deque

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
import websockets

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR    = "00002a37-0000-1000-8000-00805f9b34fb"
BAT_SERVICE= "0000180f-0000-1000-8000-00805f9b34fb"
BAT_CHAR   = "00002a19-0000-1000-8000-00805f9b34fb"

class ConnectionManager:
    """Manages BLE connection with stability features"""
    
    def __init__(self):
        self.last_seen_time = None
        self.connection_attempts = 0
        self.last_hr = None
        self.signal_quality = deque(maxlen=10)  # Track last 10 signal qualities
        
    def update_signal_quality(self, has_rr_intervals):
        """Track signal quality based on RR interval presence"""
        self.signal_quality.append(1 if has_rr_intervals else 0)
        
    def get_signal_strength(self):
        """Get signal quality percentage"""
        if not self.signal_quality:
            return 0
        return int(sum(self.signal_quality) / len(self.signal_quality) * 100)

def parse_hrm_payload(data: bytes):
    '''Parse BLE Heart Rate Measurement characteristic (2A37).'''
    flags = data[0]
    idx = 1

    hr_16bit = flags & 0x01
    contact_detected = (flags >> 1) & 0x03  # 2 bits for contact status
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
            rr_intervals.append(rr / 1024.0)  # Convert to seconds

    return hr, energy, rr_intervals, contact_detected

async def read_battery_level(client: BleakClient) -> Optional[int]:
    try:
        val = await client.read_gatt_char(BAT_CHAR)
        return int(val[0])
    except Exception:
        return None

async def find_device_stable(name_substring: Optional[str], address: Optional[str], manager: ConnectionManager):
    """Enhanced device discovery with better error handling"""
    if address:
        return address, None
    
    print("🔍 Scanning for BLE HR devices...")
    try:
        # Use active scanning for better discovery
        devices = await BleakScanner.discover(
            timeout=10.0,
            return_adv=True  # Get advertisement data
        )
        
        if not devices:
            return None, "No Bluetooth devices found"
        
        print(f"Found {len(devices)} device(s)")
        
        # Priority search: exact name match first
        for device, adv_data in devices.values():
            device_name = device.name or adv_data.local_name or ""
            if name_substring and name_substring.lower() in device_name.lower():
                manager.last_seen_time = time.time()
                print(f"  ✓ Found: {device_name} ({device.address})")
                print(f"    RSSI: {adv_data.rssi} dBm")  # Signal strength
                return device.address, None
        
        # Fallback: look for HR service in advertisement
        for device, adv_data in devices.values():
            service_uuids = adv_data.service_uuids or []
            if HR_SERVICE.lower() in [uuid.lower() for uuid in service_uuids]:
                device_name = device.name or adv_data.local_name or "Unknown HR Device"
                manager.last_seen_time = time.time()
                print(f"  ✓ Found HR device: {device_name} ({device.address})")
                print(f"    RSSI: {adv_data.rssi} dBm")
                return device.address, None
        
        return None, f"No HR device found (searched for '{name_substring}')"
            
    except BleakError as e:
        if "bluetooth" in str(e).lower():
            return None, "Bluetooth is disabled"
        return None, f"Bluetooth error: {e}"
    except Exception as e:
        return None, f"Scan error: {e}"

async def maintain_connection(client: BleakClient, manager: ConnectionManager):
    """Periodic connection health check"""
    while True:
        await asyncio.sleep(15)  # Check every 15 seconds
        try:
            # Try to read battery as a connection test
            battery = await read_battery_level(client)
            if battery:
                signal_pct = manager.get_signal_strength()
                print(f"📶 Connection stable | Battery: {battery}% | Signal Quality: {signal_pct}%")
        except Exception:
            print("⚠️  Connection check failed")
            break

async def stream_stable(args):
    """Enhanced streaming with stability improvements"""
    ws_url = args.ws
    name_substring = args.name
    address = args.address
    device_id = args.device_id or name_substring or (address or "unknown_device")
    
    manager = ConnectionManager()
    reconnect_delay = 2  # Start with 2 second delay
    max_reconnect_delay = 30
    
    print("=" * 60)
    print("🚀 Stable BLE Bridge for HRM Pro Plus")
    print("=" * 60)
    print("Connection optimizations enabled:")
    print("  • Extended timeouts for stability")
    print("  • Signal quality monitoring")
    print("  • Automatic reconnection with backoff")
    print("  • Connection health checks")
    print("-" * 60)
    
    while True:
        try:
            # Find device
            target, error_msg = await find_device_stable(name_substring, address, manager)
            if not target:
                print(f"❌ {error_msg}")
                print(f"   Retrying in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
                continue
            
            # Reset delay on successful discovery
            reconnect_delay = 2
            manager.connection_attempts += 1
            
            print(f"\n🔗 Connecting to BLE device (attempt #{manager.connection_attempts})...")
            
            # Connect with extended timeout
            async with BleakClient(
                target,
                timeout=20.0,  # Extended timeout
                disconnected_callback=lambda c: print("⚠️  BLE device disconnected")
            ) as client:
                print("✅ Connected to HRM Pro Plus")
                
                # Read device info
                battery = await read_battery_level(client)
                if battery:
                    print(f"🔋 Battery: {battery}%")
                
                # Connect to WebSocket
                print(f"🌐 Connecting to WebSocket: {ws_url}")
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as ws:
                    print("✅ Connected to WebSocket server")
                    print("-" * 60)
                    print("Streaming heart rate data...")
                    print("-" * 60)
                    
                    seq = 0
                    last_sent_ts = 0.0
                    data_received = False
                    
                    # Start connection monitor task
                    monitor_task = asyncio.create_task(maintain_connection(client, manager))
                    
                    def handle_notification(_, payload: bytearray):
                        nonlocal seq, last_sent_ts, battery, data_received
                        
                        data_received = True
                        hr, energy, rr, contact = parse_hrm_payload(bytes(payload))
                        
                        # Update signal quality
                        manager.update_signal_quality(len(rr) > 0)
                        
                        # Contact status: 0=not supported, 1=not detected, 2/3=detected
                        contact_status = ["N/A", "No Contact", "Good Contact", "Good Contact"][contact]
                        
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
                            "contact_status": contact_status,
                            "signal_quality": manager.get_signal_strength()
                        }
                        seq += 1
                        
                        # Rate limit and send
                        if now - last_sent_ts >= 0.2:  # Max 5 updates per second
                            last_sent_ts = now
                            try:
                                asyncio.create_task(ws.send(json.dumps(obj)))
                                
                                # Print status occasionally
                                if seq % 25 == 0:
                                    print(f"  📊 HR: {hr} bpm | Contact: {contact_status} | "
                                          f"Signal: {manager.get_signal_strength()}% | Packets: {seq}")
                            except:
                                pass
                    
                    # Subscribe to notifications
                    await client.start_notify(HR_CHAR, handle_notification)
                    print("📡 Receiving notifications from HRM Pro Plus")
                    
                    # Keep connection alive
                    try:
                        no_data_counter = 0
                        while True:
                            await asyncio.sleep(5)
                            
                            # Check if we're receiving data
                            if not data_received:
                                no_data_counter += 1
                                if no_data_counter > 3:  # 15 seconds without data
                                    print("⚠️  No data received for 15 seconds")
                                    break
                            else:
                                no_data_counter = 0
                                data_received = False
                            
                            # Send heartbeat to WS
                            if seq % 6 == 0:  # Every 30 seconds
                                hb = {
                                    "source": "ble_hr",
                                    "device_id": device_id,
                                    "ts_unix_s": time.time(),
                                    "seq": seq,
                                    "heartbeat": True,
                                    "battery_pct": battery,
                                    "connection_attempts": manager.connection_attempts,
                                    "signal_quality": manager.get_signal_strength()
                                }
                                await ws.send(json.dumps(hb))
                    finally:
                        monitor_task.cancel()
                        try:
                            await client.stop_notify(HR_CHAR)
                        except:
                            pass
                            
        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
            print(f"🔌 WebSocket disconnected: {e}")
            print(f"   Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            
        except BleakError as e:
            print(f"📱 Bluetooth error: {e}")
            print(f"   Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
            
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            print(f"   Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stable BLE Heart Rate → WebSocket bridge")
    parser.add_argument("--ws", default="ws://localhost:8000/ws/ingest", 
                       help="WebSocket endpoint (default: ws://localhost:8000/ws/ingest)")
    parser.add_argument("--name", default="HRM", 
                       help="Device name substring (default: HRM)")
    parser.add_argument("--address", help="Exact BLE MAC address")
    parser.add_argument("--device-id", help="Device ID for logging")
    args = parser.parse_args()

    try:
        asyncio.run(stream_stable(args))
    except KeyboardInterrupt:
        print("\n\n👋 Bridge stopped by user")
