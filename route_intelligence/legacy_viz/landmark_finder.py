"""
Landmark and Point of Interest (POI) Finder
Uses Overpass API (OpenStreetMap) to find nearby landmarks
"""

import overpy
import requests
from typing import List, Dict, Optional
import time
from functools import lru_cache


class LandmarkFinder:
    """Find landmarks and POIs near coordinates using OpenStreetMap"""

    # Common POI categories for drivers
    POI_CATEGORIES = {
        'fuel_stations': {
            'amenity': 'fuel',
            'icon': '⛽',
            'label': 'Fuel Station'
        },
        'restaurants': {
            'amenity': 'restaurant',
            'icon': '🍽️',
            'label': 'Restaurant'
        },
        'hotels': {
            'tourism': 'hotel',
            'icon': '🏨',
            'label': 'Hotel'
        },
        'parking': {
            'amenity': 'parking',
            'icon': '🅿️',
            'label': 'Parking'
        },
        'rest_areas': {
            'highway': 'rest_area',
            'icon': '🛑',
            'label': 'Rest Area'
        },
        'hospitals': {
            'amenity': 'hospital',
            'icon': '🏥',
            'label': 'Hospital'
        },
        'police': {
            'amenity': 'police',
            'icon': '👮',
            'label': 'Police Station'
        },
        'workshops': {
            'shop': 'car_repair',
            'icon': '🔧',
            'label': 'Workshop'
        }
    }

    def __init__(self):
        self.api = overpy.Overpass()
        self.request_delay = 1.0  # Be nice to OSM servers
        self.last_request_time = 0

    def _rate_limit(self):
        """Rate limiting for API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)

        self.last_request_time = time.time()

    def find_nearby_pois(
            self,
            lat: float,
            lon: float,
            radius_meters: int = 500,
            categories: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Find POIs near a coordinate

        Args:
            lat: Latitude
            lon: Longitude
            radius_meters: Search radius in meters
            categories: List of category keys (default: all fuel stations and rest areas)

        Returns:
            List of POI dictionaries
        """
        if categories is None:
            categories = ['fuel_stations', 'rest_areas', 'restaurants']

        all_pois = []

        for category_key in categories:
            if category_key not in self.POI_CATEGORIES:
                continue

            category = self.POI_CATEGORIES[category_key]
            pois = self._query_overpass(lat, lon, radius_meters, category)

            all_pois.extend(pois)

        return all_pois

    def _query_overpass(
            self,
            lat: float,
            lon: float,
            radius: int,
            category: Dict
    ) -> List[Dict]:
        """Query Overpass API for specific POI category"""
        try:
            self._rate_limit()

            # Build Overpass query
            tag_key = list(category.keys())[0] if category.keys() else 'amenity'
            tag_value = category.get(tag_key, '')

            if tag_key in ['amenity', 'tourism', 'highway', 'shop']:
                query = f"""
                [out:json][timeout:25];
                (
                  node["{tag_key}"="{tag_value}"](around:{radius},{lat},{lon});
                  way["{tag_key}"="{tag_value}"](around:{radius},{lat},{lon});
                );
                out center;
                """

                result = self.api.query(query)

                pois = []

                # Process nodes
                for node in result.nodes:
                    pois.append({
                        'name': node.tags.get('name', 'Unnamed'),
                        'category': category['label'],
                        'icon': category['icon'],
                        'lat': float(node.lat),
                        'lon': float(node.lon),
                        'distance_km': self._calculate_distance(
                            lat, lon, float(node.lat), float(node.lon)
                        ),
                        'tags': dict(node.tags)
                    })

                # Process ways (buildings)
                for way in result.ways:
                    if hasattr(way, 'center_lat') and hasattr(way, 'center_lon'):
                        pois.append({
                            'name': way.tags.get('name', 'Unnamed'),
                            'category': category['label'],
                            'icon': category['icon'],
                            'lat': float(way.center_lat),
                            'lon': float(way.center_lon),
                            'distance_km': self._calculate_distance(
                                lat, lon, float(way.center_lat), float(way.center_lon)
                            ),
                            'tags': dict(way.tags)
                        })

                return sorted(pois, key=lambda x: x['distance_km'])

        except Exception as e:
            print(f"Error querying Overpass API: {e}")
            return []

        return []

    @staticmethod
    def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in km (Haversine formula)"""
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def find_route_landmarks(
            self,
            waypoints: List[tuple],
            radius_meters: int = 1000
    ) -> Dict:
        """
        Find landmarks along a route (list of waypoints)

        Args:
            waypoints: List of (lat, lon) tuples
            radius_meters: Search radius

        Returns:
            Dictionary with landmarks by waypoint
        """
        route_landmarks = {}

        # Sample waypoints to avoid too many API calls
        sample_interval = max(1, len(waypoints) // 10)  # Max 10 samples
        sampled_waypoints = waypoints[::sample_interval]

        for idx, (lat, lon) in enumerate(sampled_waypoints):
            pois = self.find_nearby_pois(lat, lon, radius_meters)

            if pois:
                route_landmarks[f"waypoint_{idx}"] = {
                    'lat': lat,
                    'lon': lon,
                    'pois': pois[:5]  # Top 5 nearest POIs
                }

        return route_landmarks

    def get_nearest_poi(
            self,
            lat: float,
            lon: float,
            category: str = 'fuel_stations',
            max_distance_km: float = 10.0
    ) -> Optional[Dict]:
        """
        Get the nearest POI of a specific category

        Args:
            lat: Latitude
            lon: Longitude
            category: POI category key
            max_distance_km: Maximum search distance

        Returns:
            Nearest POI dictionary or None
        """
        radius_meters = int(max_distance_km * 1000)
        pois = self.find_nearby_pois(lat, lon, radius_meters, [category])

        if pois and pois[0]['distance_km'] <= max_distance_km:
            return pois[0]

        return None


# Example usage
if __name__ == "__main__":
    finder = LandmarkFinder()

    # Find fuel stations near a coordinate
    lat, lon = 22.81307800, 86.23893300

    print(f"Searching near ({lat}, {lon})...\n")

    pois = finder.find_nearby_pois(lat, lon, radius_meters=2000,
                                   categories=['fuel_stations', 'restaurants'])

    for poi in pois[:5]:
        print(f"{poi['icon']} {poi['name']}")
        print(f"   Category: {poi['category']}")
        print(f"   Distance: {poi['distance_km']:.2f} km")
        print()