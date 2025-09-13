#!/usr/bin/env python3
"""
Simple WebSocket server to test the BLE bridge
Receives and displays heart rate data from the BLE bridge
"""

import asyncio
import json
import websockets
from datetime import datetime
import math
from collections import deque

class HRMonitor:
    def __init__(self):
        self.hr_history = deque(maxlen=300)  # Keep last 5 minutes at 1Hz
        self.session_start = None
        self.total_points = 0
        self.min_hr = None
        self.max_hr = None
        self.last_battery = None
        
    def get_hr_emoji(self, hr):
        """Return emoji based on heart rate zone"""
        if hr < 60:
            return "💙"  # Resting
        elif hr < 100:
            return "💚"  # Light
        elif hr < 140:
            return "💛"  # Moderate  
        elif hr < 170:
            return "🧡"  # Hard
        else:
            return "❤️"  # Maximum
    
    def calculate_hrv(self, rr_intervals):
        """Calculate RMSSD HRV from RR intervals"""
        if not rr_intervals or len(rr_intervals) < 2:
            return None
        
        # Calculate successive differences
        diffs = []
        for i in range(1, len(rr_intervals)):
            diff = abs(rr_intervals[i] - rr_intervals[i-1])
            diffs.append(diff * 1000)  # Convert to ms
        
        # Calculate RMSSD
        if diffs:
            squared_diffs = [d**2 for d in diffs]
            mean_squared = sum(squared_diffs) / len(squared_diffs)
            rmssd = math.sqrt(mean_squared)
            return round(rmssd, 1)
        return None
    
    def process_data(self, data):
        """Process incoming heart rate data"""
        if not self.session_start:
            self.session_start = datetime.now()
        
        self.total_points += 1
        
        # Extract data
        hr = data.get('hr_bpm')
        rr_intervals = data.get('rr_s', [])
        battery = data.get('battery_pct')
        timestamp = data.get('ts_unix_s', 0)
        is_heartbeat = data.get('heartbeat', False)
        
        # Update battery if present
        if battery is not None:
            self.last_battery = battery
        
        # Skip heartbeat-only messages for HR tracking
        if is_heartbeat:
            return self.format_heartbeat(timestamp)
        
        if hr:
            # Update history
            self.hr_history.append(hr)
            
            # Update min/max
            if self.min_hr is None or hr < self.min_hr:
                self.min_hr = hr
            if self.max_hr is None or hr > self.max_hr:
                self.max_hr = hr
            
            # Calculate HRV
            hrv = self.calculate_hrv(rr_intervals)
            
            # Format output
            return self.format_hr_data(timestamp, hr, hrv, rr_intervals)
        
        return None
    
    def format_hr_data(self, timestamp, hr, hrv, rr_intervals):
        """Format heart rate data for display"""
        time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
        emoji = self.get_hr_emoji(hr)
        
        # Build output string
        output = f"[{time_str}] {emoji} {hr:3d} bpm"
        
        # Add HRV if available
        if hrv:
            output += f" | HRV: {hrv:5.1f}ms"
        else:
            output += " | HRV: ----ms"
        
        # Add signal quality indicator
        if rr_intervals and len(rr_intervals) > 0:
            output += " | ✓ Good Signal"
        else:
            output += " | ⚠ Weak Signal"
        
        # Add battery if available
        if self.last_battery:
            output += f" | 🔋 {self.last_battery}%"
        
        return output
    
    def format_heartbeat(self, timestamp):
        """Format heartbeat message"""
        time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
        output = f"[{time_str}] 💗 Heartbeat"
        if self.last_battery:
            output += f" | 🔋 {self.last_battery}%"
        return output
    
    def get_stats(self):
        """Get session statistics"""
        if not self.hr_history:
            return "No data collected yet"
        
        avg_hr = sum(self.hr_history) / len(self.hr_history)
        session_duration = (datetime.now() - self.session_start).total_seconds() if self.session_start else 0
        
        stats = f"\n📊 Session Stats:\n"
        stats += f"  Duration: {int(session_duration//60)}m {int(session_duration%60)}s\n"
        stats += f"  Avg HR: {avg_hr:.0f} bpm\n"
        stats += f"  Min/Max: {self.min_hr}/{self.max_hr} bpm\n"
        stats += f"  Data points: {self.total_points}\n"
        
        return stats

async def handle_ingest(websocket):
    """Handle incoming WebSocket connections and display received data"""
    monitor = HRMonitor()
    client_addr = websocket.remote_address
    
    print(f"\n✅ BLE Bridge connected from {client_addr}")
    print("=" * 60)
    print("Waiting for heart rate data...")
    print("=" * 60)
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Process and display data
                output = monitor.process_data(data)
                if output:
                    print(output)
                
                # Show stats every 30 data points
                if monitor.total_points % 30 == 0 and monitor.total_points > 0:
                    print(monitor.get_stats())
                    
            except json.JSONDecodeError:
                print(f"⚠️  Invalid JSON received: {message[:100]}")
            except Exception as e:
                print(f"⚠️  Error processing message: {e}")
                print(f"    Raw data: {data if 'data' in locals() else message[:200]}")
                import traceback
                traceback.print_exc()
                
    except websockets.exceptions.ConnectionClosed:
        print(f"\n❌ BLE Bridge disconnected from {client_addr}")
        if monitor.hr_history:
            print(monitor.get_stats())
    except Exception as e:
        print(f"\n❌ Connection error: {e}")

async def main():
    """Start the WebSocket server"""
    print("=" * 60)
    print("🚀 WebSocket Test Server for HRM Pro Plus")
    print("=" * 60)
    print(f"Server: ws://localhost:8000/ws/ingest")
    print("Waiting for BLE bridge to connect...")
    print("-" * 60)
    
    # Start server on all paths, we'll accept any path
    async with websockets.serve(handle_ingest, "localhost", 8000):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
