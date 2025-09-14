#!/usr/bin/env python3
"""
Real-time inference pipeline triggered by calendar changes
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import asyncio
import websockets
from dotenv import load_dotenv

from lib.supa import SupabaseClient
from lib.features import FeatureComputer
from lib.cohere_client import CohereClient
from lib.prompts import get_realtime_system_prompt
from lib.worker_logging import setup_logging, MetricsLogger
from lib.windows import realtime_window, format_window_size

load_dotenv()


class RealtimeInferenceEngine:
    """
    Real-time inference engine that processes calendar changes immediately
    """
    
    def __init__(self):
        self.logger = setup_logging()
        self.metrics = MetricsLogger()
        
        # Initialize clients
        self.supa = SupabaseClient()
        self.feature_computer = FeatureComputer()
        self.cohere_client = CohereClient()
        
        # Configuration
        self.stress_threshold = float(os.getenv("REALTIME_STRESS_THRESHOLD", "0.7"))
        self.min_events_for_inference = int(os.getenv("MIN_EVENTS_FOR_INFERENCE", "3"))
        
        self.logger.info("Real-time inference engine initialized")
    
    async def process_calendar_change(self, change_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a calendar change and generate real-time insights
        
        Args:
            change_data: Calendar change notification data
            
        Returns:
            Inference result or None if no inference needed
        """
        job_id = self.metrics.log_job_start("realtime_inference")
        start_time = time.time()
        
        try:
            self.logger.info(f"Processing calendar change: {change_data}")
            
            # Get time windows for analysis
            analysis_start, analysis_end = realtime_window()
            
            # Query recent events for context
            recent_events = self.supa.query_events(
                kinds=['calendar', 'email'],
                start_time=analysis_start,
                end_time=analysis_end,
                limit=100
            )
            
            self.logger.info(f"Found {len(recent_events)} recent events for analysis")
            
            # Check if we have enough data for meaningful inference
            calendar_events = [e for e in recent_events if e['kind'] == 'calendar']
            if len(calendar_events) < self.min_events_for_inference:
                self.logger.info("Not enough calendar events for meaningful inference")
                return None
            
            # Compute real-time features
            features = self.feature_computer.compute_realtime_features(
                events=recent_events,
                change_context=change_data
            )
            
            # Check stress indicators
            stress_score = self._calculate_stress_score(features, calendar_events)
            
            if stress_score < self.stress_threshold:
                self.logger.info(f"Stress score {stress_score:.2f} below threshold {self.stress_threshold}")
                return None
            
            self.logger.info(f"High stress detected (score: {stress_score:.2f}), generating inference")
            
            # Prepare context for AI
            context_data = {
                "change_trigger": change_data,
                "recent_events_sample": recent_events[:10],
                "stress_indicators": {
                    "score": stress_score,
                    "threshold": self.stress_threshold,
                    "calendar_density": len(calendar_events),
                    "email_volume": len([e for e in recent_events if e['kind'] == 'email'])
                },
                "analysis_window": {
                    "start": analysis_start.isoformat(),
                    "end": analysis_end.isoformat()
                }
            }
            
            # Generate AI inference
            system_prompt = get_realtime_system_prompt()
            inference_result, inference_metadata = self.cohere_client.generate_inference(
                system_prompt=system_prompt,
                features=features,
                context_data=context_data
            )
            
            # Enhance inference with real-time specific insights
            inference_result['realtime_context'] = {
                'triggered_by': change_data,
                'stress_score': stress_score,
                'urgency_level': self._get_urgency_level(stress_score),
                'recommended_actions': self._get_recommended_actions(stress_score, features)
            }
            
            # Store inference result
            inference_record = self.supa.upsert_inference(
                window_start=analysis_start,
                window_end=analysis_end,
                window_size=format_window_size("realtime"),
                inference_type="realtime_stress",
                model_version=inference_metadata['model_version'],
                confidence=inference_result.get('confidence', 0.5),
                result=inference_result
            )
            
            # Log metrics
            processing_time = (time.time() - start_time) * 1000
            self.metrics.log_inference_stats(
                job_id=job_id,
                model_version=inference_metadata['model_version'],
                tokens_used=inference_metadata.get('tokens_used'),
                latency_ms=processing_time,
                confidence=inference_result.get('confidence')
            )
            
            self.logger.info(f"Real-time inference completed in {processing_time:.2f}ms")
            return inference_result
            
        except Exception as e:
            self.logger.error(f"Error in real-time inference: {e}")
            self.metrics.log_job_failure(job_id, str(e))
            return None
    
    def _calculate_stress_score(self, features: Dict[str, Any], calendar_events: List[Dict]) -> float:
        """Calculate stress score based on features and recent events"""
        
        score = 0.0
        
        # Calendar density factors
        events_24h = features.get('events_24h_count', 0)
        if events_24h > 8:
            score += 0.3
        elif events_24h > 5:
            score += 0.2
        
        # Back-to-back meeting factor
        back_to_back_count = self._count_back_to_back_meetings(calendar_events)
        if back_to_back_count > 0:
            score += min(0.3, back_to_back_count * 0.1)
        
        # Stress keyword factor
        stress_keywords = ['deadline', 'urgent', 'crisis', 'interview', 'review', 'presentation']
        keyword_matches = 0
        for event in calendar_events:
            summary = event.get('details', {}).get('summary', '').lower()
            keyword_matches += sum(1 for keyword in stress_keywords if keyword in summary)
        
        if keyword_matches > 0:
            score += min(0.4, keyword_matches * 0.1)
        
        # Time of day factor (higher stress during work hours)
        now = datetime.now()
        if 9 <= now.hour <= 17:  # Work hours
            score += 0.1
        
        # Email volume factor
        emails_12h = features.get('emails_12h_count', 0)
        if emails_12h > 20:
            score += 0.2
        elif emails_12h > 10:
            score += 0.1
        
        return min(1.0, score)
    
    def _count_back_to_back_meetings(self, calendar_events: List[Dict]) -> int:
        """Count back-to-back meetings with less than 15 min gap"""
        
        if len(calendar_events) < 2:
            return 0
        
        # Sort by start time
        sorted_events = sorted(calendar_events, key=lambda e: e['ts_range'])
        
        back_to_back_count = 0
        for i in range(len(sorted_events) - 1):
            current_event = sorted_events[i]
            next_event = sorted_events[i + 1]
            
            # Parse time ranges
            current_end_str = current_event['ts_range'].split(',')[1].rstrip(')')
            next_start_str = next_event['ts_range'].split(',')[0].lstrip('[')
            
            try:
                current_end = datetime.fromisoformat(current_end_str.replace('Z', '+00:00'))
                next_start = datetime.fromisoformat(next_start_str.replace('Z', '+00:00'))
                
                gap_minutes = (next_start - current_end).total_seconds() / 60
                if gap_minutes < 15:  # Less than 15 minutes gap
                    back_to_back_count += 1
                    
            except Exception as e:
                self.logger.warning(f"Error parsing event times: {e}")
                continue
        
        return back_to_back_count
    
    def _get_urgency_level(self, stress_score: float) -> str:
        """Get urgency level based on stress score"""
        if stress_score >= 0.9:
            return "critical"
        elif stress_score >= 0.8:
            return "high"
        elif stress_score >= 0.7:
            return "medium"
        else:
            return "low"
    
    def _get_recommended_actions(self, stress_score: float, features: Dict[str, Any]) -> List[str]:
        """Get recommended actions based on stress level"""
        
        actions = []
        
        if stress_score >= 0.9:
            actions.extend([
                "Consider rescheduling non-critical meetings",
                "Take a 10-minute break between meetings",
                "Practice deep breathing exercises",
                "Delegate urgent tasks if possible"
            ])
        elif stress_score >= 0.8:
            actions.extend([
                "Block 15 minutes for buffer time between meetings",
                "Review meeting priorities and consider rescheduling",
                "Prepare meeting agendas in advance to save time"
            ])
        elif stress_score >= 0.7:
            actions.extend([
                "Take short breaks between tasks",
                "Stay hydrated and have a healthy snack",
                "Review your schedule for the next few hours"
            ])
        
        return actions


class RealtimeWebhookListener:
    """
    Webhook listener that triggers real-time inference
    """
    
    def __init__(self, inference_engine: RealtimeInferenceEngine):
        self.inference_engine = inference_engine
        self.logger = setup_logging()
        
    async def listen_for_webhooks(self, host: str = "localhost", port: int = 8765):
        """
        Listen for webhook notifications via WebSocket
        """
        self.logger.info(f"Starting webhook listener on {host}:{port}")
        
        async def handle_webhook(websocket, path):
            self.logger.info(f"Webhook connection from {websocket.remote_address}")
            
            try:
                async for message in websocket:
                    try:
                        webhook_data = json.loads(message)
                        self.logger.info(f"Received webhook: {webhook_data}")
                        
                        # Process the webhook asynchronously
                        result = await self.inference_engine.process_calendar_change(webhook_data)
                        
                        # Send response back
                        response = {
                            "status": "processed",
                            "inference_generated": result is not None,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        await websocket.send(json.dumps(response))
                        
                    except json.JSONDecodeError:
                        self.logger.error(f"Invalid JSON in webhook: {message}")
                        await websocket.send(json.dumps({"error": "Invalid JSON"}))
                    except Exception as e:
                        self.logger.error(f"Error processing webhook: {e}")
                        await websocket.send(json.dumps({"error": str(e)}))
                        
            except websockets.exceptions.ConnectionClosed:
                self.logger.info("Webhook connection closed")
        
        start_server = websockets.serve(handle_webhook, host, port)
        await start_server


def main():
    """Main entry point for real-time inference service"""
    
    # Initialize the inference engine
    inference_engine = RealtimeInferenceEngine()
    
    # Test with a sample calendar change
    test_change = {
        "event_kind": "calendar",
        "source_id": "test-source",
        "change_type": "created",
        "event_summary": "Urgent project deadline meeting",
        "event_time": datetime.now().isoformat()
    }
    
    # Run synchronous test
    asyncio.run(inference_engine.process_calendar_change(test_change))


if __name__ == "__main__":
    main()
