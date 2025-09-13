#!/usr/bin/env python3
"""Test WebSocket connection to see if data is flowing"""

import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/ws/ingest"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected! Listening for 10 seconds...")
            print("-" * 50)
            
            count = 0
            timeout = 10  # seconds
            
            try:
                while timeout > 0:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    count += 1
                    
                    # Print key info
                    hr = data.get('hr_bpm', 'N/A')
                    device = data.get('device_id', 'unknown')
                    heartbeat = data.get('heartbeat', False)
                    
                    if heartbeat:
                        print(f"[{count}] Heartbeat from {device}")
                    else:
                        print(f"[{count}] HR: {hr} bpm from {device}")
                    
                    if count >= 5:
                        break
                        
            except asyncio.TimeoutError:
                if count == 0:
                    print("❌ No data received - WebSocket is connected but no data flowing")
                    print("\nCheck that:")
                    print("1. BLE bridge is running and connected to HRM")
                    print("2. HRM is worn and transmitting")
                else:
                    print(f"\n✅ Received {count} messages")
                    
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except ConnectionRefusedError:
        print("❌ Cannot connect - is simple_ws_server.py running?")

if __name__ == "__main__":
    asyncio.run(test_ws())
