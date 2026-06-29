"""
Route Pattern Analyzer
Analyzes GPS routes for patterns, inefficiencies, and insights
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from collections import defaultdict


class RouteAnalyzer:
    """Analyze route patterns and provide insights"""

    def __init__(self):
        pass

    @staticmethod
    def calculate_route_efficiency(df: pd.DataFrame) -> Dict:
        """
        Calculate route efficiency metrics

        Args:
            df: DataFrame with latitude, longitude, distance, speed columns

        Returns:
            Dictionary with efficiency metrics
        """
        if 'latitude' not in df.columns or 'longitude' not in df.columns:
            return {'error': 'GPS coordinates not available'}

        # Calculate straight-line distance (as-the-crow-flies)
        start_lat, start_lon = df.iloc[0]['latitude'], df.iloc[0]['longitude']
        end_lat, end_lon = df.iloc[-1]['latitude'], df.iloc[-1]['longitude']

        straight_distance = RouteAnalyzer._haversine_distance(
            start_lat, start_lon, end_lat, end_lon
        )

        # Actual distance traveled
        actual_distance = df['Distance_km'].sum() if 'Distance_km' in df.columns else 0

        # Route efficiency (1.0 = perfect straight line)
        efficiency = straight_distance / actual_distance if actual_distance > 0 else 0

        # Detect backtracking
        backtracking_segments = RouteAnalyzer._detect_backtracking(df)

        return {
            'straight_line_distance_km': round(straight_distance, 2),
            'actual_distance_km': round(actual_distance, 2),
            'route_efficiency': round(efficiency, 3),
            'excess_distance_km': round(actual_distance - straight_distance, 2),
            'excess_percentage': round((1 - efficiency) * 100, 1),
            'backtracking_segments': len(backtracking_segments),
            'interpretation': RouteAnalyzer._interpret_efficiency(efficiency)
        }

    @staticmethod
    def detect_stop_clusters(df: pd.DataFrame, min_stops: int = 3) -> List[Dict]:
        """
        Detect geographic clusters where the driver frequently stops

        Args:
            df: DataFrame with GPS coordinates and status
            min_stops: Minimum stops to consider a cluster

        Returns:
            List of stop cluster dictionaries
        """
        if 'Status' not in df.columns:
            return []

        # Filter stopped records
        stops = df[df['Status'].str.contains('Stopped', na=False)].copy()

        if len(stops) < min_stops:
            return []

        # Simple clustering by rounding coordinates
        stops['lat_rounded'] = stops['latitude'].round(2)
        stops['lon_rounded'] = stops['longitude'].round(2)

        clusters = stops.groupby(['lat_rounded', 'lon_rounded']).agg({
            'Date Time': ['count', 'min', 'max'],
            'latitude': 'mean',
            'longitude': 'mean'
        }).reset_index()

        clusters.columns = ['lat_r', 'lon_r', 'stop_count', 'first_stop',
                            'last_stop', 'avg_lat', 'avg_lon']

        # Filter significant clusters
        significant_clusters = clusters[clusters['stop_count'] >= min_stops]

        result = []
        for _, row in significant_clusters.iterrows():
            result.append({
                'latitude': row['avg_lat'],
                'longitude': row['avg_lon'],
                'stop_count': int(row['stop_count']),
                'first_visit': row['first_stop'],
                'last_visit': row['last_stop'],
                'type': 'frequent_stop'
            })

        return result

    @staticmethod
    def analyze_speed_zones(df: pd.DataFrame) -> Dict:
        """
        Analyze speed patterns across the route

        Args:
            df: DataFrame with speed data

        Returns:
            Dictionary with speed zone analysis
        """
        if 'Speed_kmh' not in df.columns:
            return {'error': 'Speed data not available'}

        speeds = df[df['Speed_kmh'] > 0]['Speed_kmh']

        if len(speeds) == 0:
            return {'error': 'No movement data'}

        # Speed categories
        slow_speed = speeds[speeds < 20]
        moderate_speed = speeds[(speeds >= 20) & (speeds < 60)]
        normal_speed = speeds[(speeds >= 60) & (speeds < 80)]
        high_speed = speeds[speeds >= 80]

        total_records = len(speeds)

        return {
            'avg_speed_kmph': round(speeds.mean(), 1),
            'max_speed_kmph': round(speeds.max(), 1),
            'min_speed_kmph': round(speeds.min(), 1),
            'speed_std_dev': round(speeds.std(), 1),
            'slow_zone_pct': round(len(slow_speed) / total_records * 100, 1),
            'moderate_zone_pct': round(len(moderate_speed) / total_records * 100, 1),
            'normal_zone_pct': round(len(normal_speed) / total_records * 100, 1),
            'high_zone_pct': round(len(high_speed) / total_records * 100, 1),
            'speed_consistency': 'High' if speeds.std() < 15 else 'Moderate' if speeds.std() < 25 else 'Low'
        }

    @staticmethod
    def find_time_lost_to_traffic(df: pd.DataFrame, traffic_speed_threshold: int = 15) -> Dict:
        """
        Estimate time lost to traffic congestion

        Args:
            df: DataFrame with speed and time data
            traffic_speed_threshold: Speed below which we consider traffic (km/h)

        Returns:
            Dictionary with traffic delay analysis
        """
        if 'Speed_kmh' not in df.columns or 'Time_Diff_Seconds' not in df.columns:
            return {'error': 'Required data not available'}

        # Moving but slow (likely traffic)
        traffic_mask = (df['Speed_kmh'] > 0) & (df['Speed_kmh'] < traffic_speed_threshold)
        traffic_df = df[traffic_mask]

        if len(traffic_df) == 0:
            return {
                'time_lost_minutes': 0,
                'distance_in_traffic_km': 0,
                'traffic_segments': 0,
                'message': 'No significant traffic detected'
            }

        time_lost_seconds = traffic_df['Time_Diff_Seconds'].sum()
        distance_in_traffic = traffic_df['Distance_km'].sum() if 'Distance_km' in traffic_df.columns else 0

        # Estimate time if traveling at normal speed (50 km/h)
        normal_time_hours = distance_in_traffic / 50
        actual_time_hours = time_lost_seconds / 3600

        time_saved_if_no_traffic = max(0, actual_time_hours - normal_time_hours) * 60

        return {
            'time_lost_minutes': round(time_lost_seconds / 60, 1),
            'time_saved_if_no_traffic_minutes': round(time_saved_if_no_traffic, 1),
            'distance_in_traffic_km': round(distance_in_traffic, 2),
            'traffic_segments': len(traffic_df),
            'avg_traffic_speed_kmph': round(traffic_df['Speed_kmh'].mean(), 1)
        }

    @staticmethod
    def generate_route_summary(df: pd.DataFrame) -> str:
        """Generate a natural language summary of the route"""

        efficiency = RouteAnalyzer.calculate_route_efficiency(df)
        speed_zones = RouteAnalyzer.analyze_speed_zones(df)
        traffic = RouteAnalyzer.find_time_lost_to_traffic(df)

        summary_parts = []

        # Route efficiency
        if 'error' not in efficiency:
            summary_parts.append(
                f"Route covered {efficiency['actual_distance_km']} km "
                f"({efficiency['straight_line_distance_km']} km straight-line). "
                f"Route efficiency: {efficiency['route_efficiency']:.1%} - {efficiency['interpretation']}."
            )

        # Speed analysis
        if 'error' not in speed_zones:
            summary_parts.append(
                f"Average speed: {speed_zones['avg_speed_kmph']} km/h "
                f"(max: {speed_zones['max_speed_kmph']} km/h). "
                f"Speed consistency: {speed_zones['speed_consistency']}."
            )

        # Traffic delays
        if 'error' not in traffic and traffic['time_lost_minutes'] > 0:
            summary_parts.append(
                f"Encountered traffic for {traffic['time_lost_minutes']} minutes "
                f"covering {traffic['distance_in_traffic_km']} km."
            )

        return " ".join(summary_parts)

    # Helper methods

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between coordinates using Haversine formula"""
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    @staticmethod
    def _detect_backtracking(df: pd.DataFrame) -> List[int]:
        """Detect segments where vehicle is backtracking"""
        backtracking = []

        if len(df) < 3:
            return backtracking

        for i in range(1, len(df) - 1):
            prev_lat, prev_lon = df.iloc[i - 1]['latitude'], df.iloc[i - 1]['longitude']
            curr_lat, curr_lon = df.iloc[i]['latitude'], df.iloc[i]['longitude']
            next_lat, next_lon = df.iloc[i + 1]['latitude'], df.iloc[i + 1]['longitude']

            # Calculate bearings
            bearing_to_curr = RouteAnalyzer._calculate_bearing(prev_lat, prev_lon, curr_lat, curr_lon)
            bearing_to_next = RouteAnalyzer._calculate_bearing(curr_lat, curr_lon, next_lat, next_lon)

            # Backtracking if bearing changes by more than 135 degrees
            bearing_diff = abs(bearing_to_next - bearing_to_curr)
            if bearing_diff > 135 or bearing_diff < -135:
                backtracking.append(i)

        return backtracking

    @staticmethod
    def _calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing between two points"""
        from math import radians, degrees, atan2, cos, sin

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlon = lon2 - lon1
        x = sin(dlon) * cos(lat2)
        y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)

        bearing = atan2(x, y)
        return degrees(bearing)

    @staticmethod
    def _interpret_efficiency(efficiency: float) -> str:
        """Interpret route efficiency score"""
        if efficiency >= 0.9:
            return "Excellent - Very direct route"
        elif efficiency >= 0.75:
            return "Good - Minor detours"
        elif efficiency >= 0.6:
            return "Fair - Some indirect routing"
        else:
            return "Poor - Significant detours or backtracking"


# Example usage
if __name__ == "__main__":
    # Create sample data
    sample_data = {
        'latitude': [22.813, 22.815, 22.817, 22.820],
        'longitude': [86.238, 86.240, 86.242, 86.245],
        'Distance_km': [0, 0.5, 0.5, 0.5],
        'Speed_kmh': [0, 40, 45, 50],
        'Time_Diff_Seconds': [0, 45, 40, 36],
        'Status': ['Stopped', 'Moving 40', 'Moving 45', 'Moving 50']
    }

    df = pd.DataFrame(sample_data)

    analyzer = RouteAnalyzer()

    # Test route efficiency
    efficiency = analyzer.calculate_route_efficiency(df)
    print("Route Efficiency:", efficiency)

    # Test speed analysis
    speed_zones = analyzer.analyze_speed_zones(df)
    print("\nSpeed Zones:", speed_zones)

    # Generate summary
    summary = analyzer.generate_route_summary(df)
    print("\nRoute Summary:", summary)