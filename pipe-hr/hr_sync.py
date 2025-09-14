#!/usr/bin/env python3
"""
HR Data Sync Module
Streams heart rate data from local SQLite3 DB to Supabase physio_measurements table
"""

import sqlite3
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_exponential


class HRDataSync:
    """
    Syncs heart rate data from local SQLite3 database to Supabase
    """

    def __init__(self, hr_db_path: str = "../HRM/localDB/hrm_data.db"):
        self.logger = logging.getLogger(__name__)

        # Initialize Supabase client using global env vars
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SERVICE_ROLE_KEY environment variables required")

        self.supabase: Client = create_client(supabase_url, supabase_key)

        # Local SQLite DB connection
        self.hr_db_path = hr_db_path
        self.state_file = Path(".hr_sync_state.json")

        # Load last sync state
        self.last_synced_timestamp = self._load_sync_state()

        self.logger.info(f"HR Data Sync initialized. DB: {hr_db_path}")
        self.logger.info(f"Last synced timestamp: {self.last_synced_timestamp}")

    def _load_sync_state(self) -> float:
        """Load the last synced timestamp from state file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    return state.get('last_synced_timestamp', 0.0)
        except Exception as e:
            self.logger.warning(f"Could not load sync state: {e}")

        return 0.0  # Start from beginning if no state

    def _save_sync_state(self, timestamp: float):
        """Save the last synced timestamp to state file"""
        try:
            state = {'last_synced_timestamp': timestamp}
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
            self.last_synced_timestamp = timestamp
        except Exception as e:
            self.logger.error(f"Could not save sync state: {e}")

    def get_new_hr_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get new HR records from local SQLite DB since last sync

        Args:
            limit: Maximum number of records to return

        Returns:
            List of HR record dictionaries
        """
        try:
            with sqlite3.connect(self.hr_db_path) as conn:
                conn.row_factory = sqlite3.Row  # Return rows as dictionaries
                cursor = conn.cursor()

                # Query for new records since last sync
                cursor.execute("""
                    SELECT * FROM raw_metrics
                    WHERE timestamp > ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (self.last_synced_timestamp, limit))

                records = [dict(row) for row in cursor.fetchall()]
                self.logger.debug(f"Found {len(records)} new HR records")
                return records

        except sqlite3.Error as e:
            self.logger.error(f"SQLite error: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error getting HR records: {e}")
            return []

    def ensure_hr_source_exists(self, session_id: str) -> str:
        """
        Ensure a source record exists for HR data, create if needed

        Args:
            session_id: The session ID from HR data

        Returns:
            UUID of the source record
        """
        try:
            # Generate consistent UUID from session_id
            source_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"hr_session_{session_id}"))

            # Check if source exists
            result = self.supabase.table('sources').select('source_id').eq('source_id', source_uuid).execute()

            if not result.data:
                # Create new source record
                source_record = {
                    "source_id": source_uuid,
                    "kind": "hrm",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }

                self.supabase.table('sources').insert(source_record).execute()
                self.logger.info(f"Created new HR source: {source_uuid}")

            return source_uuid

        except Exception as e:
            self.logger.error(f"Error ensuring source exists: {e}")
            # Return a fallback UUID if source creation fails
            return str(uuid.uuid5(uuid.NAMESPACE_OID, f"hr_fallback_{session_id}"))

    def transform_hr_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform local HR record to Supabase physio_measurements format

        Args:
            record: Local HR record from SQLite raw_metrics table

        Returns:
            Transformed record for Supabase
        """
        try:
            # Convert Unix timestamp to ISO format
            timestamp_dt = datetime.fromtimestamp(record['timestamp'], tz=timezone.utc)

            # Ensure source exists and get UUID
            source_uuid = self.ensure_hr_source_exists(record['session_id'])

            transformed = {
                "metric": "heart_rate",
                "ts": timestamp_dt.isoformat(),
                "value": float(record['hr_bpm']),
                "device": record.get('raw_payload', 'hrm_device'),  # Use raw_payload as device string
                "source_id": source_uuid,
                "source_seq": record.get('id'),  # Use local DB ID as sequence
                "ingested_at": datetime.now(timezone.utc).isoformat()
            }

            return transformed

        except Exception as e:
            self.logger.error(f"Error transforming record {record}: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def sync_batch_to_supabase(self, records: List[Dict[str, Any]]) -> bool:
        """
        Sync a batch of HR records to Supabase

        Args:
            records: List of transformed HR records

        Returns:
            True if successful, False otherwise
        """
        if not records:
            return True

        try:
            # Transform all records
            transformed_records = []
            for record in records:
                transformed = self.transform_hr_record(record)
                if transformed:
                    transformed_records.append(transformed)

            if not transformed_records:
                self.logger.warning("No valid records to sync")
                return True

            # Batch insert to Supabase (simple insert since no unique constraints defined)
            result = self.supabase.table('physio_measurements').insert(
                transformed_records
            ).execute()

            self.logger.info(f"Synced {len(transformed_records)} HR records to Supabase")

            # Update sync state with the latest timestamp
            latest_timestamp = max(record['timestamp'] for record in records)
            self._save_sync_state(latest_timestamp)

            return True

        except Exception as e:
            self.logger.error(f"Error syncing to Supabase: {e}")
            raise  # Re-raise for retry mechanism

    def sync_new_data(self, batch_size: int = 10) -> int:
        """
        Sync new HR data from local DB to Supabase

        Args:
            batch_size: Number of records to process in one batch

        Returns:
            Number of records synced
        """
        try:
            # Get new records from local DB
            new_records = self.get_new_hr_records(limit=batch_size)

            if not new_records:
                self.logger.debug("No new HR records to sync")
                return 0

            # Sync to Supabase
            success = self.sync_batch_to_supabase(new_records)

            if success:
                return len(new_records)
            else:
                return 0

        except Exception as e:
            self.logger.error(f"Error in sync_new_data: {e}")
            return 0


def setup_logging():
    """Set up logging for HR sync"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('hr_sync.log')
        ]
    )
    return logging.getLogger(__name__)


if __name__ == "__main__":
    # Test the sync module
    logger = setup_logging()

    try:
        sync = HRDataSync()
        synced_count = sync.sync_new_data(batch_size=5)
        logger.info(f"Test sync completed. Records synced: {synced_count}")
    except Exception as e:
        logger.error(f"Test failed: {e}")