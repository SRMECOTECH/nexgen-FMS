"""
Reverse Geocoding Service with Caching
Uses Nominatim (free) for lat/lon → address conversion
"""

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import json
import time
from pathlib import Path
from typing import Optional, Dict
import hashlib


class ReverseGeocoder:
    """Reverse geocoding with intelligent caching to minimize API calls"""

    def __init__(self, cache_file: str = "data/cache/geocoding_cache.json"):
        self.geolocator = Nominatim(user_agent="driver-analytics-v1.0")
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.request_delay = 1.0  # Nominatim requires 1 second between requests
        self.last_request_time = 0

    def _load_cache(self) -> Dict:
        """Load geocoding cache from disk"""
        if self.cache_file.exists():
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        """Save geocoding cache to disk"""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)

    def _generate_cache_key(self, lat: float, lon: float, precision: int = 3) -> str:
        """Generate cache key from coordinates (rounded to reduce API calls)"""
        # Round to 3 decimal places (~111m precision) to cache nearby points
        rounded_lat = round(lat, precision)
        rounded_lon = round(lon, precision)
        return f"{rounded_lat},{rounded_lon}"

    def _rate_limit(self):
        """Ensure we don't exceed Nominatim rate limits (1 req/sec)"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.request_delay:
            time.sleep(self.request_delay - time_since_last_request)

        self.last_request_time = time.time()

    def get_address(
            self,
            lat: float,
            lon: float,
            max_retries: int = 3
    ) -> Optional[Dict]:
        """
        Get address from coordinates with caching and retry logic

        Args:
            lat: Latitude
            lon: Longitude
            max_retries: Number of retry attempts

        Returns:
            Dictionary with address components or None
        """
        # Check cache first
        cache_key = self._generate_cache_key(lat, lon)

        if cache_key in self.cache:
            return self.cache[cache_key]

        # Make API request with retries
        for attempt in range(max_retries):
            try:
                self._rate_limit()

                location = self.geolocator.reverse(
                    (lat, lon),
                    language='en',
                    timeout=10
                )

                if location:
                    address_data = {
                        'formatted_address': location.address,
                        'city': location.raw.get('address', {}).get('city') or
                                location.raw.get('address', {}).get('town') or
                                location.raw.get('address', {}).get('village'),
                        'state': location.raw.get('address', {}).get('state'),
                        'country': location.raw.get('address', {}).get('country'),
                        'postcode': location.raw.get('address', {}).get('postcode'),
                        'road': location.raw.get('address', {}).get('road'),
                        'suburb': location.raw.get('address', {}).get('suburb'),
                        'lat': lat,
                        'lon': lon
                    }

                    # Cache the result
                    self.cache[cache_key] = address_data
                    self._save_cache()

                    return address_data

                return None

            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None

            except GeocoderServiceError as e:
                print(f"Geocoding service error: {e}")
                return None

            except Exception as e:
                print(f"Unexpected geocoding error: {e}")
                return None

        return None

    def batch_geocode(self, coordinates: list, progress_callback=None) -> list:
        """
        Geocode multiple coordinates with progress tracking

        Args:
            coordinates: List of (lat, lon) tuples
            progress_callback: Optional callback function for progress updates

        Returns:
            List of address dictionaries
        """
        results = []
        total = len(coordinates)

        for idx, (lat, lon) in enumerate(coordinates):
            address = self.get_address(lat, lon)
            results.append(address)

            if progress_callback:
                progress_callback(idx + 1, total)

        return results

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'total_cached': len(self.cache),
            'cache_file': str(self.cache_file),
            'cache_exists': self.cache_file.exists()
        }

    def clear_cache(self):
        """Clear the geocoding cache"""
        self.cache = {}
        if self.cache_file.exists():
            self.cache_file.unlink()


# Example usage
if __name__ == "__main__":
    geocoder = ReverseGeocoder()

    # Test geocoding
    result = geocoder.get_address(22.81307800, 86.23893300)
    print(f"Address: {result['formatted_address']}")
    print(f"City: {result['city']}, State: {result['state']}")

    # Check cache stats
    stats = geocoder.get_cache_stats()
    print(f"\nCache stats: {stats}")