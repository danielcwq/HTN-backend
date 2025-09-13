#!/usr/bin/env python3
"""Quick database status check"""

import sqlite3
from pathlib import Path
from datetime import datetime

db_path = "localDB/hrm_data.db"

if not Path(db_path).exists():
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check counts
sessions = conn.execute("SELECT COUNT(*) as count FROM sessions").fetchone()['count']
metrics = conn.execute("SELECT COUNT(*) as count FROM raw_metrics").fetchone()['count']

print(f"📊 Database Status:")
print(f"   Sessions: {sessions}")
print(f"   Metrics: {metrics}")

if metrics > 0:
    # Get latest data
    latest = conn.execute("""
        SELECT timestamp, hr_bpm, speed_mps, cadence_spm 
        FROM raw_metrics 
        ORDER BY timestamp DESC 
        LIMIT 1
    """).fetchone()
    
    print(f"\n📈 Latest data:")
    print(f"   Time: {datetime.fromtimestamp(latest['timestamp']).strftime('%H:%M:%S')}")
    print(f"   HR: {latest['hr_bpm']} bpm")
    if latest['speed_mps']:
        print(f"   Speed: {latest['speed_mps']*3.6:.1f} km/h")
    if latest['cadence_spm']:
        print(f"   Cadence: {latest['cadence_spm']} spm")
else:
    print("\n⚠️  No data recorded yet")
    print("\nMake sure:")
    print("1. simple_ws_server.py is running")
    print("2. ble_bridge_stable.py is connected to your HRM")
    print("3. data_logger.py is running")
    print("4. Your HRM is worn and transmitting")

conn.close()
