#!/usr/bin/env python3
"""
Logging configuration for local-worker
Provides structured logging with file rotation and metrics tracking
"""

import os
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import json

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup structured logging with file rotation
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        max_bytes: Maximum size per log file
        backup_count: Number of backup files to keep
    
    Returns:
        Configured logger
    """
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "local-worker.log",
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class MetricsLogger:
    """Tracks job metrics and performance"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.metrics_file = self.log_dir / "metrics.jsonl"
    
    def log_job_start(self, job_type: str, job_id: str = None) -> str:
        """Log job start and return job ID"""
        if not job_id:
            job_id = f"{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "job_type": job_type,
            "event": "job_start"
        }
        
        self._write_metrics(metrics)
        return job_id
    
    def log_job_complete(
        self,
        job_id: str,
        duration_seconds: float,
        success: bool = True,
        error: str = None,
        stats: Dict[str, Any] = None
    ):
        """Log job completion with stats"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "event": "job_complete",
            "duration_seconds": duration_seconds,
            "success": success,
            "error": error,
            "stats": stats or {}
        }
        
        self._write_metrics(metrics)
    
    def log_data_quality(
        self,
        job_id: str,
        source_lag_seconds: Dict[str, float],
        sample_counts: Dict[str, int],
        quality_gates_passed: bool
    ):
        """Log data quality metrics"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "event": "data_quality",
            "source_lag_seconds": source_lag_seconds,
            "sample_counts": sample_counts,
            "quality_gates_passed": quality_gates_passed
        }
        
        self._write_metrics(metrics)
    
    def log_inference_stats(
        self,
        job_id: str,
        model_version: str,
        tokens_used: int = None,
        latency_ms: float = None,
        confidence: float = None
    ):
        """Log inference performance metrics"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "job_id": job_id,
            "event": "inference",
            "model_version": model_version,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms,
            "confidence": confidence
        }
        
        self._write_metrics(metrics)
    
    def _write_metrics(self, metrics: Dict[str, Any]):
        """Write metrics to JSONL file"""
        try:
            with open(self.metrics_file, 'a') as f:
                f.write(json.dumps(metrics) + '\n')
        except Exception as e:
            logging.error(f"Failed to write metrics: {e}")

# Global metrics logger instance
metrics = MetricsLogger()
