"""
Serveur Web Flask pour l'interface de surveillance de qualité de l'air
VERSION 2.2 - Responsive + Sans Authentification
Fournit une API REST et une interface web moderne pour visualiser les données en temps réel
Intègre OpenWeatherMap API pour les données météorologiques
"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
from datetime import datetime, timedelta
import json
import requests
import os
from config import config
from database import AirQualityDatabase
from ml_model import AirQualityPredictor

# ============= CONFIGURATION =============

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Créer l'application Flask
_this_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, 
            static_folder=os.path.join(_this_dir, 'static'),
            template_folder=os.path.join(_this_dir, 'templates'))
app.config['SECRET_KEY'] = config.FLASK_CONFIG['secret_key']

# Activer CORS pour permettre l'accès depuis d'autres appareils
CORS(app)

# Activer WebSocket pour les mises à jour en temps réel
socketio = SocketIO(app, cors_allowed_origins="*")

# Instances globales
db = None  # Sera initialisé dans initialize_server()
predictor = AirQualityPredictor()

# Configuration Weather API
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
WEATHER_API_URL = 'https://api.openweathermap.org/data/2.5'

# Configuration NASA API (évènements environnementaux)
NASA_API_KEY = config.NASA_CONFIG.get('api_key', '')
NASA_EONET_URL = 'https://eonet.gsfc.nasa.gov/api/v3/events'

# Cache pour les données météo (éviter trop de requêtes API)
weather_cache = {
    'data': None,
    'timestamp': None,
    'cache_duration': 600  # 10 minutes
}

# Variable pour stocker les dernières données (cache)
latest_data = {
    'sensor_data': None,
    'predictions': None,
    'alerts': [],
    'statistics': None,
    'weather': None
}


# ============= FONCTIONS UTILITAIRES =============

def _haversine_km(lat1, lon1, lat2, lon2):
    """
    Calcule la distance entre deux points GPS en kilomètres.
    Utilisé pour filtrer les évènements NASA proches de la zone mesurée.
    """
    from math import radians, sin, cos, asin, sqrt

    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None

    r = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return r * c


def get_nasa_environment_events(lat=None, lon=None, max_distance_km=1000):
    """
    Récupère des évènements environnementaux (feux de forêt, tempêtes de poussière, etc.)
    depuis l'API NASA EONET et les filtre autour de la position actuelle.

    Args:
        lat (float): Latitude de référence
        lon (float): Longitude de référence
        max_distance_km (int): Rayon de recherche en kilomètres

    Returns:
        list[dict]: Liste d'évènements pertinents près de la zone
    """
    try:
        params = {'status': 'open'}
        # Certaines APIs NASA utilisent api_key, EONET non, mais on garde la clé
        if NASA_API_KEY:
            params['api_key'] = NASA_API_KEY

        resp = requests.get(NASA_EONET_URL, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"⚠️ Erreur API NASA EONET: {resp.status_code}")
            return []

        data = resp.json()
        events = []

        for event in data.get('events', []):
            categories = [c.get('title', '').lower() for c in event.get('categories', [])]
            # On filtre sur quelques types liés à la qualité de l'air
            text_categories = " ".join(categories)
            if not any(keyword in text_categories for keyword in ['dust', 'smoke', 'fire', 'wildfire', 'sand', 'ash']):
                continue

            for geom in event.get('geometry', []):
                coords = geom.get('coordinates')
                if not coords or len(coords) < 2:
                    continue

                ev_lon, ev_lat = coords[0], coords[1]
                distance = None
                if lat is not None and lon is not None:
                    distance = _haversine_km(lat, lon, ev_lat, ev_lon)
                    if distance is None or distance > max_distance_km:
                        continue

                events.append({
                    'title': event.get('title'),
                    'categories': [c.get('title') for c in event.get('categories', [])],
                    'distance_km': round(distance, 1) if distance is not None else None,
                    'coordinates': {'lat': ev_lat, 'lon': ev_lon},
                    'link': (event.get('links') or [{}])[0].get('href'),
                    'date': geom.get('date')
                })

        # Trier par distance si disponible
        events.sort(key=lambda e: e['distance_km'] if e['distance_km'] is not None else 999999)
        return events[:10]

    except Exception as e:
        logger.error(f"✗ Erreur récupération évènements NASA: {e}")
        return []
def get_weather_data(lat=None, lon=None, city=None):
    """
    Récupère les données météo depuis OpenWeatherMap API
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
        city (str): Nom de la ville
    
    Returns:
        dict: Données météo ou None si erreur
    """
    # Vérifier le cache
    if weather_cache['data'] and weather_cache['timestamp']:
        age = (datetime.now() - weather_cache['timestamp']).seconds
        if age < weather_cache['cache_duration']:
            logger.info("☁️ Utilisation des données météo en cache")
            return weather_cache['data']
    
    if not WEATHER_API_KEY or WEATHER_API_KEY == 'your_api_key_here':
        logger.warning("⚠️ Clé API météo non configurée")
        # Retourner des données de test
        return {
            'temperature': 25.0,
            'feels_like': 24.5,
            'humidity': 60,
            'pressure': 1013,
            'description': 'Ensoleillé',
            'icon': '01d',
            'wind_speed': 15.0,
            'wind_direction': 180,
            'clouds': 10,
            'visibility': 10.0,
            'sunrise': '06:30',
            'sunset': '18:45',
            'city': 'Casablanca',
            'country': 'MA',
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        # Construire l'URL selon les paramètres disponibles
        if lat and lon:
            url = f"{WEATHER_API_URL}/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        elif city:
            url = f"{WEATHER_API_URL}/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        else:
            # Valeurs par défaut (Casablanca, Morocco)
            url = f"{WEATHER_API_URL}/weather?q=Casablanca,MA&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Formater les données
            weather_data = {
                'temperature': round(data['main']['temp'], 1),
                'feels_like': round(data['main']['feels_like'], 1),
                'humidity': data['main']['humidity'],
                'pressure': data['main']['pressure'],
                'description': data['weather'][0]['description'],
                'icon': data['weather'][0]['icon'],
                'wind_speed': round(data['wind']['speed'] * 3.6, 1),  # m/s vers km/h
                'wind_direction': data['wind'].get('deg', 0),
                'clouds': data['clouds']['all'],
                'visibility': data.get('visibility', 10000) / 1000,  # mètres vers km
                'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M'),
                'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M'),
                'city': data['name'],
                'country': data['sys']['country'],
                'timestamp': datetime.now().isoformat()
            }
            
            # Ajouter pluie si disponible
            if 'rain' in data:
                weather_data['rain_1h'] = data['rain'].get('1h', 0)
                weather_data['rain_3h'] = data['rain'].get('3h', 0)
            
            # Mettre en cache
            weather_cache['data'] = weather_data
            weather_cache['timestamp'] = datetime.now()
            
            logger.info(f"✓ Données météo récupérées: {weather_data['city']}, {weather_data['temperature']}°C")
            return weather_data
        else:
            logger.error(f"✗ Erreur API météo: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"✗ Erreur récupération météo: {e}")
        return None


def get_weather_forecast(lat=None, lon=None, city=None, days=5):
    """
    Récupère les prévisions météo sur plusieurs jours
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
        city (str): Nom de la ville
        days (int): Nombre de jours de prévisions
    
    Returns:
        dict: Prévisions météo
    """
    if not WEATHER_API_KEY or WEATHER_API_KEY == 'your_api_key_here':
        logger.warning("⚠️ Clé API météo non configurée pour prévisions")
        return {'success': False, 'error': 'API non configurée'}
    
    try:
        # API de prévisions (5 jours / 3 heures)
        if lat and lon:
            url = f"{WEATHER_API_URL}/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        elif city:
            url = f"{WEATHER_API_URL}/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        else:
            url = f"{WEATHER_API_URL}/forecast?q=Casablanca,MA&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Grouper par jour
            daily_forecasts = {}
            
            for item in data['list'][:days*8]:  # 8 prévisions par jour (toutes les 3h)
                dt = datetime.fromtimestamp(item['dt'])
                date_key = dt.strftime('%Y-%m-%d')
                
                if date_key not in daily_forecasts:
                    daily_forecasts[date_key] = {
                        'date': date_key,
                        'day_name': dt.strftime('%A'),
                        'temps': [],
                        'humidity': [],
                        'rain_prob': [],
                        'descriptions': [],
                        'icons': []
                    }
                
                daily_forecasts[date_key]['temps'].append(item['main']['temp'])
                daily_forecasts[date_key]['humidity'].append(item['main']['humidity'])
                daily_forecasts[date_key]['rain_prob'].append(item.get('pop', 0) * 100)
                daily_forecasts[date_key]['descriptions'].append(item['weather'][0]['description'])
                daily_forecasts[date_key]['icons'].append(item['weather'][0]['icon'])
            
            # Calculer les moyennes
            forecast_summary = []
            for date_key, day_data in daily_forecasts.items():
                forecast_summary.append({
                    'date': date_key,
                    'day_name': day_data['day_name'],
                    'temp_avg': round(sum(day_data['temps']) / len(day_data['temps']), 1),
                    'temp_min': round(min(day_data['temps']), 1),
                    'temp_max': round(max(day_data['temps']), 1),
                    'humidity_avg': round(sum(day_data['humidity']) / len(day_data['humidity'])),
                    'rain_chance': round(max(day_data['rain_prob'])),
                    'description': max(set(day_data['descriptions']), key=day_data['descriptions'].count),
                    'icon': max(set(day_data['icons']), key=day_data['icons'].count)
                })
            
            return {
                'success': True,
                'forecasts': forecast_summary[:days]
            }
        else:
            return {'success': False, 'error': 'API error'}
            
    except Exception as e:
        logger.error(f"✗ Erreur prévisions météo: {e}")
        return {'success': False, 'error': str(e)}


# ============= ROUTES WEB (Interface utilisateur) =============

@app.route('/')
def index():
    """
    Page d'accueil principale - Dashboard moderne
    Accès direct sans authentification
    """
    return render_template('dashbord.html', active_nav='dashboard')


@app.route('/map')
def map_view():
    """
    Vue cartographique des zones à risque
    Accès direct sans authentification
    """
    return render_template('map.html', active_nav='map')


@app.route('/predictions')
def predictions_view():
    """
    Page des prédictions ML
    Accès direct sans authentification
    """
    return render_template('predictions.html', active_nav='predictions')


@app.route('/alerts')
def alerts_view():
    """
    Page de gestion des alertes
    Accès direct sans authentification
    """
    return render_template('alerts.html', active_nav='alerts')


@app.route('/analytics')
def analytics_view():
    """
    Page d'analyses avancées sans JavaScript.
    Toutes les statistiques et analyses sont calculées côté serveur en Python.
    """
    try:
        # Période en jours pour l'analyse (7 / 30 / 90)
        days = int(request.args.get('days', 30))
        hours = days * 24

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        readings = db.get_readings_by_timerange(start_time, end_time) or []

        if not readings:
            # Pas de données en base : on réutilise la logique de /api/history pour générer un jeu de test
            readings = []
            for i in range(50):
                time_offset = timedelta(hours=hours * (i / 50))
                readings.append({
                    'timestamp': (start_time + time_offset),
                    'air_quality_ppm': 75 + (i % 30),
                    'temperature': 24 + (i % 5),
                    'humidity': 55 + (i % 15),
                    'latitude': 33.5731,
                    'longitude': -7.5898
                })

        # Listes de base
        timestamps = [
            r['timestamp'].isoformat() if hasattr(r['timestamp'], 'isoformat') else str(r['timestamp'])
            for r in readings
        ]
        air_quality = [r['air_quality_ppm'] for r in readings]
        temperature = [r.get('temperature', 25) for r in readings]
        humidity = [r.get('humidity', 60) for r in readings]

        # Statistiques principales
        if air_quality:
            avg_aqi = sum(air_quality) / len(air_quality)
            min_aqi = min(air_quality)
            max_aqi = max(air_quality)
        else:
            avg_aqi = min_aqi = max_aqi = 0

        # Distribution par niveau AQI (même logique que l'ancien JS)
        dist = [0, 0, 0, 0, 0]
        for a in air_quality:
            if a <= 50:
                dist[0] += 1
            elif a <= 100:
                dist[1] += 1
            elif a <= 150:
                dist[2] += 1
            elif a <= 200:
                dist[3] += 1
            else:
                dist[4] += 1

        # Moyenne horaire pour trouver la plage « la plus propre »
        hourly_sum = [0.0] * 24
        hourly_count = [0] * 24
        for r in readings:
            ts = r['timestamp']
            if not hasattr(ts, 'hour'):
                try:
                    ts = datetime.fromisoformat(str(ts))
                except Exception:
                    continue
            h = ts.hour
            hourly_sum[h] += r['air_quality_ppm']
            hourly_count[h] += 1

        hourly_avg = [
            (hourly_sum[i] / hourly_count[i]) if hourly_count[i] else None
            for i in range(24)
        ]

        # Meilleure plage horaire (2 heures consécutives avec AQI moyen minimal)
        best_range = "N/A"
        best_value = None
        for h in range(23):
            if hourly_avg[h] is None or hourly_avg[h + 1] is None:
                continue
            window_avg = (hourly_avg[h] + hourly_avg[h + 1]) / 2
            if best_value is None or window_avg < best_value:
                best_value = window_avg
                best_range = f"{h:02d}h - {h+1:02d}h"

        # Qualité de l'air « texte »
        quality_info = config.get_air_quality_level(avg_aqi)

        # Localisation moyenne (ou dernière position connue)
        lat = None
        lon = None
        for r in reversed(readings):
            if r.get('latitude') and r.get('longitude'):
                lat = r['latitude']
                lon = r['longitude']
                break

        # Récupérer des évènements NASA autour de la zone
        nasa_events = get_nasa_environment_events(lat=lat, lon=lon)

        summary = {
            'days': days,
            'avg_aqi': round(avg_aqi, 1),
            'min_aqi': round(min_aqi, 1),
            'max_aqi': round(max_aqi, 1),
            'total_readings': len(readings),
            'best_range': best_range,
            'quality_level': quality_info['level'],
            'quality_description': quality_info['description'],
            'distribution': dist
        }

        table_rows = list(zip(timestamps, air_quality, temperature, humidity))

        return render_template(
            'analytics.html',
            active_nav='analytics',
            summary=summary,
            table_rows=table_rows,
            nasa_events=nasa_events
        )
    except Exception as e:
        logger.error(f"Erreur affichage /analytics: {e}")
        # Si problème, rediriger vers le dashboard simple
        return render_template('dashbord.html', active_nav='dashboard')


# ============= API REST ENDPOINTS =============

@app.route('/api/current', methods=['GET'])
def get_current_data():
    """
    Récupère les données capteurs actuelles + météo
    
    Returns:
        JSON: Dernières données des capteurs et météo
    """
    try:
        readings = db.get_latest_readings(limit=1)
        weather = None
        
        if readings:
            data = readings[0]
            
            # Récupérer la météo selon la localisation
            lat = data.get('latitude')
            lon = data.get('longitude')
            
            if lat and lon:
                weather = get_weather_data(lat=lat, lon=lon)
            else:
                weather = get_weather_data()
            
            # Ajouter les informations de qualité
            quality_info = config.get_air_quality_level(data['air_quality_ppm'])
            
            response = {
                'success': True,
                'timestamp': data['timestamp'].isoformat() if hasattr(data['timestamp'], 'isoformat') else str(data['timestamp']),
                'air_quality': {
                    'value': data['air_quality_ppm'],
                    'level': quality_info['level'],
                    'color': quality_info['color'],
                    'description': quality_info['description']
                },
                'temperature': data['temperature'],
                'humidity': data['humidity'],
                'location': {
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude')
                },
                'weather': weather
            }
            
            return jsonify(response)
        else:
            # Pas de données, générer des valeurs par défaut
            weather = get_weather_data()
            return jsonify({
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'air_quality': {
                    'value': 75.0,
                    'level': 'Modéré',
                    'color': '#FFFF00',
                    'description': 'Qualité acceptable'
                },
                'temperature': 25.0,
                'humidity': 60.0,
                'location': {
                    'latitude': 33.5731,
                    'longitude': -7.5898
                },
                'weather': weather
            })
            
    except Exception as e:
        logger.error(f"Erreur API /api/current: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/weather', methods=['GET'])
def get_weather():
    """
    Récupère les données météo actuelles
    
    Query Parameters:
        lat (float): Latitude
        lon (float): Longitude
        city (str): Nom de la ville
    
    Returns:
        JSON: Données météorologiques
    """
    try:
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        city = request.args.get('city')
        
        weather_data = get_weather_data(lat=lat, lon=lon, city=city)
        
        if weather_data:
            return jsonify({
                'success': True,
                'weather': weather_data
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Impossible de récupérer les données météo'
            }), 500
            
    except Exception as e:
        logger.error(f"Erreur API /api/weather: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forecast', methods=['GET'])
def get_forecast():
    """
    Récupère les prévisions météo
    
    Query Parameters:
        days (int): Nombre de jours de prévisions (1-5)
        lat (float): Latitude
        lon (float): Longitude
    
    Returns:
        JSON: Prévisions météorologiques
    """
    try:
        days = int(request.args.get('days', 5))
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        
        forecast_data = get_weather_forecast(lat=lat, lon=lon, days=days)
        
        return jsonify(forecast_data)
        
    except Exception as e:
        logger.error(f"Erreur API /api/forecast: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    Récupère l'historique des données capteurs
    
    Query Parameters:
        hours (int): Nombre d'heures d'historique
        limit (int): Nombre maximum d'enregistrements
    
    Returns:
        JSON: Données historiques
    """
    try:
        hours = int(request.args.get('hours', 24))
        limit = int(request.args.get('limit', 100))
        
        start_time = datetime.now() - timedelta(hours=hours)
        end_time = datetime.now()
        
        readings = db.get_readings_by_timerange(start_time, end_time)
        
        if not readings:
            # Générer des données de test
            readings = []
            for i in range(min(limit, 50)):
                time_offset = timedelta(hours=hours * (i / 50))
                readings.append({
                    'timestamp': (start_time + time_offset).isoformat(),
                    'air_quality_ppm': 75 + (i % 30),
                    'temperature': 24 + (i % 5),
                    'humidity': 55 + (i % 15),
                    'latitude': 33.5731,
                    'longitude': -7.5898
                })
        
        # Formater les données pour les graphiques
        timestamps = [r['timestamp'] if isinstance(r['timestamp'], str) else r['timestamp'].isoformat() for r in readings[:limit]]
        air_quality = [r['air_quality_ppm'] for r in readings[:limit]]
        temperature = [r.get('temperature', 25) for r in readings[:limit]]
        humidity = [r.get('humidity', 60) for r in readings[:limit]]
        
        # Formater pour la carte (locations avec GPS)
        locations = []
        for r in readings[:limit]:
            if r.get('latitude') and r.get('longitude'):
                locations.append({
                    'timestamp': r['timestamp'] if isinstance(r['timestamp'], str) else r['timestamp'].isoformat(),
                    'lat': r['latitude'],
                    'lon': r['longitude'],
                    'aqi': r['air_quality_ppm']
                })
        
        response = {
            'success': True,
            'data': {
                'timestamps': timestamps,
                'air_quality': air_quality,
                'temperature': temperature,
                'humidity': humidity,
                'locations': locations
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erreur API /api/history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """
    Calcule les statistiques sur une période donnée
    
    Query Parameters:
        hours (int): Nombre d'heures pour le calcul
    
    Returns:
        JSON: Statistiques calculées
    """
    try:
        hours = int(request.args.get('hours', 24))
        
        stats = db.get_statistics(hours=hours)
        
        if not stats or not stats.get('total_readings'):
            # Retourner des stats par défaut
            stats = {
                'air_quality': {
                    'average': 75.0,
                    'min': 50.0,
                    'max': 120.0
                },
                'temperature': {
                    'average': 25.0,
                    'min': 20.0,
                    'max': 30.0
                },
                'humidity': {
                    'average': 60.0,
                    'min': 45.0,
                    'max': 75.0
                },
                'total_readings': 48
            }
        else:
            # Formater les statistiques
            stats = {
                'air_quality': {
                    'average': round(stats.get('avg_aqi', 0), 1),
                    'min': round(stats.get('min_aqi', 0), 1),
                    'max': round(stats.get('max_aqi', 0), 1)
                },
                'temperature': {
                    'average': round(stats.get('avg_temp', 0), 1),
                    'min': 0,
                    'max': 0
                },
                'humidity': {
                    'average': round(stats.get('avg_humidity', 0), 1),
                    'min': 0,
                    'max': 0
                },
                'total_readings': stats.get('total_readings', 0)
            }
        
        response = {
            'success': True,
            'statistics': stats
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erreur API /api/statistics: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    """
    Génère des prédictions ML pour les prochaines heures
    
    Query Parameters:
        hours (int): Nombre d'heures de prédiction
    
    Returns:
        JSON: Prédictions ML avec recommandations
    """
    try:
        hours = int(request.args.get('hours', 24))
        
        # Vérifier que le modèle ML est chargé
        if not predictor.model:
            logger.warning("⚠️ Modèle ML non chargé, tentative de chargement...")
            if not predictor.load_model():
                return jsonify({
                    'success': False,
                    'error': 'Modèle ML non disponible. Entraînez le modèle avec: python3 ml_model.py'
                }), 500
        
        # Récupérer les dernières données ou utiliser des valeurs par défaut
        latest_readings = db.get_latest_readings(limit=1)
        if latest_readings:
            current_data = {
                'air_quality_ppm': latest_readings[0]['air_quality_ppm'],
                'temperature': latest_readings[0]['temperature'],
                'humidity': latest_readings[0]['humidity']
            }
        else:
            current_data = {
                'air_quality_ppm': 80.0,
                'temperature': 25.0,
                'humidity': 55.0
            }
        
        # Faire les prédictions
        predictions = predictor.predict(current_data, hours_ahead=hours)
        
        # Ajouter le niveau (label) à chaque prédiction pour le frontend
        for pred in predictions:
            quality_info = config.get_air_quality_level(pred['predicted_aqi'])
            pred['level'] = quality_info['level']
        
        # Détecter les pics
        peaks = predictor.detect_pollution_peak(predictions)
        
        # Générer des recommandations (format backend)
        recommendations_raw = predictor.generate_recommendations(
            current_data['air_quality_ppm'],
            peaks
        )
        
        # Transformer en tableau { icon, title, message } pour le frontend
        recommendations = []
        if recommendations_raw.get('current_status'):
            recommendations.append({
                'icon': '📊',
                'title': 'Statut actuel',
                'message': recommendations_raw['current_status']
            })
        for action in recommendations_raw.get('actions', []):
            recommendations.append({'icon': '✓', 'title': 'Action', 'message': action})
        for advice in recommendations_raw.get('health_advice', []):
            recommendations.append({'icon': '💡', 'title': 'Conseil santé', 'message': advice})
        for period in recommendations_raw.get('time_periods_to_avoid', []):
            recommendations.append({'icon': '⏰', 'title': 'Période à éviter', 'message': period})
        
        response = {
            'success': True,
            'predictions': predictions,
            'peaks': peaks,
            'recommendations': recommendations
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erreur API /api/predictions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """
    Récupère les alertes actives
    
    Returns:
        JSON: Liste des alertes actives
    """
    try:
        alerts = db.get_active_alerts()
        formatted_alerts = []
        
        for alert in alerts:
            formatted_alerts.append({
                'id': alert['id'],
                'type': alert['alert_type'],
                'severity': alert['severity'],
                'message': alert['message'],
                'air_quality_value': alert.get('air_quality_value'),
                'location': {
                    'latitude': alert.get('latitude'),
                    'longitude': alert.get('longitude')
                },
                'created_at': alert['created_at'].isoformat() if hasattr(alert['created_at'], 'isoformat') else str(alert['created_at'])
            })
        
        response = {
            'success': True,
            'alerts': formatted_alerts,
            'count': len(formatted_alerts)
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Erreur API /api/alerts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def save_settings():
    """
    Sauvegarde les paramètres utilisateur (email pour alertes)
    SANS authentification - stockage local dans le navigateur
    
    Body JSON:
        {
            "email": "user@example.com",
            "alertsEnabled": true
        }
    
    Returns:
        JSON: Confirmation de sauvegarde
    """
    try:
        data = request.get_json()
        email = data.get('email')
        alerts_enabled = data.get('alertsEnabled', True)
        
        # Valider l'email
        if email and '@' in email and '.' in email:
            # L'email est stocké côté client dans localStorage
            # On peut optionnellement le logger ou l'utiliser pour envoyer des alertes
            
            logger.info(f"✓ Paramètres sauvegardés - Email: {email}, Alertes: {alerts_enabled}")
            
            return jsonify({
                'success': True,
                'message': 'Paramètres sauvegardés avec succès',
                'email': email,
                'alertsEnabled': alerts_enabled
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Email invalide'
            }), 400
            
    except Exception as e:
        logger.error(f"Erreur sauvegarde paramètres: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Endpoint de santé pour vérifier que l'API fonctionne
    
    Returns:
        JSON: Statut du système
    """
    return jsonify({
        'success': True,
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'version': '2.2.0',
        'features': {
            'responsive': True,
            'authentication': False,
            'database': 'connected' if db and db.connection else 'disconnected',
            'ml_model': 'loaded' if predictor.model else 'not loaded',
            'weather_api': 'configured' if WEATHER_API_KEY and WEATHER_API_KEY != 'your_api_key_here' else 'not configured'
        }
    })


# ============= WEBSOCKET EVENTS (Temps réel) =============

@socketio.on('connect')
def handle_connect():
    """Gère la connexion d'un client WebSocket"""
    logger.info("✓ Client connecté via WebSocket")
    emit('connection_response', {'status': 'connected'})


@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion d'un client"""
    logger.info("Client déconnecté")


@socketio.on('request_data')
def handle_data_request():
    """Envoie les dernières données au client qui les demande"""
    try:
        readings = db.get_latest_readings(limit=1)
        if readings:
            emit('sensor_data', readings[0])
    except Exception as e:
        logger.error(f"Erreur WebSocket request_data: {e}")


def broadcast_sensor_data(data):
    """
    Diffuse les nouvelles données capteurs à tous les clients connectés
    
    Args:
        data (dict): Données capteurs à diffuser
    """
    socketio.emit('sensor_update', data)


def broadcast_alert(alert):
    """
    Diffuse une alerte à tous les clients connectés
    
    Args:
        alert (dict): Données de l'alerte
    """
    socketio.emit('alert', alert)


# ============= INITIALISATION =============

def initialize_server():
    """Initialise le serveur et les connexions"""
    global db
    
    logger.info("=" * 60)
    logger.info("🚀 INITIALISATION DU SERVEUR AIRWATCH v2.2")
    logger.info("=" * 60)
    logger.info("")
    
    # Connexion à la base de données SQLite3
    db_path = config.DB_CONFIG.get('db_path', './data/air_quality.db')
    db = AirQualityDatabase(db_path=db_path)
    
    if db.connect():
        logger.info("✓ Connexion base de données établie")
        db.create_tables()
    else:
        logger.error("✗ Échec connexion base de données")
    
    # Charger le modèle ML
    if predictor.load_model():
        logger.info("✓ Modèle ML chargé")
    else:
        logger.warning("⚠ Modèle ML non disponible")
        logger.info("  Pour entraîner le modèle : python3 ml_model.py")
    
    # Vérifier la configuration Weather API
    if WEATHER_API_KEY and WEATHER_API_KEY != 'your_api_key_here':
        logger.info("✓ API météo configurée (OpenWeatherMap)")
    else:
        logger.warning("⚠ API météo non configurée")
        logger.info("  1. Visitez https://openweathermap.org/api")
        logger.info("  2. Créez un compte gratuit")
        logger.info("  3. Ajoutez OPENWEATHER_API_KEY dans .env")
        logger.info("  → Données météo de test seront utilisées")
    
    logger.info("")
    logger.info("✓ Serveur web initialisé avec succès")
    logger.info("")


# ============= DÉMARRAGE DU SERVEUR =============

if __name__ == '__main__':
    # Initialiser le serveur
    initialize_server()
    
    # Configuration du serveur
    host = config.FLASK_CONFIG['host']
    port = config.FLASK_CONFIG['port']
    debug = config.FLASK_CONFIG['debug']
    
    logger.info("=" * 60)
    logger.info("🌐 DÉMARRAGE DU SERVEUR")
    logger.info("=" * 60)
    logger.info(f"")
    logger.info(f"📍 URL locale:     http://localhost:{port}")
    logger.info(f"📱 URL réseau:     http://{host}:{port}")
    logger.info(f"")
    logger.info(f"📊 Dashboard:      http://localhost:{port}/")
    logger.info(f"🗺️  Carte GPS:      http://localhost:{port}/map")
    logger.info(f"🧠 Prédictions IA: http://localhost:{port}/predictions")
    logger.info(f"🔔 Alertes:        http://localhost:{port}/alerts")
    logger.info(f"")
    logger.info(f"🔌 API Health:     http://localhost:{port}/api/health")
    logger.info(f"")
    logger.info("=" * 60)
    logger.info("✨ NOUVEAUTÉS v2.2:")
    logger.info("  • Responsive Design (mobile/tablette/desktop)")
    logger.info("  • Sans authentification (accès immédiat)")
    logger.info("  • Menu hamburger sur mobile")
    logger.info("=" * 60)
    logger.info(f"")
    logger.info("🔴 Appuyez sur Ctrl+C pour arrêter le serveur")
    logger.info(f"")
    
    # Démarrer le serveur Flask avec WebSocket
    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True
    )