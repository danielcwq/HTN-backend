#!/usr/bin/env python3
"""
Local worker entrypoint for endurance tool exploration
Orchestrates multiday inference jobs for stress propensity analysis
"""

import os
import sys
import argparse
import time
from datetime import datetime
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from supa import SupabaseClient
from worker_logging import setup_logging, MetricsLogger
from windows import (
    multiday_historical_window, 
    multiday_forecast_window,
    get_inference_window,
    format_window_size
)
from features import FeatureComputer
from cohere_client import CohereClient
from prompts import get_multiday_system_prompt, get_model_version_string
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def validate_environment():
    """Validate required environment variables"""
    required_vars = [
        "SUPABASE_URL",
        "SERVICE_ROLE_KEY", 
        "COHERE_API_KEY"
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")

def check_data_quality(supa: SupabaseClient, metrics: MetricsLogger, job_id: str) -> bool:
    """
    Check data quality gates before proceeding with inference
    
    Args:
        supa: Supabase client
        metrics: Metrics logger
        job_id: Current job ID
    
    Returns:
        True if data quality is sufficient for inference
    """
    logger = setup_logging()
    
    try:
        # Check source health
        sources = supa.query_sources()
        source_lag = {}
        
        max_lag = int(os.getenv("MAX_SOURCE_LAG_SECONDS", "300"))
        
        for source in sources:
            if source.get('watermark_ts'):
                watermark = datetime.fromisoformat(source['watermark_ts'].replace('Z', '+00:00'))
                # Use timezone-aware datetime for comparison
                from windows import now_in_tz
                current_time = now_in_tz()
                lag_seconds = (current_time - watermark).total_seconds()
                source_lag[source['kind']] = lag_seconds
                
                if lag_seconds > max_lag:
                    logger.warning(f"Source {source['kind']} is stale: {lag_seconds}s lag")
            else:
                logger.warning(f"Source {source['kind']} has no watermark")
        
        # For multiday, we're less strict about real-time data
        quality_gates_passed = True
        
        # Log data quality metrics
        metrics.log_data_quality(
            job_id=job_id,
            source_lag_seconds=source_lag,
            sample_counts={"sources": len(sources)},
            quality_gates_passed=quality_gates_passed
        )
        
        return quality_gates_passed
        
    except Exception as e:
        logger.error(f"Data quality check failed: {e}")
        return False

def run_multiday_inference(dry_run: bool = False) -> bool:
    """
    Run multiday stress propensity inference
    
    Args:
        dry_run: If True, don't write to database
    
    Returns:
        True if successful
    """
    logger = setup_logging()
    metrics = MetricsLogger()
    
    job_id = metrics.log_job_start("multiday")
    start_time = time.time()
    
    try:
        logger.info(f"Starting multiday inference job {job_id}")
        
        # Initialize clients
        supa = SupabaseClient()
        feature_computer = FeatureComputer()
        cohere_client = CohereClient()
        
        # Data quality check
        if not check_data_quality(supa, metrics, job_id):
            logger.warning("Data quality gates failed, proceeding with reduced confidence")
        
        # Get time windows
        hist_start, hist_end = multiday_historical_window()
        forecast_start, forecast_end = multiday_forecast_window()
        
        logger.info(f"Historical window: {hist_start} to {hist_end}")
        logger.info(f"Forecast window: {forecast_start} to {forecast_end}")
        
        # Query historical events  
        historical_events = supa.query_events(
            kinds=['calendar', 'email'],
            start_time=hist_start,
            end_time=hist_end
        )
        
        # Query forecast events
        forecast_events = supa.query_events(
            kinds=['calendar', 'email'], 
            start_time=forecast_start,
            end_time=forecast_end
        )
        
        logger.info(f"Retrieved {len(historical_events)} historical events")
        logger.info(f"Retrieved {len(forecast_events)} forecast events")
        
        # Compute features
        features = feature_computer.compute_multiday_features(
            historical_events=historical_events,
            forecast_events=forecast_events,
            days_back=int(os.getenv("MULTIDAY_LOOKBACK_DAYS", "3"))
        )
        
        if dry_run:
            logger.info("DRY RUN: Features computed")
            logger.info(f"Features: {features}")
            return True
        
        # Write features to database
        window_size = format_window_size("multiday")
        features_record = supa.upsert_features(
            window_end=hist_end,
            window_size=window_size,
            spec_version=features['spec_version'],
            features=features
        )
        
        logger.info(f"Wrote features record: {features_record['window_end']}")
        
        # Prepare context for AI
        context_data = {
            "historical_event_sample": historical_events[:5] if historical_events else [],
            "forecast_event_sample": forecast_events[:10] if forecast_events else [],
            "analysis_period": {
                "historical_start": hist_start.isoformat(),
                "historical_end": hist_end.isoformat(),
                "forecast_start": forecast_start.isoformat(), 
                "forecast_end": forecast_end.isoformat()
            }
        }
        
        # Generate AI inference
        system_prompt = get_multiday_system_prompt()
        inference_result, inference_metadata = cohere_client.generate_inference(
            system_prompt=system_prompt,
            features=features,
            context_data=context_data
        )
        
        logger.info(f"Generated inference with confidence: {inference_result.get('confidence', 'unknown')}")
        logger.debug(f"Full inference result: {inference_result}")
        
        # Log inference metrics
        metrics.log_inference_stats(
            job_id=job_id,
            model_version=inference_metadata['model_version'],
            tokens_used=inference_metadata.get('tokens_used'),
            latency_ms=inference_metadata.get('latency_ms'),
            confidence=inference_result.get('confidence')
        )
        
        # Write inference to database
        inference_start, inference_end = get_inference_window("multiday")
        model_version = get_model_version_string("multiday")
        
        input_refs = {
            "features_window": f"{hist_start.isoformat()} to {hist_end.isoformat()}",
            "historical_events": len(historical_events),
            "forecast_events": len(forecast_events),
            "job_id": job_id
        }
        
        inference_record = supa.upsert_inference(
            namespace="multiday",
            name="stress_propensity",
            ts_range_start=inference_start,
            ts_range_end=inference_end,
            value=inference_result,
            model_version=model_version,
            input_refs=input_refs
        )
        
        logger.info(f"Wrote inference record for {inference_start} to {inference_end}")
        
        # Log job completion
        duration = time.time() - start_time
        metrics.log_job_complete(
            job_id=job_id,
            duration_seconds=duration,
            success=True,
            stats={
                "historical_events": len(historical_events),
                "forecast_events": len(forecast_events),
                "features_count": len(features),
                "inference_confidence": inference_result.get('confidence')
            }
        )
        
        logger.info(f"Multiday inference completed successfully in {duration:.1f}s")
        return True
        
    except Exception as e:
        logger.error(f"Multiday inference failed: {e}")
        duration = time.time() - start_time
        metrics.log_job_complete(
            job_id=job_id,
            duration_seconds=duration,
            success=False,
            error=str(e)
        )
        return False

def main():
    """Main entrypoint"""
    parser = argparse.ArgumentParser(description="Local worker for endurance tool exploration")
    parser.add_argument(
        "job_type", 
        choices=["multiday"],
        help="Type of job to run (instant inference not yet implemented)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute features and generate inference but don't write to database"
    )
    
    args = parser.parse_args()
    
    try:
        # Validate environment
        validate_environment()
        
        # Setup logging
        log_level = os.getenv("LOG_LEVEL", "INFO")
        logger = setup_logging(log_level=log_level)
        
        logger.info(f"Starting {args.job_type} job (dry_run={args.dry_run})")
        
        if args.job_type == "multiday":
            success = run_multiday_inference(dry_run=args.dry_run)
        else:
            logger.error(f"Job type {args.job_type} not implemented yet")
            return 1
        
        if success:
            logger.info("Job completed successfully")
            return 0
        else:
            logger.error("Job failed")
            return 1
            
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
