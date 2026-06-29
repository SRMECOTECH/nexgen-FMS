import requests
from datetime import datetime
import pandas as pd
import time
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class WeatherService:
    """
    Robust Weather Service using Open-Meteo (FREE, no API key)
    Handles retries, timeouts, caching, and rate limits

    Supports:
    - Historical weather (archive API)
    - Current/forecast weather (forecast API)
    """

    def __init__(self):
        self.archive_url = "https://archive-api.open-meteo.com/v1/archive"
        self.forecast_url = "https://api.open-meteo.com/v1/forecast"

        # Reusable session with retries
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)

    @lru_cache(maxsize=1024)
    def _cached_weather(self, lat, lon, date_str, hour):
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": (
                "temperature_2m,precipitation,rain,"
                "cloud_cover,wind_speed_10m,weather_code"
            ),
            "timezone": "auto"
        }

        response = self.session.get(self.archive_url, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def get_current_weather(self, lat: float, lon: float) -> dict:
        """
        Fetch current weather for a specific latitude/longitude.

        Args:
            lat: Latitude of the location
            lon: Longitude of the location

        Returns:
            Dictionary with current weather data or None on failure
        """
        try:
            lat = round(float(lat), 4)
            lon = round(float(lon), 4)

            params = {
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "is_day,precipitation,rain,showers,snowfall,"
                    "weather_code,cloud_cover,pressure_msl,surface_pressure,"
                    "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
                ),
                "timezone": "auto"
            }

            response = self.session.get(self.forecast_url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})

            return {
                "latitude": lat,
                "longitude": lon,
                "timezone": data.get("timezone", "Unknown"),
                "temperature_c": current.get("temperature_2m"),
                "apparent_temperature_c": current.get("apparent_temperature"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "rain_mm": current.get("rain"),
                "snowfall_cm": current.get("snowfall"),
                "weather_code": current.get("weather_code"),
                "weather_description": self._interpret_weather_code(
                    current.get("weather_code", 0)
                ),
                "cloud_cover_pct": current.get("cloud_cover"),
                "pressure_hpa": current.get("pressure_msl"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "wind_gusts_kmh": current.get("wind_gusts_10m"),
                "is_day": bool(current.get("is_day")),
                "timestamp": current.get("time")
            }

        except Exception as e:
            return {"error": str(e)}

    def get_weather_forecast(self, lat: float, lon: float, days: int = 7) -> dict:
        """
        Fetch weather forecast for a specific latitude/longitude.

        Args:
            lat: Latitude of the location
            lon: Longitude of the location
            days: Number of forecast days (1-16)

        Returns:
            Dictionary with forecast data or None on failure
        """
        try:
            lat = round(float(lat), 4)
            lon = round(float(lon), 4)
            days = min(max(days, 1), 16)

            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "apparent_temperature_max,apparent_temperature_min,"
                    "sunrise,sunset,precipitation_sum,rain_sum,snowfall_sum,"
                    "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max"
                ),
                "timezone": "auto",
                "forecast_days": days
            }

            response = self.session.get(self.forecast_url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})
            dates = daily.get("time", [])

            forecast = []
            for i, date in enumerate(dates):
                forecast.append({
                    "date": date,
                    "weather_code": daily.get("weather_code", [None])[i],
                    "weather_description": self._interpret_weather_code(
                        daily.get("weather_code", [0])[i]
                    ),
                    "temp_max_c": daily.get("temperature_2m_max", [None])[i],
                    "temp_min_c": daily.get("temperature_2m_min", [None])[i],
                    "apparent_temp_max_c": daily.get("apparent_temperature_max", [None])[i],
                    "apparent_temp_min_c": daily.get("apparent_temperature_min", [None])[i],
                    "sunrise": daily.get("sunrise", [None])[i],
                    "sunset": daily.get("sunset", [None])[i],
                    "precipitation_mm": daily.get("precipitation_sum", [None])[i],
                    "rain_mm": daily.get("rain_sum", [None])[i],
                    "snowfall_cm": daily.get("snowfall_sum", [None])[i],
                    "precipitation_probability_pct": daily.get("precipitation_probability_max", [None])[i],
                    "wind_speed_max_kmh": daily.get("wind_speed_10m_max", [None])[i],
                    "wind_gusts_max_kmh": daily.get("wind_gusts_10m_max", [None])[i]
                })

            return {
                "latitude": lat,
                "longitude": lon,
                "timezone": data.get("timezone", "Unknown"),
                "forecast": forecast
            }

        except Exception as e:
            return {"error": str(e)}

    def get_historical_weather(self, lat: float, lon: float, date: datetime):
        try:
            # 🔑 Reduce API uniqueness (very important)
            lat = round(float(lat), 3)
            lon = round(float(lon), 3)
            hour = date.hour
            date_str = date.strftime("%Y-%m-%d")

            data = self._cached_weather(lat, lon, date_str, hour)

            hourly = data["hourly"]

            return {
                "temperature_c": hourly["temperature_2m"][hour],
                "rain_mm": hourly["rain"][hour],
                "wind_speed_kmh": hourly["wind_speed_10m"][hour],
                "cloud_cover_pct": hourly["cloud_cover"][hour],
                "weather_code": hourly["weather_code"][hour],
                "weather_description": self._interpret_weather_code(
                    hourly["weather_code"][hour]
                ),
                "timestamp": hourly["time"][hour]
            }

        except Exception as e:
            # Fail gracefully
            return None

    def get_weather_for_route(self, df: pd.DataFrame, sample_interval: int = 10):
        weather_rows = []

        for idx in range(0, len(df), sample_interval):
            row = df.iloc[idx]
            weather = self.get_historical_weather(
                row["latitude"],
                row["longitude"],
                pd.to_datetime(row["window_start"])
            )

            if weather:
                weather_rows.append({"index": idx, **weather})

            # ⏱️ Rate-limit protection
            time.sleep(0.2)

        if not weather_rows:
            return df

        weather_df = pd.DataFrame(weather_rows).set_index("index")
        out = df.copy()

        for col in weather_df.columns:
            out[col] = None
            out.loc[weather_df.index, col] = weather_df[col]

        out[weather_df.columns] = out[weather_df.columns].ffill()
        return out

    @staticmethod
    def _interpret_weather_code(code: int) -> str:
        weather_codes = {
            0: 'Clear sky',
            1: 'Mainly clear',
            2: 'Partly cloudy',
            3: 'Overcast',
            45: 'Fog',
            48: 'Depositing rime fog',
            51: 'Light drizzle',
            53: 'Moderate drizzle',
            55: 'Dense drizzle',
            56: 'Light freezing drizzle',
            57: 'Dense freezing drizzle',
            61: 'Slight rain',
            63: 'Moderate rain',
            65: 'Heavy rain',
            66: 'Light freezing rain',
            67: 'Heavy freezing rain',
            71: 'Slight snow',
            73: 'Moderate snow',
            75: 'Heavy snow',
            77: 'Snow grains',
            80: 'Slight rain showers',
            81: 'Moderate rain showers',
            82: 'Violent rain showers',
            85: 'Slight snow showers',
            86: 'Heavy snow showers',
            95: 'Thunderstorm',
            96: 'Thunderstorm with slight hail',
            99: 'Thunderstorm with heavy hail'
        }
        return weather_codes.get(code, f'Unknown ({code})')
