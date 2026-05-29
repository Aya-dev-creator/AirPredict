"""
OpenWeather Data Provider
Fetches air quality and weather data from the OpenWeatherMap API.
"""

import os
import logging
import requests
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)


class OpenWeatherDataProvider:
    """Fetches weather and air pollution data from OpenWeatherMap."""

    def __init__(self, lat=None, lon=None, city=None):
        self.api_key = os.getenv('OPENWEATHER_API_KEY', '')

        if not self.api_key or self.api_key == 'your_api_key_here':
            logger.warning("OpenWeather API key not configured — using test data")
            self.api_key = None

        self.lat = lat
        self.lon = lon
        self.city = city or config.WEATHER_DEFAULT_QUERY

        self.weather_url = 'https://api.openweathermap.org/data/2.5/weather'
        self.air_quality_url = 'https://api.openweathermap.org/data/2.5/air_pollution'

        logger.info("OpenWeather data provider ready (location: %s)", self.city)

    def fetch(self):
        """Fetch current weather and air quality snapshot."""
        try:
            if self.api_key:
                return self._fetch_from_api()
            return self._generate_test_data()
        except Exception as e:
            logger.error("Failed to fetch OpenWeather data: %s", e)
            return self._generate_test_data()

    def _fetch_from_api(self):
        if self.lat is None or self.lon is None:
            if not self._resolve_location():
                return self._generate_test_data()

        weather_data = self._get_weather()
        if not weather_data:
            return self._generate_test_data()

        air_quality_data = self._get_air_quality() or {'aqi': 2, 'components': {}}

        return {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {
                'ppm': self._aqi_to_ppm(air_quality_data.get('aqi', 2)),
                'raw_value': air_quality_data.get('aqi', 2),
                'aqi': air_quality_data.get('aqi', 2),
                'components': air_quality_data.get('components', {}),
            },
            'temperature': weather_data.get('temperature', 25),
            'humidity': weather_data.get('humidity', 60),
            'pressure': {
                'pa': weather_data.get('pressure_pa', 101325),
                'hpa': weather_data.get('pressure_hpa', 1013.25),
                'altitude': 0,
            },
            'location': {
                'latitude': self.lat,
                'longitude': self.lon,
                'fix': True,
            },
        }

    def _resolve_location(self):
        try:
            if not self.api_key:
                self.lat = config.MAP_CENTER_LAT
                self.lon = config.MAP_CENTER_LON
                return True

            geo_url = 'https://api.openweathermap.org/geo/1.0/direct'
            params = {'q': self.city, 'limit': 1, 'appid': self.api_key}
            response = requests.get(geo_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data:
                    self.lat = float(data[0]['lat'])
                    self.lon = float(data[0]['lon'])
                    logger.info(
                        "Location resolved: %s → %.4f, %.4f",
                        self.city, self.lat, self.lon,
                    )
                    return True
        except Exception as e:
            logger.warning("Location resolution failed: %s", e)

        self.lat = config.MAP_CENTER_LAT
        self.lon = config.MAP_CENTER_LON
        return True

    def _get_weather(self):
        try:
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': 'metric',
            }
            response = requests.get(self.weather_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'temperature': data['main'].get('temp', 25),
                    'humidity': data['main'].get('humidity', 60),
                    'pressure_pa': data['main'].get('pressure', 1013) * 100,
                    'pressure_hpa': data['main'].get('pressure', 1013),
                    'description': (
                        data['weather'][0].get('description', 'Unknown')
                        if data.get('weather') else 'Unknown'
                    ),
                }
        except Exception as e:
            logger.warning("Weather API request failed: %s", e)
        return None

    def _get_air_quality(self):
        try:
            params = {'lat': self.lat, 'lon': self.lon, 'appid': self.api_key}
            response = requests.get(self.air_quality_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                entry = data.get('list', [{}])[0]
                main = entry.get('main', {})
                components = entry.get('components', {})
                return {
                    'aqi': main.get('aqi', 2),
                    'components': {
                        'co': components.get('co', 0),
                        'no': components.get('no', 0),
                        'no2': components.get('no2', 0),
                        'o3': components.get('o3', 0),
                        'so2': components.get('so2', 0),
                        'pm2_5': components.get('pm2_5', 0),
                        'pm10': components.get('pm10', 0),
                        'nh3': components.get('nh3', 0),
                    },
                }
        except Exception as e:
            logger.warning("Air pollution API request failed: %s", e)
        return None

    @staticmethod
    def _aqi_to_ppm(aqi_value):
        aqi_to_ppm_map = {1: 25, 2: 75, 3: 150, 4: 275, 5: 425}
        return aqi_to_ppm_map.get(int(aqi_value), 75)

    def _generate_test_data(self):
        logger.info("Using test data (OpenWeather API unavailable)")
        return {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {
                'ppm': 75.0,
                'raw_value': 2,
                'aqi': 2,
                'components': {},
            },
            'temperature': 25.0,
            'humidity': 60,
            'pressure': {'pa': 101325, 'hpa': 1013.25, 'altitude': 0},
            'location': {
                'latitude': config.MAP_CENTER_LAT,
                'longitude': config.MAP_CENTER_LON,
                'fix': True,
            },
        }

    def cleanup(self):
        logger.info("OpenWeather data provider stopped")
