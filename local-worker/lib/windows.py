#!/usr/bin/env python3
"""
Time window calculations for local-worker
Provides utility functions for time range computations
"""

import os
from datetime import datetime, timedelta
from typing import Tuple, Optional
import pytz
from dotenv import load_dotenv

load_dotenv()

def get_timezone() -> pytz.BaseTzInfo:
    """Get configured timezone"""
    tz_name = os.getenv("APP_TZ", "America/Toronto")
    return pytz.timezone(tz_name)

def now_in_tz() -> datetime:
    """Get current time in configured timezone"""
    tz = get_timezone()
    return datetime.now(tz)

def instant_physio_window(minutes_back: int = 30) -> Tuple[datetime, datetime]:
    """
    Calculate time window for instant physio data
    
    Args:
        minutes_back: How many minutes back to look
    
    Returns:
        (start_time, end_time) tuple
    """
    end_time = now_in_tz()
    start_time = end_time - timedelta(minutes=minutes_back)
    return start_time, end_time

def instant_event_window(minutes_ahead: int = 90) -> Tuple[datetime, datetime]:
    """
    Calculate time window for upcoming events
    
    Args:
        minutes_ahead: How many minutes ahead to look
    
    Returns:
        (start_time, end_time) tuple
    """
    start_time = now_in_tz()
    end_time = start_time + timedelta(minutes=minutes_ahead)
    return start_time, end_time

def multiday_historical_window(days_back: int = 3) -> Tuple[datetime, datetime]:
    """
    Calculate time window for historical multiday analysis
    
    Args:
        days_back: How many days back to analyze
    
    Returns:
        (start_time, end_time) tuple
    """
    end_time = now_in_tz().replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=days_back)
    return start_time, end_time

def multiday_forecast_window(days_ahead: int = 4) -> Tuple[datetime, datetime]:
    """
    Calculate time window for multiday forecasting
    
    Args:
        days_ahead: How many days ahead to forecast
    
    Returns:
        (start_time, end_time) tuple
    """
    start_time = now_in_tz().replace(hour=0, minute=0, second=0, microsecond=0)
    # Add 1 day to include today
    start_time = start_time + timedelta(days=1)
    end_time = start_time + timedelta(days=days_ahead)
    return start_time, end_time

def realtime_window(hours_back: int = 4, hours_ahead: int = 8) -> Tuple[datetime, datetime]:
    """
    Calculate time window for real-time analysis
    
    Args:
        hours_back: How many hours back to look for context
        hours_ahead: How many hours ahead to analyze
    
    Returns:
        (start_time, end_time) tuple
    """
    now = now_in_tz()
    start_time = now - timedelta(hours=hours_back)
    end_time = now + timedelta(hours=hours_ahead)
    return start_time, end_time

def get_inference_window(window_type: str, duration_minutes: int = 60) -> Tuple[datetime, datetime]:
    """
    Calculate time window for inference results
    
    Args:
        window_type: 'instant' or 'multiday'
        duration_minutes: Duration of inference window in minutes
    
    Returns:
        (start_time, end_time) tuple for inference validity
    """
    start_time = now_in_tz()
    
    if window_type == 'instant':
        end_time = start_time + timedelta(minutes=duration_minutes)
    elif window_type == 'multiday':
        # Multiday predictions are valid for multiple days
        days_ahead = int(os.getenv("MULTIDAY_LOOKAHEAD_DAYS", "4"))
        end_time = start_time + timedelta(days=days_ahead)
    else:
        raise ValueError(f"Unknown window_type: {window_type}")
    
    return start_time, end_time

def format_window_size(window_type: str, **kwargs) -> str:
    """
    Format window size string for database storage
    
    Args:
        window_type: 'instant' or 'multiday'
        **kwargs: Additional parameters (minutes, days, etc.)
    
    Returns:
        Formatted window size string
    """
    if window_type == 'instant':
        minutes = kwargs.get('minutes', int(os.getenv("INSTANT_WINDOW_MINUTES", "30")))
        return f"{minutes} minutes"
    elif window_type == 'multiday':
        days = kwargs.get('days', int(os.getenv("MULTIDAY_LOOKBACK_DAYS", "3")))
        return f"{days} days"
    else:
        raise ValueError(f"Unknown window_type: {window_type}")

def is_within_business_hours(dt: datetime, start_hour: int = 9, end_hour: int = 17) -> bool:
    """
    Check if datetime is within business hours
    
    Args:
        dt: Datetime to check
        start_hour: Business day start hour (24h format)
        end_hour: Business day end hour (24h format)
    
    Returns:
        True if within business hours
    """
    # Convert to local timezone if needed
    if dt.tzinfo is None:
        tz = get_timezone()
        dt = tz.localize(dt)
    else:
        tz = get_timezone()
        dt = dt.astimezone(tz)
    
    # Check weekday (Monday=0, Sunday=6)
    if dt.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check hour range
    return start_hour <= dt.hour < end_hour

def get_same_weekday_baseline(target_date: datetime, weeks_back: int = 4) -> Tuple[datetime, datetime]:
    """
    Get time range for same weekday in previous weeks (for trend analysis)
    
    Args:
        target_date: Date to find baseline for
        weeks_back: How many weeks back to look
    
    Returns:
        (start_time, end_time) tuple for baseline period
    """
    # Find the same weekday N weeks ago
    baseline_date = target_date - timedelta(weeks=weeks_back)
    
    # Get start and end of that day
    start_time = baseline_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=1)
    
    return start_time, end_time
