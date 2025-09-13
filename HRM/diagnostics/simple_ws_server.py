#!/usr/bin/env python3
"""
Simple robust WebSocket server for testing HRM Pro Plus data
"""

import asyncio
import json
import websockets
from datetime import datetime

async def handle_ingest(websocket):
    """Handle incoming WebSocket connections"""
    print(f"\n✅ BLE Bridge connected from {websocket.remote_address}")
    print("Waiting for heart rate data...")
    print("-" * 50)
    
    message_count = 0
    last_hr = None
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                message_count += 1
                
                # Extract key data
                hr = data.get('hr_bpm')
                battery = data.get('battery_pct')
                rr_intervals = data.get('rr_s', [])
                is_heartbeat = data.get('heartbeat', False)
                
                # Display based on message type
                if is_heartbeat:
                    print(f"[Heartbeat] Battery: {battery}%")
                elif hr is not None:
                    # Only print if HR changed or every 10th message
                    if hr != last_hr or message_count % 10 == 0:
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        rr_info = f"RR: {len(rr_intervals)} intervals" if rr_intervals else "No RR"
                        print(f"[{timestamp}] HR: {hr} bpm | {rr_info} | Battery: {battery}%")
                        last_hr = hr
                
            except json.JSONDecodeError as e:
                print(f"JSON Error: {e}")
                print(f"Raw message: {message[:100]}")
            except Exception as e:
                print(f"Processing error: {e}")
                # Don't crash - continue receiving
                continue
                
    except websockets.exceptions.ConnectionClosed:
        print(f"\n❌ BLE Bridge disconnected")
        print(f"Total messages received: {message_count}")
    except Exception as e:
        print(f"\n❌ Server error: {e}")

async def main():
    """Start the WebSocket server"""
    print("=" * 50)
    print("Simple WebSocket Server for HRM Pro Plus")
    print("=" * 50)
    print("Server: ws://localhost:8000/ws/ingest")
    print("Waiting for connection...")
    
    # Start server
    async with websockets.serve(handle_ingest, "localhost", 8000):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nServer stopped")
