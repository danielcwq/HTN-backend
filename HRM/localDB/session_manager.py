#!/usr/bin/env python3
"""
Session management logic for HRM data
Handles automatic session detection and lifecycle
"""

import time
from typing import Optional, Dict, Any
from .database import HRMDatabase

class SessionManager:
    """Manages workout sessions with automatic detection"""
    
    def __init__(self, db: HRMDatabase, gap_seconds: int = 300):
        """
        Initialize session manager
        
        Args:
            db: Database instance
            gap_seconds: Seconds of inactivity before new session (default 5 min)
        """
        self.db = db
        self.gap_seconds = gap_seconds
        self.active_sessions = {}  # device_id -> session_id
        self.last_activity = {}    # device_id -> timestamp
    
    def get_or_create_session(self, device_id: str, device_name: str = None) -> str:
        """
        Get active session or create new one based on activity gap
        
        Args:
            device_id: Device identifier
            device_name: Human-readable device name
            
        Returns:
            session_id: Active or newly created session ID
        """
        current_time = time.time()
        
        # Check if we have an active session in memory
        if device_id in self.active_sessions:
            last_time = self.last_activity.get(device_id, 0)
            
            # Check if gap exceeded
            if current_time - last_time > self.gap_seconds:
                # Close old session
                self._close_session(device_id)
            else:
                # Update last activity and return active session
                self.last_activity[device_id] = current_time
                return self.active_sessions[device_id]
        
        # Check database for recent session
        session_id = self.db.get_active_session(device_id, self.gap_seconds)
        
        if session_id:
            # Reactivate existing session
            self.active_sessions[device_id] = session_id
            self.last_activity[device_id] = current_time
            return session_id
        
        # Create new session
        session_id = self.db.create_session(device_id, device_name)
        self.active_sessions[device_id] = session_id
        self.last_activity[device_id] = current_time
        
        print(f"📝 New session started: {session_id}")
        return session_id
    
    def _close_session(self, device_id: str):
        """Close active session for a device"""
        if device_id in self.active_sessions:
            session_id = self.active_sessions[device_id]
            self.db.update_session_end_time(session_id)
            
            # Get and print session stats
            stats = self.db.get_session_stats(session_id)
            duration = stats.get('duration_seconds', 0)
            
            print(f"📊 Session closed: {session_id}")
            print(f"   Duration: {duration//60:.0f}m {duration%60:.0f}s")
            print(f"   Samples: {stats.get('sample_count', 0)}")
            if stats.get('avg_hr'):
                print(f"   Avg HR: {stats['avg_hr']:.0f} bpm")
            
            del self.active_sessions[device_id]
            del self.last_activity[device_id]
    
    def close_all_sessions(self):
        """Close all active sessions"""
        for device_id in list(self.active_sessions.keys()):
            self._close_session(device_id)
    
    def update_activity(self, device_id: str):
        """Update last activity timestamp for a device"""
        self.last_activity[device_id] = time.time()
    
    def check_inactive_sessions(self):
        """Check and close inactive sessions"""
        current_time = time.time()
        
        for device_id, last_time in list(self.last_activity.items()):
            if current_time - last_time > self.gap_seconds:
                self._close_session(device_id)
