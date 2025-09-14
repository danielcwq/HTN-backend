#!/usr/bin/env python3
"""
Feature engineering for local-worker
Computes Layer 1 features from raw events and physio data
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
import statistics
import logging
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

class FeatureComputer:
    """Computes features from raw data for AI inference"""
    
    def __init__(self):
        self.feature_version = os.getenv("FEATURE_SPEC_VERSION", "v1")
    
    def compute_instant_features(
        self,
        physio_data: List[Dict[str, Any]],
        upcoming_events: List[Dict[str, Any]],
        window_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Compute instant features for stress propensity prediction
        
        Args:
            physio_data: Recent physiological measurements
            upcoming_events: Events in the next 90 minutes
            window_minutes: Size of the analysis window
        
        Returns:
            Dictionary of computed features
        """
        features = {
            "window_minutes": window_minutes,
            "computed_at": datetime.now().isoformat(),
            "spec_version": self.feature_version
        }
        
        # Physiological features
        physio_features = self._compute_physio_features(physio_data)
        features.update(physio_features)
        
        # Event-based features
        event_features = self._compute_event_features(upcoming_events)
        features.update(event_features)
        
        # Quality metrics
        quality_features = self._compute_quality_features(physio_data, upcoming_events)
        features.update(quality_features)
        
        logger.info(f"Computed {len(features)} instant features")
        return features
    
    def compute_multiday_features(
        self,
        historical_events: List[Dict[str, Any]],
        forecast_events: List[Dict[str, Any]],
        days_back: int = 3
    ) -> Dict[str, Any]:
        """
        Compute multiday features for longer-term stress analysis
        
        Args:
            historical_events: Events from past N days
            forecast_events: Events for next N days
            days_back: Number of historical days analyzed
        
        Returns:
            Dictionary of computed features
        """
        features = {
            "days_analyzed": days_back,
            "computed_at": datetime.now().isoformat(),
            "spec_version": self.feature_version
        }
        
        # Historical pattern analysis
        historical_features = self._compute_historical_patterns(historical_events, days_back)
        features.update(historical_features)
        
        # Forecast load analysis
        forecast_features = self._compute_forecast_load(forecast_events)
        features.update(forecast_features)
        
        # Trend analysis
        trend_features = self._compute_trend_features(historical_events)
        features.update(trend_features)
        
        logger.info(f"Computed {len(features)} multiday features")
        return features
    
    def _compute_physio_features(self, physio_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute physiological features from recent measurements"""
        features = {}
        
        if not physio_data:
            features.update({
                "hr_avg_30m": None,
                "hr_slope_15m": None,
                "hrv_delta_30m": None,
                "physio_sample_count": 0
            })
            return features
        
        # Extract heart rate values with timestamps
        hr_values = []
        hr_timestamps = []
        
        for record in physio_data:
            if record.get('metric') == 'heart_rate' and record.get('value'):
                hr_values.append(float(record['value']))
                hr_timestamps.append(datetime.fromisoformat(record['ts'].replace('Z', '+00:00')))
        
        if hr_values:
            # Average heart rate
            features["hr_avg_30m"] = statistics.mean(hr_values)
            
            # Heart rate slope (last 15 minutes vs first 15 minutes)
            if len(hr_values) >= 2:
                mid_point = len(hr_values) // 2
                first_half = statistics.mean(hr_values[:mid_point]) if mid_point > 0 else hr_values[0]
                second_half = statistics.mean(hr_values[mid_point:])
                features["hr_slope_15m"] = second_half - first_half
            else:
                features["hr_slope_15m"] = 0
        else:
            features.update({
                "hr_avg_30m": None,
                "hr_slope_15m": None
            })
        
        # HRV analysis (if available)
        hrv_values = [
            float(record['value']) for record in physio_data
            if record.get('metric') == 'hrv' and record.get('value')
        ]
        
        if len(hrv_values) >= 2:
            features["hrv_delta_30m"] = hrv_values[-1] - hrv_values[0]
        else:
            features["hrv_delta_30m"] = None
        
        features["physio_sample_count"] = len(physio_data)
        
        return features
    
    def _compute_event_features(self, upcoming_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute features from upcoming events"""
        features = {}
        
        if not upcoming_events:
            features.update({
                "next_event_in_min": None,
                "next_event_kind": None,
                "next_event_duration_min": None,
                "lookahead_event_density_90m": 0,
                "back_to_back_gap_min": None,
                "event_types_next_90m": []
            })
            return features
        
        now = datetime.now()
        
        # Sort events by start time
        sorted_events = sorted(upcoming_events, key=lambda e: self._extract_event_start(e))
        
        # Next event features
        next_event = sorted_events[0]
        next_start = self._extract_event_start(next_event)
        next_end = self._extract_event_end(next_event)
        
        features["next_event_in_min"] = (next_start - now).total_seconds() / 60
        features["next_event_kind"] = next_event.get('kind', 'unknown')
        
        if next_end:
            features["next_event_duration_min"] = (next_end - next_start).total_seconds() / 60
        else:
            features["next_event_duration_min"] = None
        
        # Event density in next 90 minutes
        features["lookahead_event_density_90m"] = len(upcoming_events)
        
        # Back-to-back events analysis
        if len(sorted_events) >= 2:
            first_end = self._extract_event_end(sorted_events[0])
            second_start = self._extract_event_start(sorted_events[1])
            
            if first_end and second_start:
                gap_minutes = (second_start - first_end).total_seconds() / 60
                features["back_to_back_gap_min"] = gap_minutes
            else:
                features["back_to_back_gap_min"] = None
        else:
            features["back_to_back_gap_min"] = None
        
        # Event type mix
        event_types = [event.get('kind', 'unknown') for event in upcoming_events]
        features["event_types_next_90m"] = list(set(event_types))
        
        return features
    
    def _compute_quality_features(
        self, 
        physio_data: List[Dict[str, Any]], 
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Compute data quality indicators"""
        features = {}
        
        # Data freshness
        now = datetime.now()
        
        if physio_data:
            latest_physio = max(
                datetime.fromisoformat(record['ts'].replace('Z', '+00:00'))
                for record in physio_data
            )
            features["physio_lag_minutes"] = (now - latest_physio).total_seconds() / 60
        else:
            features["physio_lag_minutes"] = None
        
        # Data completeness
        min_samples = int(os.getenv("MIN_PHYSIO_SAMPLES", "10"))
        features["sufficient_physio_data"] = len(physio_data) >= min_samples
        
        # Event confidence
        if events:
            confidences = [event.get('confidence', 1.0) for event in events]
            features["avg_event_confidence"] = statistics.mean(confidences)
        else:
            features["avg_event_confidence"] = None
        
        return features
    
    def _compute_historical_patterns(
        self, 
        events: List[Dict[str, Any]], 
        days_back: int
    ) -> Dict[str, Any]:
        """Analyze historical event patterns"""
        features = {}
        
        if not events:
            return {
                "avg_daily_events": 0,
                "avg_daily_scheduled_minutes": 0,
                "back_to_back_events_per_day": 0,
                "late_evening_minutes_per_day": 0,
                "early_morning_minutes_per_day": 0,
                "dominant_event_types": []
            }
        
        # Group events by day
        daily_stats = defaultdict(lambda: {
            'event_count': 0,
            'scheduled_minutes': 0,
            'back_to_back_count': 0,
            'late_evening_minutes': 0,
            'early_morning_minutes': 0,
            'event_types': []
        })
        
        for event in events:
            start_time = self._extract_event_start(event)
            end_time = self._extract_event_end(event)
            day_key = start_time.date()
            
            daily_stats[day_key]['event_count'] += 1
            daily_stats[day_key]['event_types'].append(event.get('kind', 'unknown'))
            
            if end_time:
                duration_minutes = (end_time - start_time).total_seconds() / 60
                daily_stats[day_key]['scheduled_minutes'] += duration_minutes
                
                # Late evening (after 8:30 PM)
                if start_time.hour >= 20 and start_time.minute >= 30:
                    daily_stats[day_key]['late_evening_minutes'] += duration_minutes
                
                # Early morning (before 7:30 AM)
                if start_time.hour < 7 or (start_time.hour == 7 and start_time.minute < 30):
                    daily_stats[day_key]['early_morning_minutes'] += duration_minutes
        
        # Compute averages
        if daily_stats:
            features["avg_daily_events"] = statistics.mean([
                stats['event_count'] for stats in daily_stats.values()
            ])
            features["avg_daily_scheduled_minutes"] = statistics.mean([
                stats['scheduled_minutes'] for stats in daily_stats.values()
            ])
            features["late_evening_minutes_per_day"] = statistics.mean([
                stats['late_evening_minutes'] for stats in daily_stats.values()
            ])
            features["early_morning_minutes_per_day"] = statistics.mean([
                stats['early_morning_minutes'] for stats in daily_stats.values()
            ])
            
            # Dominant event types
            all_types = []
            for stats in daily_stats.values():
                all_types.extend(stats['event_types'])
            
            type_counts = Counter(all_types)
            features["dominant_event_types"] = [
                event_type for event_type, count in type_counts.most_common(3)
            ]
        
        return features
    
    def _compute_forecast_load(self, forecast_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze upcoming event load"""
        features = {}
        
        if not forecast_events:
            return {
                "forecast_daily_avg_events": 0,
                "forecast_peak_day_events": 0,
                "forecast_total_scheduled_hours": 0
            }
        
        # Group by day
        daily_counts = defaultdict(int)
        total_duration = 0
        
        for event in forecast_events:
            start_time = self._extract_event_start(event)
            end_time = self._extract_event_end(event)
            day_key = start_time.date()
            
            daily_counts[day_key] += 1
            
            if end_time:
                duration_hours = (end_time - start_time).total_seconds() / 3600
                total_duration += duration_hours
        
        if daily_counts:
            features["forecast_daily_avg_events"] = statistics.mean(daily_counts.values())
            features["forecast_peak_day_events"] = max(daily_counts.values())
        else:
            features["forecast_daily_avg_events"] = 0
            features["forecast_peak_day_events"] = 0
        
        features["forecast_total_scheduled_hours"] = total_duration
        
        return features
    
    def _compute_trend_features(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend indicators vs baseline"""
        features = {}
        
        # Simple trend analysis - compare recent vs older events
        if len(events) < 2:
            features["event_trend_direction"] = "stable"
            return features
        
        # Split into first half and second half
        mid_point = len(events) // 2
        first_half_count = mid_point
        second_half_count = len(events) - mid_point
        
        if second_half_count > first_half_count * 1.2:
            features["event_trend_direction"] = "increasing"
        elif second_half_count < first_half_count * 0.8:
            features["event_trend_direction"] = "decreasing"
        else:
            features["event_trend_direction"] = "stable"
        
        return features
    
    def _extract_event_start(self, event: Dict[str, Any]) -> datetime:
        """Extract start time from event ts_range"""
        ts_range = event.get('ts_range', '')
        if ts_range.startswith('['):
            start_str = ts_range.split(',')[0][1:]  # Remove '['
            # Clean up the string - remove extra quotes and fix timezone
            start_str = start_str.strip('"').replace('+00', '+00:00')
            if start_str.endswith('Z'):
                start_str = start_str[:-1] + '+00:00'
            return datetime.fromisoformat(start_str)
        return datetime.now()
    
    def _extract_event_end(self, event: Dict[str, Any]) -> Optional[datetime]:
        """Extract end time from event ts_range"""
        ts_range = event.get('ts_range', '')
        if ',' in ts_range and ts_range.endswith(')'):
            end_str = ts_range.split(',')[1][:-1]  # Remove ')'
            # Clean up the string - remove extra quotes and fix timezone
            end_str = end_str.strip('"').replace('+00', '+00:00')
            if end_str.endswith('Z'):
                end_str = end_str[:-1] + '+00:00'
            return datetime.fromisoformat(end_str)
        return None
    
    def compute_realtime_features(
        self,
        events: List[Dict[str, Any]],
        change_context: Dict[str, Any],
        analysis_hours: int = 12
    ) -> Dict[str, Any]:
        """
        Compute features for real-time stress analysis triggered by calendar changes
        
        Args:
            events: Recent events (past 4 hours + next 8 hours)
            change_context: Context about what triggered this analysis
            analysis_hours: Total hours of data to analyze
        
        Returns:
            Dictionary of computed features optimized for real-time analysis
        """
        features = {
            "analysis_hours": analysis_hours,
            "computed_at": datetime.now().isoformat(),
            "spec_version": f"{self.feature_version}-realtime",
            "trigger_context": change_context
        }
        
        now = datetime.now()
        
        # Separate events by type and time
        calendar_events = [e for e in events if e['kind'] == 'calendar']
        email_events = [e for e in events if e['kind'] == 'email']
        
        # Time-based separation
        past_events = []
        upcoming_events = []
        
        for event in calendar_events:
            event_start = self._extract_event_start(event)
            if event_start < now:
                past_events.append(event)
            else:
                upcoming_events.append(event)
        
        # Real-time calendar features
        calendar_features = self._compute_realtime_calendar_features(
            past_events, upcoming_events, now
        )
        features.update(calendar_features)
        
        # Email volume features
        email_features = self._compute_realtime_email_features(email_events, now)
        features.update(email_features)
        
        # Stress indicator features
        stress_features = self._compute_realtime_stress_features(
            calendar_events, change_context, now
        )
        features.update(stress_features)
        
        # Temporal patterns
        temporal_features = self._compute_realtime_temporal_features(
            upcoming_events, now
        )
        features.update(temporal_features)
        
        return features
    
    def _compute_realtime_calendar_features(
        self, 
        past_events: List[Dict[str, Any]], 
        upcoming_events: List[Dict[str, Any]], 
        now: datetime
    ) -> Dict[str, Any]:
        """Compute calendar-specific features for real-time analysis"""
        
        features = {}
        
        # Event counts by time window
        features['past_4h_events'] = len(past_events)
        features['next_4h_events'] = len([e for e in upcoming_events 
                                        if self._extract_event_start(e) < now + timedelta(hours=4)])
        features['next_8h_events'] = len([e for e in upcoming_events 
                                        if self._extract_event_start(e) < now + timedelta(hours=8)])
        
        # Meeting density analysis
        if upcoming_events:
            next_2h_events = [e for e in upcoming_events 
                            if self._extract_event_start(e) < now + timedelta(hours=2)]
            features['next_2h_density'] = len(next_2h_events)
            
            # Calculate minimum gap between upcoming events
            upcoming_starts = [self._extract_event_start(e) for e in upcoming_events[:5]]
            upcoming_starts.sort()
            
            min_gap_minutes = float('inf')
            for i in range(len(upcoming_starts) - 1):
                gap = (upcoming_starts[i + 1] - upcoming_starts[i]).total_seconds() / 60
                min_gap_minutes = min(min_gap_minutes, gap)
            
            features['min_gap_minutes'] = min_gap_minutes if min_gap_minutes != float('inf') else None
            features['has_back_to_back'] = min_gap_minutes < 15 if min_gap_minutes != float('inf') else False
        else:
            features['next_2h_density'] = 0
            features['min_gap_minutes'] = None
            features['has_back_to_back'] = False
        
        # Recent activity level
        recent_activity = len([e for e in past_events 
                             if self._extract_event_start(e) > now - timedelta(hours=2)])
        features['recent_activity_2h'] = recent_activity
        
        return features
    
    def _compute_realtime_email_features(
        self, 
        email_events: List[Dict[str, Any]], 
        now: datetime
    ) -> Dict[str, Any]:
        """Compute email-related features for real-time analysis"""
        
        features = {}
        
        # Email volume by time window
        emails_1h = len([e for e in email_events 
                        if self._extract_event_start(e) > now - timedelta(hours=1)])
        emails_4h = len([e for e in email_events 
                        if self._extract_event_start(e) > now - timedelta(hours=4)])
        
        features['emails_1h_count'] = emails_1h
        features['emails_4h_count'] = emails_4h
        features['email_rate_4h'] = emails_4h / 4.0  # emails per hour
        
        return features
    
    def _compute_realtime_stress_features(
        self, 
        calendar_events: List[Dict[str, Any]], 
        change_context: Dict[str, Any], 
        now: datetime
    ) -> Dict[str, Any]:
        """Compute stress-specific indicators for real-time analysis"""
        
        features = {}
        
        # Stress keyword analysis
        stress_keywords = [
            'deadline', 'urgent', 'crisis', 'emergency', 'critical',
            'interview', 'review', 'presentation', 'demo', 'pitch',
            'conflict', 'issue', 'problem', 'escalation'
        ]
        
        stress_event_count = 0
        high_stress_event_count = 0
        
        for event in calendar_events:
            summary = event.get('details', {}).get('summary', '').lower()
            
            # Count stress keywords
            keyword_count = sum(1 for keyword in stress_keywords if keyword in summary)
            if keyword_count > 0:
                stress_event_count += 1
            if keyword_count > 1:
                high_stress_event_count += 1
        
        features['stress_events_count'] = stress_event_count
        features['high_stress_events_count'] = high_stress_event_count
        features['stress_event_ratio'] = stress_event_count / max(len(calendar_events), 1)
        
        # Time-of-day stress factors
        late_events = len([e for e in calendar_events 
                          if self._extract_event_start(e).hour >= 19])  # After 7 PM
        early_events = len([e for e in calendar_events 
                           if self._extract_event_start(e).hour <= 7])   # Before 8 AM
        
        features['late_evening_events'] = late_events
        features['early_morning_events'] = early_events
        features['off_hours_events'] = late_events + early_events
        
        # Change context analysis
        change_type = change_context.get('change_type', 'unknown')
        features['change_type'] = change_type
        features['change_is_addition'] = change_type in ['created', 'added']
        features['change_is_modification'] = change_type in ['updated', 'modified']
        
        return features
    
    def _compute_realtime_temporal_features(
        self, 
        upcoming_events: List[Dict[str, Any]], 
        now: datetime
    ) -> Dict[str, Any]:
        """Compute temporal patterns for real-time analysis"""
        
        features = {}
        
        if not upcoming_events:
            features['next_event_minutes'] = None
            features['longest_event_minutes'] = None
            features['avg_event_duration'] = None
            return features
        
        # Time to next event
        next_event_start = min(self._extract_event_start(e) for e in upcoming_events)
        next_event_minutes = (next_event_start - now).total_seconds() / 60
        features['next_event_minutes'] = max(0, next_event_minutes)
        
        # Event duration analysis
        durations = []
        for event in upcoming_events:
            start = self._extract_event_start(event)
            end = self._extract_event_end(event)
            if start and end:
                duration_minutes = (end - start).total_seconds() / 60
                durations.append(duration_minutes)
        
        if durations:
            features['avg_event_duration'] = statistics.mean(durations)
            features['longest_event_minutes'] = max(durations)
            features['has_long_events'] = any(d > 120 for d in durations)  # >2 hours
        else:
            features['avg_event_duration'] = None
            features['longest_event_minutes'] = None
            features['has_long_events'] = False
        
        return features