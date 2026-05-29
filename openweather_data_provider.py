"""
OpenWeather Data Provider - Remplace les capteurs physiques
Récupère les données de qualité de l'air et météo depuis OpenWeatherMap API

Ce module fournit la même interface que sensors.py mais utilise l'API OpenWeather
pour obtenir:
- Qualité de l'air (AQI, composants polluants)
- Température et humidité
- Localisation
- Pression

Cela élimine la dépendance aux capteurs physiques Raspberry Pi.
"""

import os
import logging
import requests
from datetime import datetime
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flags de compatibilité (pas de hardware physique)
HARDWARE_AVAILABLE = False


class OpenWeatherDataProvider:
    """Récupère les données depuis OpenWeatherMap API"""
    
    def __init__(self, lat=None, lon=None, city=None):
        """
        Initialise le fournisseur de données OpenWeather
        
        Args:
            lat (float): Latitude (optionnel)
            lon (float): Longitude (optionnel)
            city (str): Nom de la ville (optionnel, par défaut config.WEATHER_DEFAULT_QUERY)
        """
        self.api_key = os.getenv('OPENWEATHER_API_KEY', '')
        
        if not self.api_key or self.api_key == 'your_api_key_here':
            logger.warning("⚠ Clé API OpenWeather non configurée - Mode données de test")
            self.api_key = None
        
        # Paramètres de localisation
        self.lat = lat
        self.lon = lon
        self.city = city or config.WEATHER_DEFAULT_QUERY.split(',')[0]
        
        # URLs de l'API
        self.weather_url = 'https://api.openweathermap.org/data/2.5/weather'
        self.air_quality_url = 'https://api.openweathermap.org/data/3.0/air_pollution'
        
        logger.info("✓ OpenWeather Data Provider initialisé")
    
    def read_all_sensors(self):
        """
        Récupère toutes les données (émule la méthode sensors.py)
        
        Returns:
            dict: Données formatées exactement comme sensors.py
        """
        try:
            if self.api_key:
                return self._fetch_from_api()
            else:
                return self._generate_test_data()
        except Exception as e:
            logger.error(f"✗ Erreur récupération données: {e}")
            return self._generate_test_data()
    
    def _fetch_from_api(self):
        """Récupère les données réelles depuis OpenWeather API"""
        try:
            # Déterminer les coordonnées
            if self.lat is None or self.lon is None:
                if not self._resolve_location():
                    return self._generate_test_data()
            
            # Récupérer les données météo
            weather_data = self._get_weather()
            if not weather_data:
                return self._generate_test_data()
            
            # Récupérer la qualité de l'air
            air_quality_data = self._get_air_quality()
            if not air_quality_data:
                air_quality_data = {'aqi': 2, 'components': {}}  # Données par défaut
            
            # Formater exactement comme sensors.py
            return {
                'timestamp': datetime.now().isoformat(),
                'air_quality': {
                    'ppm': self._aqi_to_ppm(air_quality_data.get('aqi', 2)),
                    'raw_value': air_quality_data.get('aqi', 2),
                    'aqi': air_quality_data.get('aqi', 2),
                    'components': air_quality_data.get('components', {})
                },
                'temperature': weather_data.get('temperature', 25),
                'humidity': weather_data.get('humidity', 60),
                'pressure': {
                    'pa': weather_data.get('pressure_pa', 101325),
                    'hpa': weather_data.get('pressure_hpa', 1013.25),
                    'altitude': 0
                },
                'location': {
                    'latitude': self.lat,
                    'longitude': self.lon,
                    'fix': True
                }
            }
        except Exception as e:
            logger.error(f"✗ Erreur API OpenWeather: {e}")
            return self._generate_test_data()
    
    def _resolve_location(self):
        """Résout la localisation par nom de ville"""
        try:
            if not self.api_key:
                # Utiliser les coordonnées par défaut
                self.lat = config.MAP_CENTER_LAT
                self.lon = config.MAP_CENTER_LNG
                return True
            
            # Utiliser l'API de géocodage
            geo_url = 'https://api.openweathermap.org/geo/1.0/direct'
            params = {
                'q': self.city,
                'limit': 1,
                'appid': self.api_key
            }
            
            response = requests.get(geo_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data:
                    self.lat = float(data[0]['lat'])
                    self.lon = float(data[0]['lon'])
                    logger.info(f"✓ Localisation résolvue: {self.city} → {self.lat:.4f}, {self.lon:.4f}")
                    return True
        except Exception as e:
            logger.warning(f"⚠ Erreur résolution localisation: {e}")
        
        # Fallback vers les coordonnées par défaut
        self.lat = config.MAP_CENTER_LAT
        self.lon = config.MAP_CENTER_LNG
        return True
    
    def _get_weather(self):
        """Récupère les données météo"""
        try:
            if not self.api_key:
                return None
            
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(self.weather_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'temperature': data['main'].get('temp', 25),
                    'humidity': data['main'].get('humidity', 60),
                    'pressure_pa': data['main'].get('pressure', 1013) * 100,
                    'pressure_hpa': data['main'].get('pressure', 1013),
                    'description': data['weather'][0].get('description', 'Inconnu') if data.get('weather') else 'Inconnu'
                }
        except Exception as e:
            logger.warning(f"⚠ Erreur récupération météo: {e}")
        
        return None
    
    def _get_air_quality(self):
        """Récupère les données de qualité de l'air"""
        try:
            if not self.api_key:
                return None
            
            # OpenWeatherMap API Air Pollution (v3.0)
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key
            }
            
            # Utiliser l'API v2.5 si v3.0 n'est pas disponible
            air_quality_url_v2 = 'https://api.openweathermap.org/data/2.5/air_pollution'
            response = requests.get(air_quality_url_v2, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                main = data.get('list', [{}])[0].get('main', {})
                components = data.get('list', [{}])[0].get('components', {})
                
                return {
                    'aqi': main.get('aqi', 2),  # 1=Excellent, 2=Bon, 3=Modéré, 4=Mauvais, 5=Très mauvais
                    'components': {
                        'co': components.get('co', 0),  # CO en µg/m³
                        'no': components.get('no', 0),  # NO
                        'no2': components.get('no2', 0),  # NO₂
                        'o3': components.get('o3', 0),  # O₃
                        'so2': components.get('so2', 0),  # SO₂
                        'pm2_5': components.get('pm2_5', 0),  # PM 2.5
                        'pm10': components.get('pm10', 0),  # PM 10
                        'nh3': components.get('nh3', 0)  # NH₃
                    }
                }
        except Exception as e:
            logger.warning(f"⚠ Erreur récupération qualité de l'air: {e}")
        
        return None
    
    def _aqi_to_ppm(self, aqi_value):
        """Convertit l'indice AQI en valeur PPM approximative pour compatibilité"""
        # Conversion approximative de l'AQI (1-5) en PPM (0-500)
        # AQI 1 (Excellent) → 0-50 PPM
        # AQI 2 (Bon) → 50-100 PPM
        # AQI 3 (Modéré) → 100-200 PPM
        # AQI 4 (Mauvais) → 200-350 PPM
        # AQI 5 (Très mauvais) → 350-500 PPM
        
        aqi_to_ppm_map = {
            1: 25,    # Excellent
            2: 75,    # Bon
            3: 150,   # Modéré
            4: 275,   # Mauvais
            5: 425    # Très mauvais
        }
        
        return aqi_to_ppm_map.get(int(aqi_value), 75)
    
    def _generate_test_data(self):
        """Génère des données de test si l'API ne fonctionne pas"""
        logger.info("📊 Mode données de test activé")
        return {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {
                'ppm': 75.0,
                'raw_value': 2,
                'aqi': 2,
                'components': {
                    'co': 500,
                    'no': 50,
                    'no2': 100,
                    'o3': 80,
                    'so2': 50,
                    'pm2_5': 15,
                    'pm10': 35,
                    'nh3': 10
                }
            },
            'temperature': 25.0,
            'humidity': 60,
            'pressure': {
                'pa': 101325,
                'hpa': 1013.25,
                'altitude': 0
            },
            'location': {
                'latitude': config.MAP_CENTER_LAT,
                'longitude': config.MAP_CENTER_LNG,
                'fix': True
            }
        }
    
    def cleanup(self):
        """Nettoyage (compatibilité avec sensors.py)"""
        logger.info("✓ OpenWeather Data Provider arrêté")


class SensorManager(OpenWeatherDataProvider):
    """Classe de compatibilité pour remplacer sensors.SensorManager"""
    
    def __init__(self, mq135_pin=17, dht11_pin=4, gps_enabled=True, bmp180_enabled=True, **kwargs):
        """Initialise le gestionnaire de données (compatible avec l'ancien SensorManager)"""
        # Ignorer les paramètres des capteurs physiques
        super().__init__()
        logger.info("✓ Mode OpenWeather activé (capteurs physiques remplacés par l'API)")
