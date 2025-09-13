#!/usr/bin/env python3
"""
Data processor for incoming HRM metrics
Handles validation, enrichment, and buffering
"""

import time
import json
from typing import Dict, Any, List, Optional
from collections import deque
import math

class DataProcessor:
    """Process and enrich incoming HRM data"""
    
    def __init__(self, buffer_size: int = 50):
        """
        Initialize data processor
        
        Args:
            buffer_size: Number of records to buffer before batch write
        """
        self.buffer_size = buffer_size
        self.buffers = {}  # session_id -> deque of records
        self.last_timestamps = {}  # session_id -> last timestamp (for deduplication)
    
    def process_ble_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw BLE bridge data into database format
        
        Args:
            data: Raw data from BLE bridge WebSocket
            
        Returns:
            Processed data ready for database insertion
        """
        
        # Extract and convert fields
        processed = {
            'timestamp': data.get('ts_unix_s', time.time()),
            'hr_bpm': data.get('hr_bpm'),
            'battery_pct': data.get('battery_pct'),
            'raw_payload': data.get('raw_payload')
        }
        
        # Process RR intervals if present
        rr_intervals = data.get('rr_s', [])
        if rr_intervals:
            processed['rr_intervals'] = rr_intervals
            # Calculate HRV (RMSSD) if we have enough RR intervals
            if len(rr_intervals) > 1:
                processed['hrv_rmssd'] = self._calculate_rmssd(rr_intervals)
        
        # Process speed and cadence data
        if 'speed_kph' in data:
            processed['speed_mps'] = data['speed_kph'] / 3.6  # Convert km/h to m/s
        elif 'speed_mps' in data:
            processed['speed_mps'] = data['speed_mps']
        
        if 'cadence_spm' in data:
            processed['cadence_spm'] = data['cadence_spm']
        
        if 'stride_length_cm' in data:
            processed['stride_length_cm'] = data['stride_length_cm']
        
        if 'total_distance_m' in data:
            processed['total_distance_m'] = data['total_distance_m']
        elif 'distance_m' in data:
            processed['total_distance_m'] = data['distance_m']
        
        # Contact status (0=not supported, 1=no contact, 2-3=good contact)
        if 'contact_status' in data:
            if isinstance(data['contact_status'], str):
                status_map = {
                    'N/A': 0,
                    'No Contact': 1,
                    'Good Contact': 2
                }
                processed['contact_status'] = status_map.get(data['contact_status'], 0)
            else:
                processed['contact_status'] = data['contact_status']
        
        # Determine if running based on speed/cadence
        speed = processed.get('speed_mps', 0)
        cadence = processed.get('cadence_spm', 0)
        processed['is_running'] = 1 if speed > 2.0 or cadence > 120 else 0
        
        return processed
    
    def _calculate_rmssd(self, rr_intervals: List[float]) -> float:
        """
        Calculate Root Mean Square of Successive Differences (HRV metric)
        
        Args:
            rr_intervals: List of RR intervals in seconds
            
        Returns:
            RMSSD in milliseconds
        """
        if len(rr_intervals) < 2:
            return 0.0
        
        # Calculate successive differences
        diffs = []
        for i in range(1, len(rr_intervals)):
            diff = (rr_intervals[i] - rr_intervals[i-1]) * 1000  # Convert to ms
            diffs.append(diff * diff)  # Square the difference
        
        # Calculate mean and square root
        if diffs:
            mean_squared = sum(diffs) / len(diffs)
            return math.sqrt(mean_squared)
        
        return 0.0
    
    def add_to_buffer(self, session_id: str, data: Dict[str, Any]) -> bool:
        """
        Add processed data to buffer for batch writing
        
        Args:
            session_id: Session identifier
            data: Processed data record
            
        Returns:
            True if buffer is full and ready to flush
        """
        
        # Check for duplicate timestamps
        timestamp = data['timestamp']
        last_ts = self.last_timestamps.get(session_id, 0)
        
        if timestamp <= last_ts:
            # Skip duplicate or out-of-order data
            return False
        
        self.last_timestamps[session_id] = timestamp
        
        # Add to buffer
        if session_id not in self.buffers:
            self.buffers[session_id] = deque(maxlen=self.buffer_size)
        
        self.buffers[session_id].append(data)
        
        # Check if buffer is full
        return len(self.buffers[session_id]) >= self.buffer_size
    
    def get_buffer(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get and clear buffer for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of buffered records
        """
        if session_id not in self.buffers:
            return []
        
        records = list(self.buffers[session_id])
        self.buffers[session_id].clear()
        return records
    
    def get_all_buffers(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all buffers (for flushing on shutdown)
        
        Returns:
            Dictionary of session_id -> list of records
        """
        result = {}
        for session_id in self.buffers:
            records = self.get_buffer(session_id)
            if records:
                result[session_id] = records
        return result
    
    def validate_data(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Validate incoming data
        
        Args:
            data: Data to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        
        # Check for required fields
        if not data:
            return "Empty data"
        
        # Validate heart rate if present
        hr = data.get('hr_bpm')
        if hr is not None:
            if not isinstance(hr, (int, float)) or hr < 30 or hr > 250:
                return f"Invalid heart rate: {hr}"
        
        # Validate battery percentage if present
        battery = data.get('battery_pct')
        if battery is not None:
            if not isinstance(battery, (int, float)) or battery < 0 or battery > 100:
                return f"Invalid battery percentage: {battery}"
        
        # Validate speed if present
        speed = data.get('speed_mps')
        if speed is not None:
            if not isinstance(speed, (int, float)) or speed < 0 or speed > 20:
                return f"Invalid speed: {speed} m/s"
        
        # Validate cadence if present
        cadence = data.get('cadence_spm')
        if cadence is not None:
            if not isinstance(cadence, (int, float)) or cadence < 0 or cadence > 300:
                return f"Invalid cadence: {cadence}"
        
        return None
