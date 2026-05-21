"""
Serveur Web Flask pour l'interface de surveillance de qualité de l'air
VERSION 2.2 - Responsive + Sans Authentification
Fournit une API REST et une interface web moderne pour visualiser les données en temps réel
Intègre OpenWeatherMap API pour les données météorologiques
"""
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import logging
from datetime import datetime, timedelta
import json
import requests
import os
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
from config import config
from database import AirQualityDatabase
from ml_model import AirQualityPredictor

# Identifiant affiché dans le pied de page et /api/health (vérifie que le bon code est déployé)
AIRWATCH_BUILD = '2026-05-13c'

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

# CORS désactivé (No-JS)

# Instances globales
db = None  # Sera initialisé dans initialize_server()
predictor = AirQualityPredictor()

# Configuration Weather API
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
WEATHER_API_URL = 'https://api.openweathermap.org/data/2.5'

# Configuration NASA API (évènements environnementaux)
NASA_API_KEY = config.NASA_CONFIG.get('api_key', '')
NASA_EONET_URL = 'https://eonet.gsfc.nasa.gov/api/v3/events'

# Configuration NewsData API (clé uniquement via .env — ne pas commiter de clé)
NEWSDATA_API_KEY = os.getenv('NEWSDATA_API_KEY', '')
NEWSDATA_SOURCES_URL = 'https://newsdata.io/api/1/sources'
NEWSDATA_NEWS_URL = 'https://newsdata.io/api/1/latest'

# Flux RSS publics (sans clé API) — liens réels vers les articles
RSS_FALLBACK_FEEDS = [
    'https://www.francetvinfo.fr/environnement.rss',
    'https://www.actu-environnement.com/ae/news/news_rss.xml',
]

# Cache pour les données météo (éviter trop de requêtes API)
weather_cache = {
    'data': None,
    'timestamp': None,
    'cache_duration': 600  # 10 minutes
}

# Cache for NASA events (environmental events from NASA EONET)
nasa_events_cache = {
    'data': None,
    'timestamp': None,
    'key': None,
    'cache_duration': 6 * 60 * 60  # 6 hours in seconds
}

# Cache for news articles
news_cache = {
    'data': None,
    'timestamp': None,
    'key': None,
    'cache_duration': 30 * 60  # 30 minutes in seconds
}

# Cache for weather forecast
forecast_cache = {
    'data': None,
    'timestamp': None,
    'key': None,
    'cache_duration': 1 * 60 * 60  # 1 hour in seconds
}

# Jours de la semaine en français (prévisions météo)
WEEKDAYS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

# Exemples d’articles (affichés si l’API actualités ne renvoie rien)
DEMO_NEWS_ARTICLES = [
    {'tag': 'Environnement', 'tag_style': 'env', 'title': 'Qualité de l’air : les bons réflexes à Casablanca',
     'meta': 'Le Matin • 22 mai 2024', 'summary': 'Réduction des émissions et mobilité douce au centre des recommandations.',
     'url': 'https://lematin.ma/express/2024/environnement'},
    {'tag': 'Politique', 'tag_style': 'pol', 'title': 'Nouvelle stratégie nationale sur le climat',
     'meta': 'TelQuel • 20 mai 2024', 'summary': 'Les objectifs de neutralité carbone sont précisés pour les prochaines années.',
     'url': 'https://telquel.ma/categorie/environnement'},
    {'tag': 'Santé', 'tag_style': 'health', 'title': 'Pollution et santé respiratoire : ce qu’il faut savoir',
     'meta': 'Médias24 • 18 mai 2024', 'summary': 'Les médecins rappellent les précautions pour les personnes sensibles.',
     'url': 'https://www.medias24.com/sante/'},
    {'tag': 'Lifestyle', 'tag_style': 'life', 'title': 'Jardins urbains et îlots de fraîcheur',
     'meta': 'Hespress • 15 mai 2024', 'summary': 'Comment les villes marocaines intègrent le végétal pour limiter la chaleur.',
     'url': 'https://fr.hespress.com/tag/environnement'},
    {'tag': 'Climatologie', 'tag_style': 'cli', 'title': 'Vagues de chaleur : tendances pour l’été',
     'meta': 'Le Matin • 12 mai 2024', 'summary': 'Analyse des modèles climatiques pour la région méditerranéenne.',
     'url': 'https://lematin.ma/express/2024/environnement'},
]

DEMO_NEWS_SOURCES = [
    {'name': 'Le Matin', 'sub': 'Maroc — FR', 'tag': 'Environnement', 'tag_style': 'env'},
    {'name': 'TelQuel', 'sub': 'Maroc — FR', 'tag': 'Politique', 'tag_style': 'pol'},
    {'name': 'Médias24', 'sub': 'Maroc — FR', 'tag': 'Santé', 'tag_style': 'health'},
    {'name': 'Hespress', 'sub': 'Maroc — FR', 'tag': 'Lifestyle', 'tag_style': 'life'},
]

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
    global nasa_events_cache
    # Create a cache key based on the parameters
    key = (lat, lon, max_distance_km)
    now = datetime.now().timestamp()

    # Check if we have a valid cache
    if nasa_events_cache['data'] is not None and nasa_events_cache['timestamp'] is not None:
        if nasa_events_cache['key'] == key and (now - nasa_events_cache['timestamp']) < nasa_events_cache['cache_duration']:
            return nasa_events_cache['data']

    # Otherwise, fetch new data
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
        events = events[:10]

        # Update cache
        nasa_events_cache['key'] = key
        nasa_events_cache['data'] = events
        nasa_events_cache['timestamp'] = now

        return events

    except Exception as e:
        logger.error(f"✗ Erreur récupération évènements NASA: {e}")
        return []


def get_news_sources(country='ma', language='fr', category='lifestyle,health,environment', prioritydomain='medium'):
    """
    Récupère les sources d'actualité depuis l'API NewsData.io.

    Args:
        country (str): Code pays
        language (str): Langue des sources
        category (str): Catégories séparées par des virgules
        prioritydomain (str): Priorité du domaine

    Returns:
        dict: Réponse JSON de NewsData.io
    """
    try:
        if not NEWSDATA_API_KEY:
            return {}
        params = {
            'apikey': NEWSDATA_API_KEY,
            'country': country,
            'language': language,
            'category': category,
            'prioritydomain': prioritydomain
        }
        response = requests.get(NEWSDATA_SOURCES_URL, params=params, timeout=15)
        if response.status_code != 200:
            logger.warning(f"⚠️ Erreur API NewsData: {response.status_code}")
            return {}

        data = response.json()
        logger.info(f"✓ Données NewsData récupérées: {len(data.get('results', []))} sources")
        return data
    except Exception as e:
        logger.error(f"✗ Erreur récupération sources NewsData: {e}")
        return {}


def _fmt_news_meta(item):
    src = item.get('source_id') or item.get('source_name') or ''
    raw_date = item.get('pubDate') or item.get('pubdate') or ''
    if raw_date and len(raw_date) > 16:
        raw_date = raw_date[:16].replace('T', ' ')
    parts = [p for p in (src, raw_date) if p]
    return ' • '.join(parts) if parts else 'Actualité'


def _category_to_tag_style(cat):
    c = (str(cat) if cat is not None else '').lower()
    if 'health' in c or 'sant' in c:
        return 'health', 'Santé'
    if 'politic' in c or 'polit' in c:
        return 'pol', 'Politique'
    if 'environment' in c or 'environ' in c:
        return 'env', 'Environnement'
    if 'science' in c or 'tech' in c:
        return 'cli', 'Science'
    label = (str(cat) if cat else 'Actualités').replace('_', ' ').strip() or 'Actualités'
    return 'life', label[:40]


def get_news_articles(country='ma', language='fr', category='environment,health,lifestyle,science'):
    """Articles récents (endpoint /news) avec liens vers les sources."""
    global news_cache
    if not NEWSDATA_API_KEY:
        return []
    # Create a cache key based on the parameters
    key = (country, language, category)
    now = datetime.now().timestamp()

    # Check if we have a valid cache
    if news_cache['data'] is not None and news_cache['timestamp'] is not None:
        if news_cache['key'] == key and (now - news_cache['timestamp']) < news_cache['cache_duration']:
            return news_cache['data']

    # Otherwise, fetch new data
    try:
        params = {
            'apikey': NEWSDATA_API_KEY,
            'country': country,
            'language': language,
            'category': category,
        }
        response = requests.get(NEWSDATA_NEWS_URL, params=params, timeout=20)
        if response.status_code != 200:
            logger.warning(f"⚠️ Erreur API NewsData articles: {response.status_code}")
            return []
        data = response.json()
        rows = data.get('results') or []
        out = []
        for row in rows:
            link = row.get('link') or row.get('url') or row.get('source_url') or row.get('article_url')
            title = (row.get('title') or '').strip()
            if not link or not title:
                continue
            desc = (row.get('description') or row.get('content') or '')[:500]
            cat = row.get('category')
            if isinstance(cat, list) and cat:
                cat = cat[0]
            tag_style, tag_label = _category_to_tag_style(cat)
            out.append({
                'tag': tag_label,
                'tag_style': tag_style,
                'title': title,
                'meta': _fmt_news_meta(row),
                'summary': (desc or '').strip() or "Voir l'article sur le site de la source.",
                'url': link,
            })
        logger.info(f"✓ NewsData articles: {len(out)}")
        out = out[:20]

        # Update cache
        news_cache['key'] = key
        news_cache['data'] = out
        news_cache['timestamp'] = now

        return out
    except Exception as e:
        logger.error(f"✗ Erreur récupération articles NewsData: {e}")
        return []


def fetch_rss_environment_news(max_items=14):
    """Articles avec liens via flux RSS (requests + SSL — plus fiable que urllib sur Raspberry Pi)."""
    collected = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; AirWatch/2.2; +https://airwatch.local)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    # Désactiver la vérification SSL sur Raspberry Pi si nécessaire
    verify_ssl = not os.path.exists('/etc/os-release')
    
    for feed_url in RSS_FALLBACK_FEEDS:
        if len(collected) >= max_items:
            break
        try:
            # Essayer avec vérification SSL d'abord, puis sans sur Raspberry Pi
            try:
                r = requests.get(feed_url, headers=headers, timeout=22, verify=verify_ssl)
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
                logger.warning(f'Erreur SSL pour {feed_url}, nouvelle tentative sans vérification...')
                r = requests.get(feed_url, headers=headers, timeout=22, verify=False)
            
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            logger.warning(f'⚠ Flux RSS indisponible {feed_url}: {e}')
            continue

        for item in root.iter():
            if not item.tag.endswith('item') or len(collected) >= max_items:
                continue
            title = link = desc = ''
            for child in item:
                tag = child.tag.split('}')[-1].lower()
                if tag == 'title' and child.text:
                    title = child.text.strip()
                elif tag == 'link':
                    link = (child.text or '').strip()
                    if not link and child.attrib.get('href'):
                        link = child.attrib.get('href', '').strip()
                elif tag in ('description', 'summary') and child.text:
                    txt = child.text.strip()
                    if len(txt) > 400:
                        txt = txt[:400] + '…'
                    desc = txt
            if title and link:
                collected.append({
                    'tag': 'Environnement',
                    'tag_style': 'env',
                    'title': title,
                    'meta': 'Flux RSS',
                    'summary': desc or 'Article externe.',
                    'url': link,
                })
            elif title and not link:
                # Fallback: créer un lien de recherche si l'article n'en a pas
                collected.append({
                    'tag': 'Environnement',
                    'tag_style': 'env',
                    'title': title,
                    'meta': 'Flux RSS',
                    'summary': desc or 'Article externe.',
                    'url': 'https://www.google.com/search?q=' + urllib.parse.quote_plus(title),
                })
    if collected:
        logger.info(f'✓ RSS: {len(collected)} articles avec liens')
    return collected[:max_items]


def merge_news_article_lists(max_total, *lists):
    """Fusionne plusieurs listes d’articles sans doublon d’URL (ordre conservé)."""
    seen = set()
    out = []
    for lst in lists:
        for a in lst or []:
            if not isinstance(a, dict):
                continue
            u = (a.get('url') or '').strip()
            key = u if u else f"t:{a.get('title','')}"
            if key in seen:
                continue
            seen.add(key)
            out.append(ensure_article_has_link(dict(a)))
            if len(out) >= max_total:
                return out
    return out


def ensure_article_has_link(article):
    """Garantit une URL cliquable (recherche titre en dernier recours)."""
    a = dict(article)
    u = (a.get('url') or '').strip()
    if u:
        return a
    title = (a.get('title') or '').strip()
    if title:
        a['url'] = 'https://www.google.com/search?q=' + urllib.parse.quote_plus(title)
        a['meta'] = (a.get('meta') or '') + (' • ' if a.get('meta') else '') + 'Recherche web'
    return a


def normalize_news_source_card(s):
    """Formate une entrée API « sources » pour le template HTML."""
    if not isinstance(s, dict):
        return None
    name = s.get('name') or s.get('id') or 'Source'
    country = s.get('country')
    if isinstance(country, (list, tuple)):
        country_txt = ', '.join(str(c).upper() for c in country[:8])
        if len(country) > 8:
            country_txt += '…'
    else:
        country_txt = str(country or 'MA').upper()
    lang = s.get('language')
    if isinstance(lang, (list, tuple)):
        lang_txt = ', '.join(str(x).upper() for x in lang[:5])
    else:
        lang_txt = str(lang or 'fr').upper()
    sub = f"{country_txt} — {lang_txt}"
    cat = s.get('category')
    if isinstance(cat, (list, tuple)) and cat:
        tag_txt = str(cat[0])
    else:
        tag_txt = str(cat or 'Info')
    tag_style, tag_label = _category_to_tag_style(tag_txt)
    return {
        'name': name,
        'sub': sub,
        'tag': tag_label,
        'tag_style': tag_style,
    }


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
            'city': config.WEATHER_DEFAULT_QUERY.split(',')[0].replace('+', ' '),
            'country': 'MA',
            'latitude': config.MAP_CENTER_LAT,
            'longitude': config.MAP_CENTER_LON,
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        # Construire l'URL selon les paramètres disponibles
        default_q = config.WEATHER_DEFAULT_QUERY
        if lat and lon:
            url = f"{WEATHER_API_URL}/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        elif city:
            url = f"{WEATHER_API_URL}/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        else:
            url = f"{WEATHER_API_URL}/weather?q={default_q}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        
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
                'latitude': data['coord']['lat'],
                'longitude': data['coord']['lon'],
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
            url = f"{WEATHER_API_URL}/forecast?q={config.WEATHER_DEFAULT_QUERY}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
        
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
                        'weekday': dt.weekday(),
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
                wd = day_data.get('weekday', 0)
                forecast_summary.append({
                    'date': date_key,
                    'day_name': day_data['day_name'],
                    'day_name_fr': WEEKDAYS_FR[wd % 7],
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
    Page d'accueil principale - Dashboard moderne 100% No-JS
    Toutes les données sont injectées côté serveur
    """
    # 1. Données Météo Actuelles
    weather = get_weather_data()
    
    # 2. Dernières données capteurs
    latest_readings = db.get_latest_readings(limit=1)
    current_sensor = latest_readings[0] if latest_readings else None
    
    # 3. Statistiques 24h
    stats = db.get_statistics(hours=24)
    
    # 4. Prévisions météo (5 jours)
    forecast_data = get_weather_forecast(days=5)
    forecasts = forecast_data.get('forecasts', []) if forecast_data.get('success') else []
    
    # 5. Alertes actives
    alerts = db.get_recent_alerts(limit=5)
    
    # 6. Infos de Qualité d'Air
    aqi_value = current_sensor['air_quality_ppm'] if current_sensor else 0
    aqi_info = config.get_air_quality_level(aqi_value)
    
    now_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    return render_template(
        'dashboard.html',
        active_nav='dashboard',
        weather=weather,
        sensor=current_sensor,
        stats=stats,
        forecasts=forecasts,
        alerts=alerts,
        aqi=aqi_info,
        aqi_value=round(aqi_value, 1),
        now_str=now_str,
    )


@app.route('/map')
def map_view():
    """Vue cartographique (Version No-JS) - Centré sur Casablanca par défaut"""
    # Récupérer les dernières données avec coordonnées GPS
    readings = db.get_latest_readings(limit=20)
    locations = []
    for reading in readings:
        if reading.get('latitude') and reading.get('longitude'):
            try:
                locations.append({
                    **reading,
                    'latitude': float(reading['latitude']),
                    'longitude': float(reading['longitude'])
                })
            except (TypeError, ValueError):
                continue
    
    # Si aucune donnée GPS n'est dispo, utiliser la position de Casablanca (défaut)
    if not locations:
        weather = get_weather_data()
        if weather and 'latitude' in weather and 'longitude' in weather:
            # Vérifier que c'est bien Casablanca (ou proche)
            weather_lat = float(weather.get('latitude', config.MAP_CENTER_LAT))
            weather_lon = float(weather.get('longitude', config.MAP_CENTER_LON))
            distance = _haversine_km(weather_lat, weather_lon, float(config.MAP_CENTER_LAT), float(config.MAP_CENTER_LON))
            # Si la météo est trop loin, utiliser Casablanca
            if distance is None or distance > config.MAP_GPS_MAX_DISTANCE_KM:
                weather_lat = float(config.MAP_CENTER_LAT)
                weather_lon = float(config.MAP_CENTER_LON)
            locations = [{
                'latitude': weather_lat,
                'longitude': weather_lon,
                'timestamp': 'Position via Météo (Casablanca)',
                'air_quality_ppm': 95,
                'air_quality_color': '#fbbf24',
                'is_fallback': True
            }]
        else:
            # Fallback à Casablanca
            locations = [{
                'latitude': float(config.MAP_CENTER_LAT),
                'longitude': float(config.MAP_CENTER_LON),
                'timestamp': 'Position Casablanca (défaut)',
                'air_quality_ppm': 95,
                'air_quality_color': '#fbbf24',
                'is_fallback': True
            }]
    
    latest_one = db.get_latest_readings(limit=1)
    current_sensor = latest_one[0] if latest_one else None

    loc = locations[0]

    # Centre carte : TOUJOURS Casablanca (33.5731, -7.5898) par défaut
    # GPS et météo sont affichés mais ne changent pas le centre de la carte
    weather = get_weather_data()
    home_lat = float(config.MAP_CENTER_LAT)  # Casablanca
    home_lon = float(config.MAP_CENTER_LON)  # Casablanca
    city_name = config.WEATHER_DEFAULT_QUERY.split(',')[0].replace('+', ' ')
    
    # Toujours utiliser Casablanca comme centre de carte
    map_lat, map_lon = home_lat, home_lon

    sensor_gps = None
    if current_sensor and current_sensor.get('latitude') and current_sensor.get('longitude'):
        try:
            sensor_gps = (
                float(current_sensor['latitude']),
                float(current_sensor['longitude']),
            )
        except (TypeError, ValueError):
            sensor_gps = None

    dist_sensor_home = None
    if sensor_gps:
        dist_sensor_home = _haversine_km(sensor_gps[0], sensor_gps[1], home_lat, home_lon)

    map_extra = {
        'city_name': city_name,
        'ref_lat': home_lat,
        'ref_lon': home_lon,
        'sensor_lat': sensor_gps[0] if sensor_gps else None,
        'sensor_lon': sensor_gps[1] if sensor_gps else None,
        'gps_ignored': bool(
            sensor_gps
            and not getattr(config, 'MAP_FOLLOW_GPS', False)
            and (
                dist_sensor_home is None
                or dist_sensor_home > float(getattr(config, 'MAP_GPS_MAX_DISTANCE_KM', 320))
            )
        ),
        'sensor_distance_km': round(dist_sensor_home, 1) if dist_sensor_home is not None else None,
    }

    ppm_val = None
    if current_sensor and current_sensor.get('air_quality_ppm') is not None:
        try:
            ppm_val = float(current_sensor['air_quality_ppm'])
        except (TypeError, ValueError):
            ppm_val = None
    if ppm_val is None:
        try:
            v = loc.get('air_quality_ppm')
            ppm_val = float(v) if v not in (None, '--', '') else 96.5
        except (TypeError, ValueError):
            ppm_val = 96.5

    aqi_row = config.get_air_quality_level(ppm_val)
    try:
        t_val = float(current_sensor.get('temperature')) if current_sensor and current_sensor.get('temperature') is not None else 28.3
    except (TypeError, ValueError):
        t_val = 28.3
    try:
        h_val = float(current_sensor.get('humidity')) if current_sensor and current_sensor.get('humidity') is not None else 43.9
    except (TypeError, ValueError):
        h_val = 43.9

    map_info = {
        'lat': map_lat,
        'lon': map_lon,
        'ppm': round(ppm_val, 1),
        'level': aqi_row['level'],
        'temp': round(t_val, 1),
        'humidity': round(h_val, 1),
    }

    return render_template('map.html', active_nav='map', locations=locations, map_info=map_info, map_extra=map_extra)


@app.route('/news')
def news_view():
    """
    Page des sources d'actualités liées à l'environnement.
    """
    try:
        articles = merge_news_article_lists(
            22,
            DEMO_NEWS_ARTICLES[:3],
            get_news_articles(),
            fetch_rss_environment_news(12),
            DEMO_NEWS_ARTICLES[3:],
        )
        if not articles:
            articles = [ensure_article_has_link(a) for a in DEMO_NEWS_ARTICLES]

        news_pack = get_news_sources()
        raw_sources = []
        if isinstance(news_pack, dict):
            raw_sources = news_pack.get('results') or []
        sources = []
        for s in raw_sources[:12]:
            card = normalize_news_source_card(s)
            if card:
                sources.append(card)
        if not sources:
            sources = DEMO_NEWS_SOURCES

        return render_template(
            'news.html',
            active_nav='news',
            sources=sources,
            articles=articles,
        )
    except Exception as e:
        logger.error(f"Erreur /news: {e}")
        return render_template(
            'news.html',
            active_nav='news',
            sources=DEMO_NEWS_SOURCES,
            articles=[ensure_article_has_link(a) for a in DEMO_NEWS_ARTICLES],
        )


@app.route('/predictions')
def predictions_view():
    """
    Page des prédictions ML - Version sans JavaScript
    Toujours affiche des prédictions, même si le modèle ML n'est pas disponible (Raspberry Pi 4)
    """
    try:
        # Récupérer les prédictions (logique similaire à l'API)
        # On simule ou on utilise le predictor si possible
        predictions = []
        recommendations = []
        
        # Prédictions ML (même logique que /api/predictions — predict_next_hours n’existait pas)
        try:
            if not predictor.model:
                predictor.load_model()
            if predictor.model:
                latest_readings = db.get_latest_readings(limit=1)
                if latest_readings:
                    current_data = {
                        'air_quality_ppm': latest_readings[0]['air_quality_ppm'],
                        'temperature': latest_readings[0]['temperature'],
                        'humidity': latest_readings[0]['humidity'],
                    }
                else:
                    current_data = {
                        'air_quality_ppm': 80.0,
                        'temperature': 25.0,
                        'humidity': 55.0,
                    }
                preds = predictor.predict(current_data, hours_ahead=24)
                if preds:
                    for p in preds:
                        ts_raw = p['timestamp']
                        if isinstance(ts_raw, str):
                            pred_time = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                        else:
                            pred_time = ts_raw
                        level_info = config.get_air_quality_level(p['predicted_aqi'])
                        predictions.append({
                            'time': pred_time.strftime('%H:%M'),
                            'value': round(float(p['predicted_aqi']), 1),
                            'level': level_info['level'],
                            'color': level_info['color'],
                        })

                    avg_pred = sum(float(p['predicted_aqi']) for p in preds) / len(preds)
                    if avg_pred > 100:
                        recommendations.append({
                            'title': 'Attention Pollution',
                            'message': 'Des niveaux élevés sont prévus. Limitez les activités physiques intenses.',
                            'icon': '⚠️',
                        })
                    else:
                        recommendations.append({
                            'title': 'Qualité Stable',
                            'message': 'La qualité de l\'air devrait rester acceptable pour les prochaines 24h.',
                            'icon': '✅',
                        })
        except Exception as ml_err:
            logger.warning(f"⚠️ Erreur modèle ML (utilisation fallback): {ml_err}")
        
        # Si aucune prédiction ML, utiliser les données de secours (toujours fonctionnel sur Raspberry Pi)
        if not predictions:
            base_h = datetime.now().replace(minute=0, second=0, microsecond=0)
            # Pattern réaliste basé sur l'heure de la journée
            demo_vals = []
            for i in range(24):
                t = base_h + timedelta(hours=i + 1)
                hour = t.hour
                # Pattern: pic vers 18h, baisse la nuit
                base_val = 85 + 20 * np.sin((hour - 6) * np.pi / 12)
                noise = np.random.normal(0, 8)
                val = max(50, min(150, base_val + noise))
                demo_vals.append(val)
            
            predictions = []
            for i, val in enumerate(demo_vals):
                t = base_h + timedelta(hours=i + 1)
                level_info = config.get_air_quality_level(val)
                predictions.append({
                    'time': t.strftime('%H:%M'),
                    'value': round(float(val), 1),
                    'level': level_info['level'],
                    'color': level_info['color'],
                    'bar_pct': min(100, int(val / 1.5)),
                })

        for p in predictions:
            if 'bar_pct' not in p:
                try:
                    p['bar_pct'] = min(100, int(float(p['value']) / 1.5))
                except (TypeError, ValueError):
                    p['bar_pct'] = 40

        reco_cards = [
            {
                'icon': '🌿',
                'title': 'Ventilation',
                'message': 'Aérez votre maison tôt le matin ou tard le soir, quand la pollution est plus faible.',
            },
            {
                'icon': '🏃',
                'title': 'Activité physique',
                'message': 'Évitez le sport intense en extérieur aux heures de pic de pollution signalées.',
            },
            {
                'icon': '😷',
                'title': 'Protection',
                'message': 'Les personnes sensibles devraient limiter les sorties prolongues aux pics.',
            },
            {
                'icon': '📡',
                'title': 'Surveillance',
                'message': 'Température et humidité actuelles restent dans des plages habituelles — suivez l\'IQA.',
            },
        ]

        peak_banner = None
        if predictions:
            peak = max(predictions, key=lambda x: float(x['value']))
            if float(peak['value']) >= 100:
                peak_banner = {
                    'detail': (
                        f"Pic de pollution prévu. Valeur maximale prévue à {peak['time']} : "
                        f"{float(peak['value']):.0f} PPM — {peak['level']}. Prenez vos précautions et limitez les activités "
                        f"extérieures intenses à ce moment."
                    )
                }

        return render_template(
            'predictions.html',
            active_nav='predictions',
            predictions=predictions,
            recommendations=recommendations,
            reco_cards=reco_cards,
            peak_banner=peak_banner,
        )
    except Exception as e:
        logger.error(f"Erreur /predictions: {e}")
        # Fallback ultime - toujours retourner quelque chose
        base_h = datetime.now().replace(minute=0, second=0, microsecond=0)
        demo_vals = [99, 101, 102, 83, 67, 71, 88, 95, 110, 116, 108, 92]
        fallback_preds = []
        for i, val in enumerate(demo_vals):
            t = base_h + timedelta(hours=i + 1)
            level_info = config.get_air_quality_level(val)
            fallback_preds.append({
                'time': t.strftime('%H:%M'),
                'value': float(val),
                'level': level_info['level'],
                'color': level_info['color'],
                'bar_pct': min(100, int(val / 1.5)),
            })
        return render_template(
            'predictions.html',
            active_nav='predictions',
            predictions=fallback_preds,
            recommendations=[],
            reco_cards=[
                {
                    'icon': '📦',
                    'title': 'Mode Simulation',
                    'message': (
                        'Les prédictions de secours s’affichent. '
                        'Le système fonctionne en mode simulation sur Raspberry Pi 4.'
                    ),
                },
            ],
            peak_banner=None,
        )


@app.route('/analytics')
def analytics_view():
    """
    Page d'analyses avancées sans JavaScript.
    Toutes les statistiques et analyses sont calculées côté serveur en Python.
    """
    try:
        # Période : 1 = 24 h, 7 ou 30 jours
        days = int(request.args.get('days', 7))
        if days not in (1, 7, 30, 90):
            days = 7
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

        avg_temp = sum(temperature) / len(temperature) if temperature else 0.0
        avg_hum = sum(humidity) / len(humidity) if humidity else 0.0

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
            'avg_temp': round(avg_temp, 1),
            'avg_humidity': round(avg_hum, 1),
            'total_readings': len(readings),
            'best_range': best_range,
            'quality_level': quality_info['level'],
            'quality_description': quality_info['description'],
            'distribution': dist,
            'dist_sensitive': dist[2] + dist[3] + dist[4],
            'dist_moderate': dist[1],
            'dist_good': dist[0],
        }

        history_rows = []
        for r in readings:
            ts = r['timestamp']
            ts_str = ts.isoformat(sep=' ', timespec='seconds') if hasattr(ts, 'isoformat') else str(ts)
            aq = r['air_quality_ppm']
            info = config.get_air_quality_level(aq)
            history_rows.append({
                'ts': ts_str,
                'aqi': round(float(aq), 1),
                'temp': round(float(r.get('temperature', 0) or 0), 1),
                'hum': round(float(r.get('humidity', 0) or 0), 1),
                'level': info['level'],
                'level_color': info['color'],
            })
        history_rows.reverse()

        return render_template(
            'analytics.html',
            active_nav='analytics',
            summary=summary,
            history_rows=history_rows,
            nasa_events=nasa_events,
        )
    except Exception as e:
        logger.error(f"Erreur affichage /analytics: {e}")
        # Si problème, rediriger vers le dashboard simple
        return render_template('dashboard.html', active_nav='dashboard')


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
        'build': AIRWATCH_BUILD,
        'features': {
            'responsive': True,
            'authentication': False,
            'database': 'connected' if db and db.connection else 'disconnected',
            'ml_model': 'loaded' if predictor.model else 'not loaded',
            'weather_api': 'configured' if WEATHER_API_KEY and WEATHER_API_KEY != 'your_api_key_here' else 'not configured'
        }
    })






# ============= FONCTIONS BROADCAST (Désactivées) =============

def broadcast_sensor_data(data):
    """Plus utilisé dans la version sans JS"""
    pass

def broadcast_alert(alert):
    """Plus utilisé dans la version sans JS"""
    pass


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

@app.context_processor





def _hf_chat_completion(hf_api_key, messages, model_id=None):
    """
    Appelle Hugging Face InferenceClient (meilleure approche avec permissions).
    Retourne (texte, status_code, corps_brut_tronqué).
    """
    if not hf_api_key:
        logger.warning("HF_API_KEY vide, passage au prochain service...")
        return None, 0, ''
    
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        logger.warning("⚠ huggingface_hub not installed. Install with: pip install huggingface-hub")
        return None, 0, 'huggingface_hub not installed'
    
    try:
        client = InferenceClient(api_key=hf_api_key)
        
        # Essayer avec le modèle spécifié ou le fallback
        models_to_try = []
        if model_id:
            models_to_try.append(model_id)
        
        # Modèles disponibles et fiables
        models_to_try.extend([
            'Qwen/Qwen2.5-72B-Instruct',
            'meta-llama/Llama-3.1-70b-instruct',
            'mistralai/Mistral-7B-Instruct-v0.3',
            'HuggingFaceTB/SmolLM2-1.7B-Instruct',
        ])
        
        for model in models_to_try:
            try:
                logger.info(f"🔮 Essai HF InferenceClient avec {model}...")
                
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=256,
                    temperature=0.7,
                    timeout=30
                )
                
                text = response.choices[0].message.content
                if text:
                    logger.info(f'✓ HF InferenceClient OK — {model}')
                    return text, 200, text[:500]
                    
            except Exception as model_err:
                err_msg = str(model_err)
                if 'not available' in err_msg.lower() or 'not found' in err_msg.lower():
                    logger.warning(f"⚠ Modèle {model} indisponible: {err_msg[:100]}")
                    continue
                elif 'timeout' in err_msg.lower():
                    logger.warning(f"⚠ Timeout avec {model}")
                    continue
                else:
                    logger.warning(f"⚠ Erreur HF {model}: {err_msg[:100]}")
                    continue
        
        logger.error("✗ Aucun modèle HF disponible")
        return None, 0, 'No HF models available'
        
    except Exception as e:
        logger.error(f"✗ HF InferenceClient error: {str(e)[:200]}")
        return None, 0, str(e)[:500]

# ============= DÉMARRAGE DU SERVEUR =============

@app.context_processor
def inject_theme():
    """Rend la variable theme disponible dans tous les templates"""
    return {'theme': session.get('theme', 'dark'), 'app_build': AIRWATCH_BUILD}

@app.route('/toggle-theme')
def toggle_theme():
    """Bascule entre le mode sombre et le mode clair"""
    current_theme = session.get('theme', 'dark')
    session['theme'] = 'light' if current_theme == 'dark' else 'dark'
    return redirect(request.referrer or url_for('index'))

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
    
    # Lancer le serveur Flask
    logger.info(f"🚀 Serveur Web démarré sur http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)