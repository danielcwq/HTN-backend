#!/usr/bin/env python3
"""
SQLite database schema and core operations for HRM data storage
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

class HRMDatabase:
    """Core database operations for HRM data storage"""
    
    def __init__(self, db_path: str = "hrm_data.db"):
        """Initialize database connection and create schema"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect with optimizations for time-series data
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None  # Autocommit mode
        )
        
        # Enable WAL mode for better concurrent access
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=10000")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        
        # Row factory for dict-like access
        self.conn.row_factory = sqlite3.Row
        
        self._create_schema()
    
    def _create_schema(self):
        """Create database tables and indexes"""
        
        # Sessions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time REAL NOT NULL,
                end_time REAL,
                device_id TEXT NOT NULL,
                device_name TEXT,
                activity_type TEXT DEFAULT 'unknown',
                notes TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                sync_version INTEGER DEFAULT 0,
                deleted_at REAL
            )
        """)
        
        # Raw metrics table - optimized for writes
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                hr_bpm INTEGER,
                rr_intervals TEXT,  -- JSON array
                speed_mps REAL,
                cadence_spm INTEGER,
                stride_length_cm INTEGER,
                total_distance_m REAL,
                battery_pct INTEGER,
                contact_status INTEGER,
                is_running INTEGER DEFAULT 0,
                raw_payload TEXT,  -- Hex string for debugging
                created_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        
        # Aggregated metrics table - optimized for queries
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS aggregated_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                interval_start REAL NOT NULL,
                interval_seconds INTEGER NOT NULL,  -- 5, 30, 60
                avg_hr REAL,
                min_hr INTEGER,
                max_hr INTEGER,
                avg_speed REAL,
                max_speed REAL,
                avg_cadence REAL,
                total_distance REAL,
                hrv_rmssd REAL,  -- Heart rate variability
                sample_count INTEGER,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                UNIQUE(session_id, interval_start, interval_seconds)
            )
        """)
        
        # Sync status table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_status (
                batch_id TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                row_ids TEXT NOT NULL,  -- JSON array
                sync_started_at REAL,
                sync_completed_at REAL,
                sync_status TEXT DEFAULT 'pending',  -- pending, success, failed
                error_message TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        # Create indexes for performance
        self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for query performance"""
        
        # Raw metrics indexes
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_session_time 
            ON raw_metrics(session_id, timestamp DESC)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_timestamp 
            ON raw_metrics(timestamp DESC)
        """)
        
        # Aggregated metrics indexes
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agg_session_interval 
            ON aggregated_metrics(session_id, interval_seconds, interval_start)
        """)
        
        # Sessions index
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_start 
            ON sessions(start_time DESC)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_device 
            ON sessions(device_id, start_time DESC)
        """)
    
    def create_session(self, device_id: str, device_name: str = None) -> str:
        """Create a new session"""
        session_id = f"session_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        
        self.conn.execute("""
            INSERT INTO sessions (session_id, start_time, device_id, device_name)
            VALUES (?, ?, ?, ?)
        """, (session_id, time.time(), device_id, device_name))
        
        return session_id
    
    def update_session_end_time(self, session_id: str, end_time: float = None):
        """Update session end time"""
        if end_time is None:
            end_time = time.time()
        
        self.conn.execute("""
            UPDATE sessions 
            SET end_time = ?, updated_at = ?
            WHERE session_id = ?
        """, (end_time, time.time(), session_id))
    
    def insert_raw_metric(self, session_id: str, data: Dict[str, Any]) -> int:
        """Insert a single raw metric record"""
        
        # Convert RR intervals to JSON if present
        rr_json = None
        if 'rr_intervals' in data and data['rr_intervals']:
            rr_json = json.dumps(data['rr_intervals'])
        
        cursor = self.conn.execute("""
            INSERT INTO raw_metrics (
                session_id, timestamp, hr_bpm, rr_intervals,
                speed_mps, cadence_spm, stride_length_cm,
                total_distance_m, battery_pct, contact_status,
                is_running, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            data.get('timestamp', time.time()),
            data.get('hr_bpm'),
            rr_json,
            data.get('speed_mps'),
            data.get('cadence_spm'),
            data.get('stride_length_cm'),
            data.get('total_distance_m'),
            data.get('battery_pct'),
            data.get('contact_status'),
            data.get('is_running', 0),
            data.get('raw_payload')
        ))
        
        return cursor.lastrowid
    
    def batch_insert_raw_metrics(self, session_id: str, metrics: List[Dict[str, Any]]) -> int:
        """Batch insert multiple raw metrics for better performance"""
        
        prepared_data = []
        for data in metrics:
            rr_json = None
            if 'rr_intervals' in data and data['rr_intervals']:
                rr_json = json.dumps(data['rr_intervals'])
            
            prepared_data.append((
                session_id,
                data.get('timestamp', time.time()),
                data.get('hr_bpm'),
                rr_json,
                data.get('speed_mps'),
                data.get('cadence_spm'),
                data.get('stride_length_cm'),
                data.get('total_distance_m'),
                data.get('battery_pct'),
                data.get('contact_status'),
                data.get('is_running', 0),
                data.get('raw_payload')
            ))
        
        self.conn.executemany("""
            INSERT INTO raw_metrics (
                session_id, timestamp, hr_bpm, rr_intervals,
                speed_mps, cadence_spm, stride_length_cm,
                total_distance_m, battery_pct, contact_status,
                is_running, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, prepared_data)
        
        return len(prepared_data)
    
    def get_active_session(self, device_id: str, gap_seconds: int = 300) -> Optional[str]:
        """Get active session or None if gap exceeded (default 5 minutes)"""
        
        cutoff_time = time.time() - gap_seconds
        
        cursor = self.conn.execute("""
            SELECT s.session_id 
            FROM sessions s
            WHERE s.device_id = ? 
                AND s.end_time IS NULL
                AND EXISTS (
                    SELECT 1 FROM raw_metrics r 
                    WHERE r.session_id = s.session_id 
                    AND r.timestamp > ?
                )
            ORDER BY s.start_time DESC
            LIMIT 1
        """, (device_id, cutoff_time))
        
        row = cursor.fetchone()
        return row['session_id'] if row else None
    
    def get_recent_metrics(self, session_id: str = None, seconds: int = 60, limit: int = 100) -> List[Dict]:
        """Get recent metrics for a session or all sessions"""
        
        cutoff = time.time() - seconds
        
        if session_id:
            cursor = self.conn.execute("""
                SELECT * FROM raw_metrics
                WHERE session_id = ? AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (session_id, cutoff, limit))
        else:
            cursor = self.conn.execute("""
                SELECT * FROM raw_metrics
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a session"""
        
        cursor = self.conn.execute("""
            SELECT 
                COUNT(*) as sample_count,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                MIN(hr_bpm) as min_hr,
                MAX(hr_bpm) as max_hr,
                AVG(hr_bpm) as avg_hr,
                MIN(speed_mps) as min_speed,
                MAX(speed_mps) as max_speed,
                AVG(speed_mps) as avg_speed,
                AVG(cadence_spm) as avg_cadence,
                MAX(total_distance_m) as total_distance
            FROM raw_metrics
            WHERE session_id = ? AND hr_bpm IS NOT NULL
        """, (session_id,))
        
        stats = dict(cursor.fetchone())
        
        # Calculate duration
        if stats['start_time'] and stats['end_time']:
            stats['duration_seconds'] = stats['end_time'] - stats['start_time']
        
        return stats
    
    def compute_aggregates(self, session_id: str, interval_seconds: int = 30):
        """Compute and store aggregated metrics for a session"""
        
        # Get session time range
        cursor = self.conn.execute("""
            SELECT MIN(timestamp) as start, MAX(timestamp) as end
            FROM raw_metrics
            WHERE session_id = ?
        """, (session_id,))
        
        row = cursor.fetchone()
        if not row or not row['start']:
            return 0
        
        start_time = row['start']
        end_time = row['end']
        
        # Process in intervals
        count = 0
        current = start_time
        
        while current < end_time:
            interval_end = current + interval_seconds
            
            # Get metrics for this interval
            cursor = self.conn.execute("""
                SELECT 
                    AVG(hr_bpm) as avg_hr,
                    MIN(hr_bpm) as min_hr,
                    MAX(hr_bpm) as max_hr,
                    AVG(speed_mps) as avg_speed,
                    MAX(speed_mps) as max_speed,
                    AVG(cadence_spm) as avg_cadence,
                    MAX(total_distance_m) as total_distance,
                    COUNT(*) as sample_count
                FROM raw_metrics
                WHERE session_id = ? 
                    AND timestamp >= ? 
                    AND timestamp < ?
                    AND hr_bpm IS NOT NULL
            """, (session_id, current, interval_end))
            
            row = dict(cursor.fetchone())
            
            if row['sample_count'] > 0:
                # Insert or replace aggregate
                self.conn.execute("""
                    INSERT OR REPLACE INTO aggregated_metrics (
                        session_id, interval_start, interval_seconds,
                        avg_hr, min_hr, max_hr, avg_speed, max_speed,
                        avg_cadence, total_distance, sample_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, current, interval_seconds,
                    row['avg_hr'], row['min_hr'], row['max_hr'],
                    row['avg_speed'], row['max_speed'],
                    row['avg_cadence'], row['total_distance'],
                    row['sample_count']
                ))
                count += 1
            
            current = interval_end
        
        return count
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
