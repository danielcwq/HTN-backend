#!/usr/bin/env python3
"""
HR Data Streamer - Standalone Service
Continuously streams heart rate data from local SQLite3 DB to Supabase in near real-time
"""

import asyncio
import signal
import sys
import os
import logging
from pathlib import Path

# Add parent directory to path to access the dotenv
sys.path.append('..')
from dotenv import load_dotenv

from hr_sync import HRDataSync, setup_logging


class HRStreamer:
    """
    Continuous HR data streaming service
    """

    def __init__(self, sync_interval: float = 2.0, batch_size: int = 50):
        self.sync_interval = sync_interval
        self.batch_size = batch_size
        self.running = False
        self.hr_sync = None
        self.logger = setup_logging()

        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False

    async def start_streaming(self):
        """
        Start the continuous HR data streaming service
        """
        self.logger.info("🚀 Starting HR Data Streamer")
        self.logger.info(f"📊 Sync interval: {self.sync_interval}s, Batch size: {self.batch_size}")

        try:
            # Initialize HR sync
            self.hr_sync = HRDataSync()
            self.running = True

            total_synced = 0
            sync_cycles = 0

            while self.running:
                try:
                    # Sync new data
                    synced_count = self.hr_sync.sync_new_data(batch_size=self.batch_size)

                    if synced_count > 0:
                        total_synced += synced_count
                        self.logger.info(f"💓 Synced {synced_count} HR records (total: {total_synced})")
                    else:
                        # Only log every 30 cycles (1 minute at 2s intervals) to avoid spam
                        if sync_cycles % 30 == 0:
                            self.logger.debug(f"🔄 No new HR data (cycle {sync_cycles})")

                    sync_cycles += 1

                    # Wait for next sync cycle
                    await asyncio.sleep(self.sync_interval)

                except Exception as e:
                    self.logger.error(f"❌ Error in sync cycle: {e}")
                    # Brief pause before retrying
                    await asyncio.sleep(5.0)

        except KeyboardInterrupt:
            self.logger.info("⏹️ Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"❌ Fatal error in streamer: {e}")
        finally:
            self.logger.info(f"📈 Streamer stopped. Total HR records synced: {total_synced}")

    def run(self):
        """
        Run the HR streamer (blocking)
        """
        try:
            asyncio.run(self.start_streaming())
        except KeyboardInterrupt:
            self.logger.info("👋 HR Streamer stopped by user")
        except Exception as e:
            self.logger.error(f"❌ HR Streamer crashed: {e}")
            sys.exit(1)


def main():
    """
    Main entry point for HR streamer
    """
    # Load environment variables from parent directory
    load_dotenv("../.env")

    # Verify environment
    if not os.getenv("SUPABASE_URL") or not os.getenv("SERVICE_ROLE_KEY"):
        print("❌ Error: SUPABASE_URL and SERVICE_ROLE_KEY environment variables required")
        print("💡 Make sure .env file exists in parent directory with these variables")
        sys.exit(1)

    # Configuration from environment or defaults
    sync_interval = float(os.getenv("HR_SYNC_INTERVAL_SECONDS", "2.0"))
    batch_size = int(os.getenv("HR_SYNC_BATCH_SIZE", "50"))

    print("🫀 HR Data Streamer")
    print(f"📡 Streaming from: ../HRM/localDB/hrm_data.db")
    print(f"🎯 Target: Supabase physio_measurements table")
    print(f"⏱️ Sync interval: {sync_interval}s")
    print(f"📦 Batch size: {batch_size}")
    print("🚦 Press Ctrl+C to stop")
    print()

    # Start the streamer
    streamer = HRStreamer(
        sync_interval=sync_interval,
        batch_size=batch_size
    )
    streamer.run()


if __name__ == "__main__":
    main()