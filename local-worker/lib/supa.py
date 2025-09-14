#!/usr/bin/env python3
"""
Supabase client wrapper for local-worker
Provides connection management and query helpers
"""

import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Wrapper for Supabase client with retry logic and connection management"""
    
    def __init__(self, env_file: str = ".env"):
        """Initialize Supabase client from environment variables"""
        load_dotenv(env_file)
        
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SERVICE_ROLE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Missing SUPABASE_URL or SERVICE_ROLE_KEY")
        
        self.client: Client = create_client(self.url, self.key)
        logger.info(f"Initialized Supabase client for {self.url}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def query_events(
        self, 
        kinds: List[str] = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Query events table with time range filtering
        
        Args:
            kinds: Event types to filter by (e.g., ['email', 'calendar'])
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum records to return
        
        Returns:
            List of event records
        """
        query = self.client.table('events').select('*')
        
        if kinds:
            query = query.in_('kind', kinds)
        
        if start_time:
            query = query.gte('ts_range', f"[{start_time.isoformat()},)")
        
        if end_time:
            query = query.lt('ts_range', f"[{end_time.isoformat()},)")
        
        query = query.limit(limit).order('ts_range')
        
        response = query.execute()
        logger.debug(f"Retrieved {len(response.data)} events")
        return response.data
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def query_physio_measurements(
        self,
        metrics: List[str] = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Query physio_measurements table
        
        Args:
            metrics: Metric types to filter by (e.g., ['heart_rate', 'hrv'])
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum records to return
        
        Returns:
            List of physio measurement records
        """
        query = self.client.table('physio_measurements').select('*')
        
        if metrics:
            query = query.in_('metric', metrics)
        
        if start_time:
            query = query.gte('ts', start_time.isoformat())
        
        if end_time:
            query = query.lt('ts', end_time.isoformat())
        
        query = query.limit(limit).order('ts')
        
        response = query.execute()
        logger.debug(f"Retrieved {len(response.data)} physio measurements")
        return response.data
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def query_sources(self) -> List[Dict[str, Any]]:
        """Query sources table for data quality checks"""
        response = self.client.table('sources').select('*').execute()
        logger.debug(f"Retrieved {len(response.data)} sources")
        return response.data
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def upsert_features(
        self,
        window_end: datetime,
        window_size: str,
        spec_version: str,
        features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Upsert features record
        
        Args:
            window_end: End time of the feature window
            window_size: Size of the window (e.g., '30 minutes', '3 days')
            spec_version: Feature specification version
            features: Feature values as JSON
        
        Returns:
            Upserted record
        """
        record = {
            'window_end': window_end.isoformat(),
            'window_size': window_size,
            'spec_version': spec_version,
            'features': features
        }
        
        response = self.client.table('features').upsert(record).execute()
        logger.info(f"Upserted features record: {window_end}, {window_size}")
        return response.data[0] if response.data else None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def upsert_inference(
        self,
        namespace: str,
        name: str,
        ts_range_start: datetime,
        ts_range_end: datetime,
        value: Dict[str, Any],
        model_version: str,
        input_refs: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Upsert inference record
        
        Args:
            namespace: Inference namespace (e.g., 'instant', 'multiday')
            name: Inference name (e.g., 'stress_propensity')
            ts_range_start: Start of prediction time range
            ts_range_end: End of prediction time range
            value: Inference result as JSON
            model_version: Model version used
            input_refs: References to input data
        
        Returns:
            Upserted record
        """
        ts_range = f"[{ts_range_start.isoformat()},{ts_range_end.isoformat()})"
        
        record = {
            'namespace': namespace,
            'name': name,
            'ts_range': ts_range,
            'value': value,
            'model_version': model_version,
            'input_refs': input_refs or {},
            'ingested_at': datetime.now().isoformat()
        }
        
        response = self.client.table('inferences').upsert(record).execute()
        logger.info(f"Upserted inference: {namespace}.{name} for {ts_range}")
        return response.data[0] if response.data else None
