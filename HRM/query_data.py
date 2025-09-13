#!/usr/bin/env python3
"""
Query interface for retrieving and analyzing HRM data from SQLite
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Add localDB to path
sys.path.append(str(Path(__file__).parent))

from localDB import HRMDatabase

class HRMDataQuery:
    """Query interface for HRM data"""
    
    def __init__(self, db_path: str = "localDB/hrm_data.db"):
        """Initialize query interface"""
        self.db = HRMDatabase(db_path)
    
    def list_sessions(self, 
                     device_id: Optional[str] = None,
                     days_back: int = 7) -> List[Dict[str, Any]]:
        """
        List recent sessions
        
        Args:
            device_id: Filter by device (optional)
            days_back: Number of days to look back
            
        Returns:
            List of session summaries
        """
        cutoff = datetime.now().timestamp() - (days_back * 86400)
        
        if device_id:
            cursor = self.db.conn.execute("""
                SELECT 
                    s.session_id,
                    s.device_id,
                    s.device_name,
                    s.start_time,
                    s.end_time,
                    s.activity_type,
                    s.notes,
                    COUNT(r.id) as sample_count,
                    AVG(r.hr_bpm) as avg_hr,
                    MAX(r.total_distance_m) as total_distance
                FROM sessions s
                LEFT JOIN raw_metrics r ON s.session_id = r.session_id
                WHERE s.device_id = ? AND s.start_time > ?
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """, (device_id, cutoff))
        else:
            cursor = self.db.conn.execute("""
                SELECT 
                    s.session_id,
                    s.device_id,
                    s.device_name,
                    s.start_time,
                    s.end_time,
                    s.activity_type,
                    s.notes,
                    COUNT(r.id) as sample_count,
                    AVG(r.hr_bpm) as avg_hr,
                    MAX(r.total_distance_m) as total_distance
                FROM sessions s
                LEFT JOIN raw_metrics r ON s.session_id = r.session_id
                WHERE s.start_time > ?
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """, (cutoff,))
        
        sessions = []
        for row in cursor.fetchall():
            session = dict(row)
            
            # Format timestamps
            session['start_time_str'] = datetime.fromtimestamp(
                session['start_time']
            ).strftime('%Y-%m-%d %H:%M:%S')
            
            if session['end_time']:
                session['end_time_str'] = datetime.fromtimestamp(
                    session['end_time']
                ).strftime('%Y-%m-%d %H:%M:%S')
                session['duration_seconds'] = session['end_time'] - session['start_time']
                session['duration_str'] = self._format_duration(session['duration_seconds'])
            
            sessions.append(session)
        
        return sessions
    
    def get_session_details(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Detailed session information
        """
        # Get session info
        cursor = self.db.conn.execute("""
            SELECT * FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        session = dict(cursor.fetchone())
        
        # Get statistics
        stats = self.db.get_session_stats(session_id)
        session['stats'] = stats
        
        # Get heart rate zones
        zones = self._calculate_hr_zones(session_id)
        session['hr_zones'] = zones
        
        # Get aggregated metrics
        cursor = self.db.conn.execute("""
            SELECT * FROM aggregated_metrics
            WHERE session_id = ? AND interval_seconds = 30
            ORDER BY interval_start
        """, (session_id,))
        
        session['aggregates'] = [dict(row) for row in cursor.fetchall()]
        
        return session
    
    def get_raw_data(self, 
                     session_id: str,
                     start_time: Optional[float] = None,
                     end_time: Optional[float] = None,
                     limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get raw metric data for a session
        
        Args:
            session_id: Session identifier
            start_time: Start timestamp (optional)
            end_time: End timestamp (optional)
            limit: Maximum records to return
            
        Returns:
            List of raw metric records
        """
        query = "SELECT * FROM raw_metrics WHERE session_id = ?"
        params = [session_id]
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp LIMIT ?"
        params.append(limit)
        
        cursor = self.db.conn.execute(query, params)
        
        records = []
        for row in cursor.fetchall():
            record = dict(row)
            # Parse RR intervals if present
            if record.get('rr_intervals'):
                record['rr_intervals'] = json.loads(record['rr_intervals'])
            records.append(record)
        
        return records
    
    def export_session(self, session_id: str, format: str = 'json') -> str:
        """
        Export session data
        
        Args:
            session_id: Session identifier
            format: Export format ('json' or 'csv')
            
        Returns:
            Exported data as string
        """
        data = self.get_raw_data(session_id)
        
        if format == 'json':
            return json.dumps(data, indent=2)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            
            if data:
                fieldnames = ['timestamp', 'hr_bpm', 'speed_mps', 'cadence_spm', 
                             'stride_length_cm', 'total_distance_m', 'battery_pct']
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                
                for record in data:
                    # Convert timestamp to readable format
                    record['timestamp'] = datetime.fromtimestamp(
                        record['timestamp']
                    ).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    writer.writerow(record)
            
            return output.getvalue()
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _calculate_hr_zones(self, session_id: str) -> Dict[str, Any]:
        """
        Calculate time in heart rate zones
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with zone information
        """
        cursor = self.db.conn.execute("""
            SELECT hr_bpm FROM raw_metrics
            WHERE session_id = ? AND hr_bpm IS NOT NULL
        """, (session_id,))
        
        # Define zones (can be customized)
        zones = {
            'zone1': {'name': 'Recovery', 'min': 0, 'max': 110, 'count': 0},
            'zone2': {'name': 'Easy', 'min': 110, 'max': 130, 'count': 0},
            'zone3': {'name': 'Moderate', 'min': 130, 'max': 150, 'count': 0},
            'zone4': {'name': 'Hard', 'min': 150, 'max': 170, 'count': 0},
            'zone5': {'name': 'Maximum', 'min': 170, 'max': 250, 'count': 0}
        }
        
        total = 0
        for row in cursor.fetchall():
            hr = row['hr_bpm']
            total += 1
            
            for zone in zones.values():
                if zone['min'] <= hr < zone['max']:
                    zone['count'] += 1
                    break
        
        # Calculate percentages
        if total > 0:
            for zone in zones.values():
                zone['percentage'] = round(100 * zone['count'] / total, 1)
                zone['seconds'] = zone['count']  # Assuming 1Hz data
        
        return zones
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to readable string"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def get_summary_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get summary statistics for recent activity
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Summary statistics
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        
        # Total sessions
        cursor = self.db.conn.execute("""
            SELECT COUNT(*) as count FROM sessions
            WHERE start_time > ?
        """, (cutoff,))
        total_sessions = cursor.fetchone()['count']
        
        # Total time
        cursor = self.db.conn.execute("""
            SELECT SUM(end_time - start_time) as total
            FROM sessions
            WHERE start_time > ? AND end_time IS NOT NULL
        """, (cutoff,))
        total_time = cursor.fetchone()['total'] or 0
        
        # Average metrics
        cursor = self.db.conn.execute("""
            SELECT 
                AVG(hr_bpm) as avg_hr,
                MAX(hr_bpm) as max_hr,
                AVG(speed_mps) as avg_speed,
                MAX(speed_mps) as max_speed,
                COUNT(*) as total_samples
            FROM raw_metrics r
            JOIN sessions s ON r.session_id = s.session_id
            WHERE s.start_time > ? AND hr_bpm IS NOT NULL
        """, (cutoff,))
        
        metrics = dict(cursor.fetchone())
        
        return {
            'days': days,
            'total_sessions': total_sessions,
            'total_time_seconds': total_time,
            'total_time_str': self._format_duration(total_time) if total_time else '0s',
            'avg_hr': round(metrics['avg_hr'], 1) if metrics['avg_hr'] else 0,
            'max_hr': metrics['max_hr'] or 0,
            'avg_speed_kph': round(metrics['avg_speed'] * 3.6, 1) if metrics['avg_speed'] else 0,
            'max_speed_kph': round(metrics['max_speed'] * 3.6, 1) if metrics['max_speed'] else 0,
            'total_samples': metrics['total_samples'] or 0
        }


def main():
    """CLI interface for querying data"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Query HRM data from SQLite")
    parser.add_argument("--db", default="localDB/hrm_data.db",
                       help="Database path")
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List sessions
    list_parser = subparsers.add_parser('list', help='List sessions')
    list_parser.add_argument('--days', type=int, default=7,
                            help='Days to look back')
    list_parser.add_argument('--device', help='Filter by device ID')
    
    # Session details
    detail_parser = subparsers.add_parser('details', help='Session details')
    detail_parser.add_argument('session_id', help='Session ID')
    
    # Export session
    export_parser = subparsers.add_parser('export', help='Export session data')
    export_parser.add_argument('session_id', help='Session ID')
    export_parser.add_argument('--format', choices=['json', 'csv'], default='json',
                              help='Export format')
    export_parser.add_argument('--output', help='Output file')
    
    # Summary stats
    stats_parser = subparsers.add_parser('stats', help='Summary statistics')
    stats_parser.add_argument('--days', type=int, default=7,
                             help='Days to analyze')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    query = HRMDataQuery(args.db)
    
    if args.command == 'list':
        sessions = query.list_sessions(device_id=args.device, days_back=args.days)
        
        if not sessions:
            print("No sessions found")
            return
        
        print(f"\n📊 Found {len(sessions)} session(s) in the last {args.days} days:\n")
        
        for session in sessions:
            print(f"Session: {session['session_id']}")
            print(f"  Device: {session['device_name'] or session['device_id']}")
            print(f"  Start: {session['start_time_str']}")
            if session.get('duration_str'):
                print(f"  Duration: {session['duration_str']}")
            if session.get('avg_hr'):
                print(f"  Avg HR: {session['avg_hr']:.0f} bpm")
            print(f"  Samples: {session['sample_count']}")
            print()
    
    elif args.command == 'details':
        details = query.get_session_details(args.session_id)
        
        print(f"\n📊 Session Details: {args.session_id}\n")
        print(f"Device: {details.get('device_name') or details.get('device_id')}")
        
        if details.get('stats'):
            stats = details['stats']
            print(f"\nStatistics:")
            print(f"  Duration: {query._format_duration(stats.get('duration_seconds', 0))}")
            print(f"  Samples: {stats.get('sample_count', 0)}")
            print(f"  HR: {stats.get('min_hr', 0)}-{stats.get('max_hr', 0)} bpm "
                  f"(avg: {stats.get('avg_hr', 0):.0f})")
            if stats.get('avg_speed'):
                print(f"  Speed: {stats['avg_speed']*3.6:.1f} km/h avg, "
                      f"{stats.get('max_speed', 0)*3.6:.1f} km/h max")
        
        if details.get('hr_zones'):
            print(f"\nHeart Rate Zones:")
            for zone_id, zone in details['hr_zones'].items():
                if zone.get('percentage', 0) > 0:
                    print(f"  {zone['name']}: {zone['percentage']}% "
                          f"({query._format_duration(zone.get('seconds', 0))})")
    
    elif args.command == 'export':
        data = query.export_session(args.session_id, format=args.format)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(data)
            print(f"✅ Exported to {args.output}")
        else:
            print(data)
    
    elif args.command == 'stats':
        stats = query.get_summary_stats(days=args.days)
        
        print(f"\n📊 Summary Statistics (last {stats['days']} days)\n")
        print(f"Total sessions: {stats['total_sessions']}")
        print(f"Total time: {stats['total_time_str']}")
        print(f"Total samples: {stats['total_samples']}")
        
        if stats['avg_hr'] > 0:
            print(f"\nHeart Rate:")
            print(f"  Average: {stats['avg_hr']} bpm")
            print(f"  Maximum: {stats['max_hr']} bpm")
        
        if stats['avg_speed_kph'] > 0:
            print(f"\nSpeed:")
            print(f"  Average: {stats['avg_speed_kph']} km/h")
            print(f"  Maximum: {stats['max_speed_kph']} km/h")


if __name__ == "__main__":
    main()
