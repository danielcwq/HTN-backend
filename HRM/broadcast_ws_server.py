#!/usr/bin/env python3
"""
WebSocket server that broadcasts BLE data to all connected clients
Allows BLE bridge to send data and data_logger to receive it
"""

import asyncio
import json
import websockets
from datetime import datetime

# Global set to track all connected clients
connected_clients = set()
# Track which client is the data source (BLE bridge)
data_source = None

async def handle_connection(websocket, path=None):
    """Handle incoming WebSocket connections"""
    global data_source
    
    # Register client
    connected_clients.add(websocket)
    client_type = "Unknown"
    
    print(f"\n✅ Client connected from {websocket.remote_address}")
    print(f"   Total clients: {len(connected_clients)}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Identify client type by first message
                if data.get('source') == 'ble_hr':
                    if data_source != websocket:
                        data_source = websocket
                        client_type = "BLE Bridge"
                        print(f"   Identified as: {client_type}")
                    
                    # Broadcast to all OTHER clients
                    if connected_clients:
                        disconnected = set()
                        for client in connected_clients:
                            if client != websocket:  # Don't echo back to sender
                                try:
                                    await client.send(message)
                                except:
                                    disconnected.add(client)
                        
                        # Remove disconnected clients
                        for client in disconnected:
                            connected_clients.discard(client)
                    
                    # Display status
                    hr = data.get('hr_bpm')
                    if hr and not data.get('heartbeat'):
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        print(f"[{timestamp}] HR: {hr} bpm → {len(connected_clients)-1} clients")
                        
            except json.JSONDecodeError:
                pass  # Might be a client checking connection
            except Exception as e:
                print(f"Error: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Unregister client
        connected_clients.discard(websocket)
        if websocket == data_source:
            data_source = None
            print(f"\n❌ BLE Bridge disconnected")
        else:
            print(f"\n❌ Client disconnected")
        print(f"   Remaining clients: {len(connected_clients)}")

async def main():
    """Start the WebSocket server"""
    print("=" * 50)
    print("Broadcast WebSocket Server for HRM Pro Plus")
    print("=" * 50)
    print("Server: ws://localhost:8000")
    print("Ready for multiple connections...")
    print("-" * 50)
    
    # Start server that handles multiple connections
    async with websockets.serve(handle_connection, "localhost", 8000):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nServer stopped")
