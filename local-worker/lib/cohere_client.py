#!/usr/bin/env python3
"""
Cohere API client for local-worker
Handles AI inference with robust error handling and JSON extraction
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

import cohere
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class CohereClient:
    """Robust Cohere API client with retry logic and structured output parsing"""
    
    def __init__(self):
        """Initialize Cohere client from environment variables"""
        self.api_key = os.getenv("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError("Missing COHERE_API_KEY")
        
        self.client = cohere.ClientV2(api_key=self.api_key)
        self.model_version = os.getenv("INFERENCE_MODEL_VERSION", "command-a-reasoning-08-2025")
        logger.info(f"Initialized Cohere client with model {self.model_version}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_inference(
        self,
        system_prompt: str,
        features: Dict[str, Any],
        context_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Generate AI inference from features
        
        Args:
            system_prompt: System prompt for the model
            features: Computed features to analyze
            context_data: Additional context (raw event snippets, etc.)
        
        Returns:
            Tuple of (inference_result, metadata)
        """
        start_time = time.time()
        
        # Prepare user message
        user_message = self._format_user_message(features, context_data)
        
        logger.debug(f"Sending inference request with {len(user_message)} chars")
        
        try:
            response = self.client.chat(
                model=self.model_version,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract and parse response
            response_text = response.message.content[0].text
            inference_result = self._extract_json_response(response_text)
            
            # Build metadata
            metadata = {
                "model_version": self.model_version,
                "latency_ms": latency_ms,
                "response_length": len(response_text),
                "raw_response": response_text[:500] + "..." if len(response_text) > 500 else response_text
            }
            
            # Add token usage if available
            if hasattr(response, 'usage') and response.usage:
                metadata["tokens_used"] = getattr(response.usage, 'total_tokens', None)
            
            logger.info(f"Generated inference in {latency_ms:.1f}ms")
            return inference_result, metadata
            
        except Exception as e:
            logger.error(f"Cohere API error: {e}")
            raise
    
    def _format_user_message(
        self, 
        features: Dict[str, Any], 
        context_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format features and context into user message"""
        message_parts = []
        
        # Features section
        message_parts.append("FEATURES:")
        message_parts.append(json.dumps(features, indent=2, default=str))
        
        # Context section (if provided)
        if context_data:
            message_parts.append("\nCONTEXT:")
            message_parts.append(json.dumps(context_data, indent=2, default=str))
        
        return "\n".join(message_parts)
    
    def _extract_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        Extract structured JSON from model response with fallback parsing
        
        Args:
            response_text: Raw response from the model
        
        Returns:
            Parsed inference result
        """
        # Try to find JSON block first
        json_start = response_text.find('{')
        json_end = response_text.rfind('}')
        
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON block, trying fallback parsing")
        
        # Fallback: extract key information with regex/text parsing
        return self._fallback_parse_response(response_text)
    
    def _fallback_parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Fallback parsing when JSON extraction fails
        
        Args:
            response_text: Raw response from the model
        
        Returns:
            Best-effort parsed result
        """
        result = {
            "propensity": None,
            "drivers": [],
            "recommendations": [],
            "confidence": 0.5,
            "parsing_method": "fallback"
        }
        
        # Extract propensity score (look for numbers 0-100)
        import re
        
        # Look for patterns like "stress propensity: 75" or "score: 65"
        propensity_patterns = [
            r"propensity[:\s]+(\d{1,3})",
            r"score[:\s]+(\d{1,3})",
            r"stress[:\s]+level[:\s]+(\d{1,3})",
            r"(\d{1,3})[%\s]*stress"
        ]
        
        for pattern in propensity_patterns:
            match = re.search(pattern, response_text.lower())
            if match:
                score = int(match.group(1))
                if 0 <= score <= 100:
                    result["propensity"] = score
                    break
        
        # Extract drivers (look for bullet points or listed items)
        drivers = []
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if (line.startswith('-') or line.startswith('•') or 
                line.startswith('*') or re.match(r'^\d+\.', line)):
                # Clean up the bullet point
                clean_line = re.sub(r'^[-•*\d\.]\s*', '', line).strip()
                if len(clean_line) > 5:  # Avoid very short items
                    drivers.append(clean_line)
        
        if drivers:
            result["drivers"] = drivers[:5]  # Limit to top 5
        
        # Extract recommendations (similar approach)
        recommendation_section = False
        recommendations = []
        
        for line in lines:
            line = line.strip().lower()
            if 'recommend' in line or 'suggest' in line or 'advice' in line:
                recommendation_section = True
                continue
            
            if recommendation_section and (line.startswith('-') or line.startswith('•') or 
                                         line.startswith('*') or re.match(r'^\d+\.', line)):
                clean_line = re.sub(r'^[-•*\d\.]\s*', '', line).strip()
                if len(clean_line) > 5:
                    recommendations.append(clean_line)
        
        if recommendations:
            result["recommendations"] = recommendations[:3]  # Limit to top 3
        
        # Set confidence based on parsing success
        confidence = 0.3  # Base confidence for fallback parsing
        if result["propensity"] is not None:
            confidence += 0.3
        if result["drivers"]:
            confidence += 0.2
        if result["recommendations"]:
            confidence += 0.2
        
        result["confidence"] = min(confidence, 0.8)  # Cap at 0.8 for fallback
        
        logger.warning(f"Used fallback parsing, confidence: {result['confidence']}")
        return result
