#!/usr/bin/env python3
"""
WebSocket consumer that connects BLE bridge to local database
Handles data ingestion from HRM Pro Plus to SQLite
"""

import asyncio
import json
import time
import signal
import sys
from pathlib import Path
import websockets
from typing import Optional

# Add localDB to path
sys.path.append(str(Path(__file__).parent))

from localDB import HRMDatabase, SessionManager, DataProcessor

class HRMDataLogger:
    """Main data logger that connects BLE bridge to database"""
    
    def __init__(self, 
                 ws_url: str = "ws://localhost:8000/ws/ingest",
                 db_path: str = "localDB/hrm_data.db",
                 buffer_size: int = 30,
                 gap_seconds: int = 300):
        """
        Initialize data logger
        
        Args:
            ws_url: WebSocket URL of BLE bridge
            db_path: Path to SQLite database
            buffer_size: Records to buffer before batch write
            gap_seconds: Seconds of inactivity before new session
        """
        self.ws_url = ws_url
        self.db = HRMDatabase(db_path)
        self.session_manager = SessionManager(self.db, gap_seconds)
        self.processor = DataProcessor(buffer_size)
        
        self.running = True
        self.stats = {
            'total_records': 0,
            'failed_records': 0,
            'sessions_created': 0,
            'last_flush': time.time()
        }
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\n⚠️  Shutting down gracefully...")
        self.running = False
    
    async def connect_and_consume(self):
        """Connect to WebSocket and consume data"""
        retry_count = 0
        max_retries = 10
        
        while self.running:
            try:
                print(f"🔌 Connecting to {self.ws_url}...")
                
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    print("✅ Connected to BLE bridge")
                    retry_count = 0  # Reset on successful connection
                    
                    await self._consume_data(websocket)
                    
            except websockets.ConnectionClosedError as e:
                print(f"❌ Connection closed: {e}")
            except websockets.InvalidURI:
                print(f"❌ Invalid WebSocket URL: {self.ws_url}")
                break
            except Exception as e:
                print(f"❌ Connection error: {e}")
            
            if not self.running:
                break
            
            # Exponential backoff for reconnection
            retry_count += 1
            if retry_count > max_retries:
                print("❌ Max retries exceeded. Exiting.")
                break
            
            wait_time = min(2 ** retry_count, 30)
            print(f"⏳ Reconnecting in {wait_time} seconds...")
            await asyncio.sleep(wait_time)
    
    async def _consume_data(self, websocket):
        """Consume data from WebSocket"""
        print("📊 Receiving HRM data...")
        print("-" * 50)
        
        async for message in websocket:
            if not self.running:
                break
            
            try:
                # Parse JSON message
                data = json.loads(message)
                
                # Skip heartbeat messages
                if data.get('heartbeat'):
                    continue
                
                # Get device info
                device_id = data.get('device_id', 'unknown')
                device_name = data.get('device_name')
                
                # Get or create session
                session_id = self.session_manager.get_or_create_session(
                    device_id, device_name
                )
                
                # Process data
                processed = self.processor.process_ble_data(data)
                
                # Validate data
                error = self.processor.validate_data(processed)
                if error:
                    self.stats['failed_records'] += 1
                    print(f"⚠️  Invalid data: {error}")
                    continue
                
                # Add to buffer
                buffer_full = self.processor.add_to_buffer(session_id, processed)
                
                # Flush if buffer is full
                if buffer_full:
                    await self._flush_buffer(session_id)
                
                # Update stats
                self.stats['total_records'] += 1
                
                # Print status every 50 records
                if self.stats['total_records'] % 50 == 0:
                    await self._print_status()
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Invalid JSON: {e}")
                self.stats['failed_records'] += 1
            except Exception as e:
                print(f"❌ Error processing data: {e}")
                self.stats['failed_records'] += 1
    
    async def _flush_buffer(self, session_id: str = None):
        """Flush buffer(s) to database"""
        if session_id:
            # Flush specific session
            records = self.processor.get_buffer(session_id)
            if records:
                count = self.db.batch_insert_raw_metrics(session_id, records)
                self.session_manager.update_activity(session_id.split('_')[1])  # Extract device_id
                self.stats['last_flush'] = time.time()
                return count
        else:
            # Flush all buffers
            total = 0
            buffers = self.processor.get_all_buffers()
            for sid, records in buffers.items():
                if records:
                    count = self.db.batch_insert_raw_metrics(sid, records)
                    total += count
            self.stats['last_flush'] = time.time()
            return total
    
    async def _print_status(self):
        """Print current status"""
        success_rate = 100 * (1 - self.stats['failed_records'] / max(self.stats['total_records'], 1))
        
        print(f"\n📈 Status Update:")
        print(f"   Total records: {self.stats['total_records']}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Active sessions: {len(self.session_manager.active_sessions)}")
        
        # Print session stats
        for device_id, session_id in self.session_manager.active_sessions.items():
            stats = self.db.get_session_stats(session_id)
            if stats.get('avg_hr'):
                print(f"   {device_id}: HR {stats['avg_hr']:.0f} bpm, "
                      f"{stats.get('sample_count', 0)} samples")
        print("-" * 50)
    
    async def periodic_tasks(self):
        """Run periodic maintenance tasks"""
        while self.running:
            await asyncio.sleep(30)  # Run every 30 seconds
            
            if not self.running:
                break
            
            # Check for inactive sessions
            self.session_manager.check_inactive_sessions()
            
            # Flush any pending buffers
            count = await self._flush_buffer()
            if count > 0:
                print(f"💾 Flushed {count} pending records")
            
            # Compute aggregates for active sessions
            for session_id in self.session_manager.active_sessions.values():
                try:
                    agg_count = self.db.compute_aggregates(session_id, interval_seconds=30)
                    if agg_count > 0:
                        print(f"📊 Computed {agg_count} aggregates for {session_id}")
                except Exception as e:
                    print(f"⚠️  Error computing aggregates: {e}")
    
    async def run(self):
        """Main run loop"""
        print("=" * 60)
        print("🚀 HRM Data Logger")
        print("=" * 60)
        print(f"WebSocket: {self.ws_url}")
        print(f"Database: {Path(self.db.db_path).absolute()}")
        print(f"Buffer size: {self.processor.buffer_size} records")
        print(f"Session gap: {self.session_manager.gap_seconds} seconds")
        print("-" * 60)
        print("Press Ctrl+C to stop")
        print("-" * 60)
        
        # Create tasks
        consumer_task = asyncio.create_task(self.connect_and_consume())
        periodic_task = asyncio.create_task(self.periodic_tasks())
        
        try:
            # Wait for tasks
            await asyncio.gather(consumer_task, periodic_task)
        except asyncio.CancelledError:
            pass
        finally:
            # Cleanup
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup on shutdown"""
        print("\n🧹 Cleaning up...")
        
        # Flush all buffers
        count = await self._flush_buffer()
        if count > 0:
            print(f"💾 Flushed {count} pending records")
        
        # Close all sessions
        self.session_manager.close_all_sessions()
        
        # Final stats
        print("\n📊 Final Statistics:")
        print(f"   Total records: {self.stats['total_records']}")
        print(f"   Failed records: {self.stats['failed_records']}")
        
        # Close database
        self.db.close()
        print("✅ Shutdown complete")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="HRM Data Logger - SQLite backend")
    parser.add_argument("--ws", default="ws://localhost:8000/ws/ingest",
                       help="WebSocket URL (default: ws://localhost:8000/ws/ingest)")
    parser.add_argument("--db", default="localDB/hrm_data.db",
                       help="Database path (default: localDB/hrm_data.db)")
    parser.add_argument("--buffer", type=int, default=30,
                       help="Buffer size before batch write (default: 30)")
    parser.add_argument("--gap", type=int, default=300,
                       help="Session gap in seconds (default: 300)")
    
    args = parser.parse_args()
    
    logger = HRMDataLogger(
        ws_url=args.ws,
        db_path=args.db,
        buffer_size=args.buffer,
        gap_seconds=args.gap
    )
    
    await logger.run()


if __name__ == "__main__":
    asyncio.run(main())
