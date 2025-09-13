#!/usr/bin/env python3
"""Test data flow and force immediate database write"""

import asyncio
import json
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from localDB import HRMDatabase, SessionManager, DataProcessor

async def test_immediate_write():
    """Test with buffer size of 1 for immediate writes"""
    
    # Initialize with buffer size of 1
    db = HRMDatabase("localDB/hrm_data.db")
    session_manager = SessionManager(db, gap_seconds=300)
    processor = DataProcessor(buffer_size=1)  # Immediate write
    
    print("🧪 Testing data flow with immediate writes (buffer_size=1)")
    print("-" * 50)
    
    # Simulate incoming data
    test_data = {
        "source": "ble_hr",
        "device_id": "test_device",
        "ts_unix_s": time.time(),
        "hr_bpm": 75,
        "battery_pct": 85,
        "rr_s": [],
        "speed_kph": 0,
        "cadence_spm": 0
    }
    
    # Get or create session
    session_id = session_manager.get_or_create_session("test_device", "Test HRM")
    print(f"✅ Session created: {session_id}")
    
    # Process and add to buffer
    processed = processor.process_ble_data(test_data)
    print(f"✅ Data processed: HR={processed.get('hr_bpm')} bpm")
    
    # Add to buffer (should return True immediately with buffer_size=1)
    buffer_full = processor.add_to_buffer(session_id, processed)
    print(f"✅ Buffer full: {buffer_full}")
    
    if buffer_full:
        # Flush buffer
        records = processor.get_buffer(session_id)
        if records:
            count = db.batch_insert_raw_metrics(session_id, records)
            print(f"✅ Written {count} record(s) to database")
    
    # Check database
    metrics = db.get_recent_metrics(session_id, seconds=60)
    print(f"✅ Database now has {len(metrics)} record(s)")
    
    # Get stats
    stats = db.get_session_stats(session_id)
    print(f"📊 Session stats: {stats.get('sample_count', 0)} samples, avg HR: {stats.get('avg_hr', 0):.0f}")
    
    db.close()
    print("\n✅ Test complete - check database with: python check_db.py")

if __name__ == "__main__":
    asyncio.run(test_immediate_write())
