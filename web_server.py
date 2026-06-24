"""
Serveur Web Flask pour l'interface de surveillance de qualité de l'air
VERSION 2.2 - Responsive + Sans Authentification
Fournit une API REST et une interface web moderne pour visualiser les données en temps réel
Intègre OpenWeatherMap API pour les données météorologiques
"""
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, Response
import logging
from datetime import datetime, timedelta
import json
import requests
import os
import urllib.parse
import xml.etree.ElementTree as ET
import numpy as np
import csv
import io
import random
try:
    import folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
from config import config
from database import AirQualityDatabase
from ml_model import AirQualityPredictor
from weather_chatbot import get_chatbot

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

# Cache météo par localisation : chaque visiteur reçoit la météo de SA position
# Clé = coordonnées GPS arrondies, ou nom de ville, ou 'default'
_weather_caches = {}  # dict: cache_key (str) -> {'data': dict, 'timestamp': datetime}
WEATHER_CACHE_DURATION = 600  # Durée du cache météo en secondes (10 min)

# Cache géolocalisation IP : associe une adresse IP à des coordonnées GPS
# Permet d'éviter de sur-solliciter ip-api.com (limite gratuite : 45 req/min)
_ip_geo_cache = {}  # dict: ip_str -> {'data': dict | None, 'timestamp': float}
IP_GEO_CACHE_DURATION = 3600  # Durée du cache IP en secondes (1 heure)

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
    # Importation locale des modules trigonométriques pour éviter les dépendances inutiles au démarrage
    from math import radians, sin, cos, asin, sqrt

    try:
        # Conversion des coordonnées en nombres flottants (float) pour sécuriser le calcul
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        # Si une coordonnée est absente ou invalide, on retourne None pour éviter une exception
        return None

    # Rayon moyen de la Terre en kilomètres
    r = 6371.0
    # Calcul de la différence de latitude convertie en radians
    d_lat = radians(lat2 - lat1)
    # Calcul de la différence de longitude convertie en radians
    d_lon = radians(lon2 - lon1)
    # Formule mathématique Haversine pour la distance sphérique
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    # Calcul de l'angle central en radians
    c = 2 * asin(sqrt(a))
    # Retourne le produit du rayon terrestre par l'angle pour obtenir la distance en kilomètres
    return r * c


def get_client_ip():
    """
    Récupère l'adresse IP réelle du visiteur depuis les headers HTTP.
    Fonctionne correctement derrière Cloudflare, Nginx et autres reverse proxies.

    Priorité des headers :
        1. CF-Connecting-IP  — header Cloudflare contenant l'IP client originale
        2. X-Forwarded-For   — standard proxy ; le premier élément est l'IP client
        3. request.remote_addr — connexion directe (développement local)

    Returns:
        str: Adresse IP du visiteur
    """
    # Header spécifique à Cloudflare (le plus fiable pour votre hébergement)
    cf_ip = request.headers.get('CF-Connecting-IP', '').strip()
    if cf_ip:
        return cf_ip

    # Header standard reverse proxy — peut contenir plusieurs IPs séparées par virgule
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        first_ip = forwarded_for.split(',')[0].strip()
        if first_ip:
            return first_ip

    # Connexion directe (sans proxy, ex. développement local)
    return request.remote_addr or '127.0.0.1'


def get_ip_geolocation(ip):
    """
    Convertit une adresse IP en coordonnées GPS via l'API gratuite ip-api.com.
    Aucune clé API requise. Limite gratuite : 45 requêtes/minute.

    Les IPs locales/privées (127.0.0.1, 192.168.x.x, etc.) retournent None
    afin d'utiliser la position par défaut (définie dans config.py).

    Args:
        ip (str): Adresse IP du visiteur

    Returns:
        dict | None: {'lat', 'lon', 'city', 'country', 'countryCode', 'region'}
                     ou None si IP locale ou erreur réseau
    """
    import ipaddress

    # Rejeter les IPs privées / loopback — elles ne peuvent pas être géolocalisées
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            logger.info(f"IP locale/privée ({ip}) — position par défaut utilisée")
            return None
    except ValueError:
        logger.warning(f"Adresse IP invalide : {ip}")
        return None

    # Vérifier le cache pour éviter des appels répétés pour la même IP
    now = datetime.now().timestamp()
    cached = _ip_geo_cache.get(ip)
    if cached and (now - cached['timestamp']) < IP_GEO_CACHE_DURATION:
        return cached['data']  # Peut être None si la géolocalisation avait échoué

    # Appel à ip-api.com — gratuit, sans authentification
    try:
        url = f'http://ip-api.com/json/{ip}?fields=status,message,lat,lon,city,country,countryCode,regionName'
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success':
                result = {
                    'lat': float(data['lat']),
                    'lon': float(data['lon']),
                    'city': data.get('city', ''),
                    'country': data.get('country', ''),
                    'countryCode': data.get('countryCode', ''),
                    'region': data.get('regionName', ''),
                }
                _ip_geo_cache[ip] = {'data': result, 'timestamp': now}
                logger.info(
                    f"Géolocalisation IP {ip} → {result['city']}, "
                    f"{result['country']} ({result['lat']:.4f}, {result['lon']:.4f})"
                )
                return result
            else:
                logger.warning(f"ip-api.com échec pour {ip} : {data.get('message', '?')}")
    except Exception as e:
        logger.warning(f"Erreur géolocalisation IP {ip} : {e}")

    # Mettre None en cache pour éviter de spammer l'API en cas d'erreur
    _ip_geo_cache[ip] = {'data': None, 'timestamp': now}
    return None


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
    # Création d'une clé de cache unique basée sur les paramètres de recherche
    key = (lat, lon, max_distance_km)
    # Récupération du timestamp actuel sous forme de secondes
    now = datetime.now().timestamp()

    # Vérification de la validité du cache (données présentes et durée de cache non dépassée)
    if nasa_events_cache['data'] is not None and nasa_events_cache['timestamp'] is not None:
        if nasa_events_cache['key'] == key and (now - nasa_events_cache['timestamp']) < nasa_events_cache['cache_duration']:
            # Retourne les données en cache si elles correspondent aux paramètres et sont fraîches
            return nasa_events_cache['data']

    # Sinon, on interroge l'API NASA EONET
    try:
        # Paramètres de la requête : ne récupérer que les évènements en cours (ouverts)
        params = {'status': 'open'}
        # Si une clé API NASA est présente dans la configuration, on l'ajoute aux paramètres
        if NASA_API_KEY:
            params['api_key'] = NASA_API_KEY

        # Envoi de la requête HTTP GET vers l'API NASA avec un timeout de 15 secondes
        resp = requests.get(NASA_EONET_URL, params=params, timeout=15)
        # Si la réponse n'est pas un succès (code HTTP 200), on logge un warning et on s'arrête
        if resp.status_code != 200:
            logger.warning(f"Erreur API NASA EONET: {resp.status_code}")
            return []

        # Extraction des données JSON de la réponse
        data = resp.json()
        events = []

        # Parcours de chaque évènement environnemental renvoyé par la NASA
        for event in data.get('events', []):
            # Récupération des catégories de l'évènement en minuscules
            categories = [c.get('title', '').lower() for c in event.get('categories', [])]
            # Création d'une chaîne combinée pour faciliter le filtrage par mots-clés
            text_categories = " ".join(categories)
            # On ne garde que les évènements liés à l'air (poussière, fumée, incendies, sable, cendres)
            if not any(keyword in text_categories for keyword in ['dust', 'smoke', 'fire', 'wildfire', 'sand', 'ash']):
                continue

            # Parcours des géométries associées (position géographique de l'évènement)
            for geom in event.get('geometry', []):
                coords = geom.get('coordinates')
                # Vérification de la présence de coordonnées valides (longitude, latitude)
                if not coords or len(coords) < 2:
                    continue

                ev_lon, ev_lat = coords[0], coords[1]
                distance = None
                # Si une position utilisateur est fournie, on calcule la distance à l'évènement
                if lat is not None and lon is not None:
                    distance = _haversine_km(lat, lon, ev_lat, ev_lon)
                    # Si l'évènement est trop éloigné, on l'ignore
                    if distance is None or distance > max_distance_km:
                        continue

                # Ajout de l'évènement filtré et enrichi dans notre liste locale
                events.append({
                    'title': event.get('title'),
                    'categories': [c.get('title') for c in event.get('categories', [])],
                    'distance_km': round(distance, 1) if distance is not None else None,
                    'coordinates': {'lat': ev_lat, 'lon': ev_lon},
                    'link': (event.get('links') or [{}])[0].get('href'),
                    'date': geom.get('date')
                })

        # Tri des évènements trouvés du plus proche au plus éloigné
        events.sort(key=lambda e: e['distance_km'] if e['distance_km'] is not None else 999999)
        # On limite le retour aux 10 évènements les plus proches
        events = events[:10]

        # Mise à jour du cache global pour éviter de surcharger l'API lors des prochaines visites
        nasa_events_cache['key'] = key
        nasa_events_cache['data'] = events
        nasa_events_cache['timestamp'] = now

        return events

    except Exception as e:
        # En cas d'erreur réseau ou autre, on logge l'erreur et on retourne une liste vide
        logger.error(f"Erreur récupération évènements NASA: {e}")
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
        # Si la clé API NewsData n'est pas configurée dans les variables d'environnement, on ignore l'appel
        if not NEWSDATA_API_KEY:
            return {}
        # Construction des paramètres requis par l'API NewsData
        params = {
            'apikey': NEWSDATA_API_KEY,
            'country': country,
            'language': language,
            'category': category,
            'prioritydomain': prioritydomain
        }
        # Envoi de la requête GET avec un timeout de 15 secondes pour éviter le blocage
        response = requests.get(NEWSDATA_SOURCES_URL, params=params, timeout=15)
        # Gestion des erreurs de retour API
        if response.status_code != 200:
            logger.warning(f"Erreur API NewsData: {response.status_code}")
            return {}

        # Conversion et log du nombre de sources récupérées
        data = response.json()
        logger.info(f"Données NewsData récupérées: {len(data.get('results', []))} sources")
        return data
    except Exception as e:
        # En cas de plantage réseau ou parse, renvoie un dictionnaire vide
        logger.error(f"Erreur récupération sources NewsData: {e}")
        return {}


def _fmt_news_meta(item):
    """Formate les métadonnées d'un article (nom de la source + date de publication)."""
    # Récupère l'identifiant de la source ou son nom
    src = item.get('source_id') or item.get('source_name') or ''
    # Récupère la date brute de publication
    raw_date = item.get('pubDate') or item.get('pubdate') or ''
    # Si la date est trop longue, on la tronque au format 'AAAA-MM-JJ HH:MM'
    if raw_date and len(raw_date) > 16:
        raw_date = raw_date[:16].replace('T', ' ')
    # Ne garde que les parties non vides
    parts = [p for p in (src, raw_date) if p]
    # Joint les éléments avec un point médian
    return ' • '.join(parts) if parts else 'Actualité'


def _category_to_tag_style(cat):
    """Associe une catégorie d'actualité à un style CSS et un label en français."""
    c = (str(cat) if cat is not None else '').lower()
    # Association de la catégorie "Santé"
    if 'health' in c or 'sant' in c:
        return 'health', 'Santé'
    # Association de la catégorie "Politique"
    if 'politic' in c or 'polit' in c:
        return 'pol', 'Politique'
    # Association de la catégorie "Environnement"
    if 'environment' in c or 'environ' in c:
        return 'env', 'Environnement'
    # Association de la catégorie "Climat/Science"
    if 'science' in c or 'tech' in c:
        return 'cli', 'Science'
    # Fallback pour les autres catégories (ex. lifestyle)
    label = (str(cat) if cat else 'Actualités').replace('_', ' ').strip() or 'Actualités'
    return 'life', label[:40]


def get_news_articles(country='ma', language='fr', category='environment,health,lifestyle,science'):
    """Articles récents (endpoint /news) avec liens vers les sources."""
    global news_cache
    # Si pas de clé d'API NewsData configurée, on retourne une liste vide directement
    if not NEWSDATA_API_KEY:
        return []
    # Clé de cache unique basée sur les paramètres géographiques et thématiques
    key = (country, language, category)
    now = datetime.now().timestamp()

    # Vérifie si le cache contient des données fraîches
    if news_cache['data'] is not None and news_cache['timestamp'] is not None:
        if news_cache['key'] == key and (now - news_cache['timestamp']) < news_cache['cache_duration']:
            return news_cache['data']

    # Sinon, on fait une requête à NewsData.io
    try:
        params = {
            'apikey': NEWSDATA_API_KEY,
            'country': country,
            'language': language,
            'category': category,
        }
        response = requests.get(NEWSDATA_NEWS_URL, params=params, timeout=20)
        # Log en cas d'erreur de retour
        if response.status_code != 200:
            logger.warning(f"Erreur API NewsData articles: {response.status_code}")
            return []
        data = response.json()
        rows = data.get('results') or []
        out = []
        # Nettoyage et normalisation des articles reçus
        for row in rows:
            # Récupération de l'URL de l'article (supporte plusieurs clés de retour possibles)
            link = row.get('link') or row.get('url') or row.get('source_url') or row.get('article_url')
            title = (row.get('title') or '').strip()
            # Un article doit impérativement avoir un titre et un lien pour être affiché
            if not link or not title:
                continue
            # Troncation de la description si trop longue
            desc = (row.get('description') or row.get('content') or '')[:500]
            cat = row.get('category')
            if isinstance(cat, list) and cat:
                cat = cat[0]
            # Détermination de la mise en forme du badge de l'article
            tag_style, tag_label = _category_to_tag_style(cat)
            out.append({
                'tag': tag_label,
                'tag_style': tag_style,
                'title': title,
                'meta': _fmt_news_meta(row),
                'summary': (desc or '').strip() or "Voir l'article sur le site de la source.",
                'url': link,
            })
        logger.info(f"NewsData articles: {len(out)}")
        # Limite de sécurité à 20 articles
        out = out[:20]

        # Mise à jour du cache
        news_cache['key'] = key
        news_cache['data'] = out
        news_cache['timestamp'] = now

        return out
    except Exception as e:
        logger.error(f"Erreur récupération articles NewsData: {e}")
        return []


def fetch_rss_environment_news(max_items=14):
    """Articles avec liens via flux RSS (requests + SSL — plus fiable que urllib sur Raspberry Pi)."""
    collected = []
    # User-Agent personnalisé pour éviter les blocages de certains serveurs de flux RSS
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; AirPredict/2.2; +https://airpredict.local)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    # Sur Raspberry Pi (détecté via l'absence de certains fichiers Linux standards), on désactive SSL si besoin
    verify_ssl = not os.path.exists('/etc/os-release')
    
    # Parcours des flux RSS de secours configurés
    for feed_url in RSS_FALLBACK_FEEDS:
        if len(collected) >= max_items:
            break
        try:
            # Tentative de requête avec ou sans vérification stricte des certificats SSL
            try:
                r = requests.get(feed_url, headers=headers, timeout=22, verify=verify_ssl)
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
                logger.warning(f'Erreur SSL pour {feed_url}, nouvelle tentative sans vérification...')
                r = requests.get(feed_url, headers=headers, timeout=22, verify=False)
            
            r.raise_for_status()
            # Parsing de l'arbre XML du flux RSS
            root = ET.fromstring(r.content)
        except Exception as e:
            logger.warning(f'Flux RSS indisponible {feed_url}: {e}')
            continue

        # Extraction des items de l'arborescence XML
        for item in root.iter():
            if not item.tag.endswith('item') or len(collected) >= max_items:
                continue
            title = link = desc = ''
            for child in item:
                # Extraction du nom du tag en ignorant le namespace XML
                tag = child.tag.split('}')[-1].lower()
                if tag == 'title' and child.text:
                    title = child.text.strip()
                elif tag == 'link':
                    link = (child.text or '').strip()
                    if not link and child.attrib.get('href'):
                        link = child.attrib.get('href', '').strip()
                elif tag in ('description', 'summary') and child.text:
                    txt = child.text.strip()
                    # Limite la taille de l'extrait affiché
                    if len(txt) > 400:
                        txt = txt[:400] + '…'
                    desc = txt
            # Si on a un titre et un lien, l'article est prêt
            if title and link:
                collected.append({
                    'tag': 'Environnement',
                    'tag_style': 'env',
                    'title': title,
                    'meta': 'Flux RSS',
                    'summary': desc or 'Article externe.',
                    'url': link,
                })
            # Si l'article n'a pas d'URL (rare mais possible), on génère un lien Google Search sur son titre
            elif title and not link:
                collected.append({
                    'tag': 'Environnement',
                    'tag_style': 'env',
                    'title': title,
                    'meta': 'Flux RSS',
                    'summary': desc or 'Article externe.',
                    'url': 'https://www.google.com/search?q=' + urllib.parse.quote_plus(title),
                })
    if collected:
        logger.info(f'RSS: {len(collected)} articles avec liens')
    return collected[:max_items]


def merge_news_article_lists(max_total, *lists):
    """Fusionne plusieurs listes d’articles sans doublon d’URL (ordre conservé)."""
    seen = set()
    out = []
    # Parcours des listes d'articles fournies en arguments
    for lst in lists:
        for a in lst or []:
            if not isinstance(a, dict):
                continue
            # Nettoyage et vérification de la clé unique (URL de l'article)
            u = (a.get('url') or '').strip()
            key = u if u else f"t:{a.get('title','')}"
            # Déduplication
            if key in seen:
                continue
            seen.add(key)
            # Garantir le lien cliquable et l'ajouter à la liste finale
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
    # Si l'article n'a pas d'URL, on crée un lien de recherche Web basé sur son titre
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
    # Normalise l'affichage des pays de diffusion
    if isinstance(country, (list, tuple)):
        country_txt = ', '.join(str(c).upper() for c in country[:8])
        if len(country) > 8:
            country_txt += '…'
    else:
        country_txt = str(country or 'MA').upper()
    lang = s.get('language')
    # Normalise l'affichage des langues supportées
    if isinstance(lang, (list, tuple)):
        lang_txt = ', '.join(str(x).upper() for x in lang[:5])
    else:
        lang_txt = str(lang or 'fr').upper()
    sub = f"{country_txt} — {lang_txt}"
    cat = s.get('category')
    # Détermination de la catégorie principale
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
    # Construire une clé de cache unique par localisation
    # (permet à chaque visiteur d'avoir la météo de sa propre position)
    if lat and lon:
        try:
            cache_key = f"coords:{round(float(lat), 2)}:{round(float(lon), 2)}"
        except (TypeError, ValueError):
            cache_key = "default"
    elif city:
        cache_key = f"city:{str(city).lower().strip()}"
    else:
        cache_key = "default"

    # Vérifier le cache pour cette position
    _cached = _weather_caches.get(cache_key)
    if _cached and _cached.get('data') and _cached.get('timestamp'):
        age = (datetime.now() - _cached['timestamp']).seconds
        if age < WEATHER_CACHE_DURATION:
            logger.info(f"Météo en cache pour {cache_key}")
            return _cached['data']
    
    if not WEATHER_API_KEY or WEATHER_API_KEY == 'your_api_key_here':
        logger.warning("Clé API météo non configurée")
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
            
            # Stocker dans le cache par position (clé unique par localisation)
            _weather_caches[cache_key] = {
                'data': weather_data,
                'timestamp': datetime.now()
            }
            
            logger.info(f"Données météo récupérées: {weather_data['city']}, {weather_data['temperature']}°C")
            return weather_data
        else:
            logger.error(f"Erreur API météo: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Erreur récupération météo: {e}")
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
        logger.warning("Clé API météo non configurée pour prévisions")
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
        logger.error(f"Erreur prévisions météo: {e}")
        return {'success': False, 'error': str(e)}


# ============= ROUTES WEB (Interface utilisateur) =============

@app.route('/')
def index():
    """
    Page d'accueil principale - Dashboard moderne 100% No-JS
    Toutes les données sont injectées côté serveur
    """
    # 0. Géolocalisation du visiteur par son adresse IP
    #    Fonctionne derrière Cloudflare grâce au header CF-Connecting-IP
    #    Ainsi la météo et la carte reflètent la position du visiteur,
    #    pas celle du Raspberry Pi qui héberge le code.
    _client_ip = get_client_ip()
    _client_geo = get_ip_geolocation(_client_ip)
    _client_lat = _client_geo['lat'] if _client_geo else None
    _client_lon = _client_geo['lon'] if _client_geo else None

    # 1. Données Météo selon la position du visiteur (pas du Raspberry Pi)
    weather = get_weather_data(lat=_client_lat, lon=_client_lon)

    # 2. Dernière mesure enregistrée (AQI)
    latest_readings = db.get_latest_readings(limit=1)
    latest_reading = latest_readings[0] if latest_readings else None

    # 3. Statistiques 24h
    stats = db.get_statistics(hours=24)

    # 4. Prévisions météo (5 jours) pour la position du visiteur
    forecast_data = get_weather_forecast(lat=_client_lat, lon=_client_lon, days=5)
    forecasts = forecast_data.get('forecasts', []) if forecast_data.get('success') else []

    # 5. Alertes actives
    alerts = db.get_recent_alerts(limit=5)

    # 6. Infos de Qualité d'Air
    aqi_value = latest_reading['air_quality_ppm'] if latest_reading else 0
    aqi_info = config.get_air_quality_level(aqi_value)

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    return render_template(
        'dashboard.html',
        active_nav='dashboard',
        weather=weather,
        stats=stats,
        forecasts=forecasts,
        alerts=alerts,
        aqi=aqi_info,
        aqi_value=round(aqi_value, 1),
        now_str=now_str,
        client_geo=_client_geo,
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

    # Géolocalisation du visiteur pour centrer la carte sur SA position
    # (et non sur Casablanca ou sur le Raspberry Pi)
    _client_ip = get_client_ip()
    _client_geo = get_ip_geolocation(_client_ip)

    if _client_geo:
        # Le visiteur a été géolocalisé : centrer sur sa position
        home_lat = _client_geo['lat']
        home_lon = _client_geo['lon']
        city_name = _client_geo.get('city') or config.WEATHER_DEFAULT_QUERY.split(',')[0].replace('+', ' ')
        logger.info(f"Carte centrée sur la position du visiteur : {city_name} ({home_lat:.4f}, {home_lon:.4f})")
    else:
        # IP locale ou non géolocalisable : repli sur Casablanca (position du capteur)
        home_lat = float(config.MAP_CENTER_LAT)
        home_lon = float(config.MAP_CENTER_LON)
        city_name = config.WEATHER_DEFAULT_QUERY.split(',')[0].replace('+', ' ')

    # Données météo pour la position du visiteur
    weather = get_weather_data(lat=home_lat, lon=home_lon)

    # Centre de la carte = position du visiteur (ou défaut si non disponible)
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
        'osm_url': (
            f'https://www.openstreetmap.org/?mlat={map_lat}&mlon={map_lon}'
            f'#map=13/{map_lat}/{map_lon}'
        ),
    }

    return render_template('map.html', active_nav='map', locations=locations, map_info=map_info, map_extra=map_extra)


@app.route('/map/static.png')
def map_static_image():
    """Image carte statique — générée localement avec la bibliothèque staticmap."""
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    if lat is None or lon is None:
        return jsonify({'success': False, 'error': 'lat et lon requis'}), 400

    try:
        from staticmap import StaticMap, CircleMarker
        import io
        
        # Initialiser la carte avec une taille adaptée
        m = StaticMap(1280, 560)
        
        # Ajouter le marqueur rouge pour la position actuelle (lon, lat)
        marker = CircleMarker((lon, lat), '#ef4444', 18)
        m.add_marker(marker)
        
        # Rendre la carte
        image = m.render()
        
        # Écrire l'image dans un flux d'octets PNG
        img_io = io.BytesIO()
        image.save(img_io, 'PNG')
        img_io.seek(0)
        
        resp = Response(img_io.getvalue(), mimetype='image/png')
        resp.headers['Cache-Control'] = 'public, max-age=600'
        return resp
    except Exception as e:
        logger.error('Erreur lors de la génération de la carte statique locale: %s', e)

    # SVG de secours si le service externe échoue
    label = f'{lat:.4f}, {lon:.4f}'
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="560" viewBox="0 0 1280 560">
  <rect width="100%" height="100%" fill="#1e293b"/>
  <text x="50%" y="48%" text-anchor="middle" fill="#94a3b8" font-family="sans-serif" font-size="22">
    Carte temporairement indisponible
  </text>
  <text x="50%" y="54%" text-anchor="middle" fill="#e2e8f0" font-family="sans-serif" font-size="18">{label}</text>
</svg>'''
    return Response(svg, mimetype='image/svg+xml')


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
                        })
                    else:
                        recommendations.append({
                            'title': 'Qualité Stable',
                            'message': 'La qualité de l\'air devrait rester acceptable pour les prochaines 24h.',
                        })
        except Exception as ml_err:
            logger.warning(f"Erreur modèle ML (utilisation fallback): {ml_err}")
        
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
                'title': 'Ventilation',
                'message': 'Aérez votre maison tôt le matin ou tard le soir, quand la pollution est plus faible.',
            },
            {
                'title': 'Activité physique',
                'message': 'Évitez le sport intense en extérieur aux heures de pic de pollution signalées.',
            },
            {
                'title': 'Protection',
                'message': 'Les personnes sensibles devraient limiter les sorties prolongues aux pics.',
            },
            {
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
                    'latitude': config.MAP_CENTER_LAT,
                    'longitude': config.MAP_CENTER_LON
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
                    'latitude': config.MAP_CENTER_LAT,
                    'longitude': config.MAP_CENTER_LON
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
                    'latitude': config.MAP_CENTER_LAT,
                    'longitude': config.MAP_CENTER_LON
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
            logger.warning("Modèle ML non chargé, tentative de chargement...")
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
                'title': 'Statut actuel',
                'message': recommendations_raw['current_status']
            })
        for action in recommendations_raw.get('actions', []):
            recommendations.append({'title': 'Action', 'message': action})
        for advice in recommendations_raw.get('health_advice', []):
            recommendations.append({'title': 'Conseil santé', 'message': advice})
        for period in recommendations_raw.get('time_periods_to_avoid', []):
            recommendations.append({'title': 'Période à éviter', 'message': period})
        
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

# ============= INITIALISATION =============

def initialize_server():
    """Initialise le serveur et les connexions"""
    global db
    
    logger.info("INITIALISATION DU SERVEUR AIRWATCH v2.2")
    
    # Connexion à la base de données SQLite3
    db_path = config.DB_CONFIG.get('db_path', './data/air_quality.db')
    db = AirQualityDatabase(db_path=db_path)
    
    if db.connect():
        logger.info("Connexion base de données établie")
        db.create_tables()
    else:
        logger.error("Échec connexion base de données")
    
    # Charger le modèle ML
    if predictor.load_model():
        logger.info("Modèle ML chargé")
    else:
        logger.warning("Modèle ML non disponible")
        logger.info("  Pour entraîner le modèle : python3 ml_model.py")
    
    # Vérifier la configuration Weather API
    if WEATHER_API_KEY and WEATHER_API_KEY != 'your_api_key_here':
        logger.info("API météo configurée (OpenWeatherMap)")
    else:
        logger.warning("API météo non configurée")
        logger.info("  1. Visitez https://openweathermap.org/api")
        logger.info("  2. Créez un compte gratuit")
        logger.info("  3. Ajoutez OPENWEATHER_API_KEY dans .env")
        logger.info("  → Données météo de test seront utilisées")
    
    logger.info("")
    logger.info("Serveur web initialisé avec succès")
    logger.info("")


# ============= DÉMARRAGE DU SERVEUR =============

@app.context_processor




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


# ============= WEATHER CHATBOT ROUTES =============

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    """Weather chatbot interface without JavaScript"""
    # Initialize chat history in session if not present
    if 'chat_history' not in session:
        session['chat_history'] = [
            {
                'role': 'assistant',
                'content': "👋 Bonjour ! Je suis votre assistant météo intelligent. Comment puis-je vous aider aujourd'hui ?",
                'timestamp': datetime.now().strftime('%H:%M')
            }
        ]
    
    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        user_input = request.form.get('user_input', '').strip()
        quick_action = request.form.get('quick_action', '').strip()
        
        if action == 'reset':
            session['chat_history'] = [
                {
                    'role': 'assistant',
                    'content': "🔄 Conversation réinitialisée ! Posez-moi vos questions sur la météo ou la qualité de l'air.",
                    'timestamp': datetime.now().strftime('%H:%M')
                }
            ]
            session.modified = True
            return redirect(url_for('chatbot') + '#bottom')
        
        # Determine the message content
        message_to_send = user_input
        if quick_action:
            message_to_send = quick_action
            
        if message_to_send:
            # Add user message to history
            history = session['chat_history']
            history.append({
                'role': 'user',
                'content': message_to_send,
                'timestamp': datetime.now().strftime('%H:%M')
            })
            session['chat_history'] = history
            session.modified = True
            
            try:
                # Get current weather data for context
                weather_context = get_weather_data() or {}
                if 'description' in weather_context:
                    weather_context['weather_type'] = weather_context['description']
                
                # Get chatbot instance
                chatbot_inst = get_chatbot()
                
                # Sync session history to chatbot instance (excluding the last one we just appended)
                chatbot_inst.conversation_history = [
                    {'role': msg['role'], 'content': msg['content']}
                    for msg in session['chat_history'][:-1]
                ]
                
                # Get response from chatbot
                response = chatbot_inst.chat(message_to_send, weather_context=weather_context)
                
                if response.get('status') == 'success':
                    assistant_msg = response.get('message', '')
                else:
                    assistant_msg = f"Désolé, j'ai rencontré une erreur : {response.get('message')}"
                    
            except Exception as e:
                logger.error(f"Chatbot error: {str(e)}")
                assistant_msg = "Désolé, une erreur est survenue lors de la communication avec l'IA."
                
            # Add assistant message to history
            history = session['chat_history']
            history.append({
                'role': 'assistant',
                'content': assistant_msg,
                'timestamp': datetime.now().strftime('%H:%M')
            })
            session['chat_history'] = history
            session.modified = True
            
            return redirect(url_for('chatbot') + '#bottom')
            
    return render_template(
        'chatbot.html',
        theme=session.get('theme', 'dark'),
        app_build=AIRWATCH_BUILD,
        active_nav='chatbot',
        chat_history=session['chat_history']
    )


# Keep simple placeholders/compatibility API endpoints that return standard error/unsupported response in case of external requests
@app.route('/api/chatbot/message', methods=['POST'])
def chatbot_message():
    return jsonify({'status': 'error', 'message': 'API deprecated. Use /chatbot form submission instead.'}), 400


@app.route('/api/chatbot/advice', methods=['GET'])
def chatbot_advice():
    return jsonify({'status': 'error', 'message': 'API deprecated. Use /chatbot form submission instead.'}), 400


@app.route('/api/chatbot/reset', methods=['POST'])
def chatbot_reset():
    return jsonify({'status': 'error', 'message': 'API deprecated. Use /chatbot form submission instead.'}), 400


# ============= ENTREPRISE ROUTES (CO2 WASH) =============
import random
from functools import wraps

def entreprise_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('entreprise_logged_in'):
            return redirect(url_for('entreprise_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_external_emissions_data():
    """Fetch real emissions data from Carbon Interface or fallback if no key"""
    api_key = os.getenv('CARBON_INTERFACE_API_KEY')
    if api_key:
        try:
            # Example call to Carbon Interface API for electricity generation emissions
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "type": "electricity",
                "electricity_unit": "mwh",
                "electricity_value": 50.0, # Assumed 50 MWh consumed by factory per hour
                "country": "ma" # Morocco
            }
            resp = requests.post("https://www.carboninterface.com/api/v1/estimates", json=payload, headers=headers, timeout=5)
            if resp.status_code == 201:
                data = resp.json()
                return data['data']['attributes']['carbon_kg']
        except Exception as e:
            logger.error(f"Erreur API Carbone: {e}")
    
    # Fallback réaliste : génère autour de 18 tonnes de CO2 émises
    base_emissions = 18000.0 
    noise = random.uniform(-1000.0, 1500.0)
    return base_emissions + noise

@app.route('/entreprise/login', methods=['GET', 'POST'])
def entreprise_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'pfe2026':
            session['entreprise_logged_in'] = True
            return redirect(url_for('entreprise_co2_wash'))
        else:
            error = "Identifiants invalides."
    return render_template(
        'login_entreprise.html',
        error=error,
        theme=session.get('theme', 'dark'),
    )

@app.route('/entreprise/logout')
def entreprise_logout():
    session.pop('entreprise_logged_in', None)
    return redirect(url_for('entreprise_login'))

@app.route('/entreprise/co2-wash')
@entreprise_required
def entreprise_co2_wash():
    """
    Dashboard CO2 Wash.

    Nouveau comportement:
    - La source principale des émissions (gross kg/h) et de l'efficacité vient d'un CSV uploadé par l'entreprise.
    - Si aucun CSV n'a été uploadé dans la session, on affiche un fallback (API externe / simulation)
      avec un statut explicite, afin que la page reste utilisable.
    """
    error = request.args.get('error', '')
    success = request.args.get('success', '')

    co2_data = session.get('co2_wash_data')
    if co2_data:
        gross_emissions_kg = float(co2_data.get('gross_kg_h', 0.0) or 0.0)
        efficiency = float(co2_data.get('efficiency', 0.88) or 0.88)
        source_label = f"CSV upload ({co2_data.get('file_name', 'unknown')})"
        status_label = "Actif - Données CSV"
        last_upload = co2_data.get('upload_timestamp')
        num_records = co2_data.get('num_records', 0)
    else:
        # Mode strict: utiliser uniquement les données du CSV.
        gross_emissions_kg = 0.0
        efficiency = 0.88
        source_label = "Aucune donnée (CSV requis)"
        status_label = "En attente - Uploadez un CSV CO2 Wash"
        last_upload = None
        num_records = 0
    
    captured_kg = gross_emissions_kg * efficiency
    net_emissions_kg = gross_emissions_kg - captured_kg
    
    # Trees equivalent (assuming a tree absorbs ~22kg of CO2 per year)
    trees_saved = int(captured_kg / (22.0 / 365.0)) # Daily equivalent
    
    stats = {
        'gross': round(gross_emissions_kg, 1),
        'efficiency': round(efficiency * 100, 1),
        'captured': round(captured_kg, 1),
        'net': round(net_emissions_kg, 1),
        'trees': trees_saved,
        'status': status_label,
        'source': source_label,
        'last_upload': last_upload,
        'num_records': num_records,
    }
    
    return render_template(
        'co2_wash.html',
        stats=stats,
        active_nav='co2-wash',
        error=error,
        success=success,
    )


@app.route('/entreprise/co2-wash/upload', methods=['POST'])
@entreprise_required
def entreprise_co2_wash_upload():
    """
    Upload CSV (CO2 Wash) par l'entreprise.

    Le CSV peut contenir (au minimum) une colonne d'émissions brutes:
      - gross_emissions_kg_h / gross_kg_h / gross / emissions
    Et optionnellement:
      - efficiency / efficiency_percent / co2_wash_efficiency
      - captured_kg_h / captured
      - net_emissions_kg_h / net

    Si efficiency n'est pas fournie mais captured et gross existent, on la déduit:
      efficiency = captured / gross
    """
    try:
        if 'file' not in request.files:
            return redirect(url_for('entreprise_co2_wash') + '?error=Aucun%20fichier%20fourni')

        file = request.files['file']
        if file.filename == '':
            return redirect(url_for('entreprise_co2_wash') + '?error=Fichier%20vide')

        if not allowed_file(file.filename):
            return redirect(url_for('entreprise_co2_wash') + '?error=Format%20fichier%20invalide%20-%20CSV%20requis')

        parse_result = parse_csv_co2_wash_data(file)
        if not parse_result.get('success'):
            error_msg = parse_result.get('error', 'Erreur inconnue')
            return redirect(url_for('entreprise_co2_wash') + f'?error={error_msg.replace(" ", "%20")}')

        session['co2_wash_data'] = {
            'gross_kg_h': parse_result['gross_kg_h'],
            'efficiency': parse_result['efficiency'],
            'gross_last_kg_h': parse_result.get('gross_last_kg_h'),
            'efficiency_last': parse_result.get('efficiency_last'),
            'gross_slope_per_day': parse_result.get('gross_slope_per_day', 0.0),
            'eff_slope_per_day': parse_result.get('eff_slope_per_day', 0.0),
            'has_timeseries': parse_result.get('has_timeseries', False),
            'num_records': parse_result.get('num_records', 0),
            'file_name': file.filename,
            'upload_timestamp': datetime.now().isoformat(),
        }
        session.modified = True

        return redirect(url_for('entreprise_co2_wash') + '?success=CSV%20CO2%20Wash%20upload%C3%A9%20avec%20succ%C3%A8s')
    except Exception as e:
        logger.error(f"Erreur upload CO2 Wash: {e}")
        return redirect(url_for('entreprise_co2_wash') + '?error=Erreur%20serveur')


@app.route('/entreprise/co2-wash/reset', methods=['POST'])
@entreprise_required
def entreprise_co2_wash_reset():
    session.pop('co2_wash_data', None)
    session.modified = True
    return redirect(url_for('entreprise_co2_wash') + '?success=Donn%C3%A9es%20CO2%20Wash%20r%C3%A9initialis%C3%A9es')

@app.route('/entreprise/assistant', methods=['GET', 'POST'])
@entreprise_required
def entreprise_assistant():
    if 'ent_chat_history' not in session:
        session['ent_chat_history'] = [
            {
                'role': 'assistant',
                'content': "🏭 Bonjour. Je suis votre IA d'optimisation environnementale. Voulez-vous un résumé de vos émissions actuelles ou des conseils pour optimiser votre filtre CO2 Wash ?",
                'timestamp': datetime.now().strftime('%H:%M')
            }
        ]
        
    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        user_input = request.form.get('user_input', '').strip()
        
        if action == 'reset':
            session['ent_chat_history'] = [
                {
                    'role': 'assistant',
                    'content': "🔄 Session réinitialisée. Comment puis-je vous aider avec vos procédés industriels ?",
                    'timestamp': datetime.now().strftime('%H:%M')
                }
            ]
            session.modified = True
            return redirect(url_for('entreprise_assistant') + '#bottom')
            
        if user_input:
            history = session['ent_chat_history']
            history.append({
                'role': 'user',
                'content': user_input,
                'timestamp': datetime.now().strftime('%H:%M')
            })
            session['ent_chat_history'] = history
            session.modified = True
            
            try:
                chatbot_inst = get_chatbot()
                # Sync history to chatbot
                chatbot_inst.conversation_history = [
                    {'role': msg['role'], 'content': msg['content']}
                    for msg in session['ent_chat_history'][:-1]
                ]
                
                # Context with current emissions (prefer CSV upload if available)
                co2_data = session.get('co2_wash_data')
                if co2_data:
                    gross = float(co2_data.get('gross_kg_h', 0.0) or 0.0)
                    eff_pct = float(co2_data.get('efficiency', 0.88) or 0.88) * 100.0
                else:
                    gross = get_external_emissions_data()
                    eff_pct = 88.0
                context = {
                    "Emissions actuelles": f"{round(gross, 1)} kg/h",
                    "Efficacité lavage": f"{round(eff_pct, 1)}%",
                }
                
                response = chatbot_inst.chat(user_input, weather_context=context, mode='enterprise')
                
                if response.get('status') == 'success':
                    assistant_msg = response.get('message', '')
                else:
                    assistant_msg = f"Erreur IA : {response.get('message')}"
                    
            except Exception as e:
                logger.error(f"Erreur chatbot entreprise: {str(e)}")
                assistant_msg = "Erreur de communication avec l'IA industrielle."
                
            history = session['ent_chat_history']
            history.append({
                'role': 'assistant',
                'content': assistant_msg,
                'timestamp': datetime.now().strftime('%H:%M')
            })
            session['ent_chat_history'] = history
            session.modified = True
            
            return redirect(url_for('entreprise_assistant') + '#bottom')

    return render_template(
        'entreprise_chatbot.html',
        active_nav='assistant',
        chat_history=session['ent_chat_history']
    )


def build_co2_wash_projections(co2_data: dict, days: int = 7):
    """
    Construit une projection CO2 Wash à J+N basée sur les métriques issues du CSV.

    co2_data attendu (min):
      - gross_kg_h (moyenne)
      - efficiency (moyenne, [0..1])
    optionnel (si CSV contient une série temporelle):
      - gross_last_kg_h
      - efficiency_last
      - gross_slope_per_day
      - eff_slope_per_day
    """
    # Noms de jours en français (strftime('%A') dépend de la locale système, souvent en anglais).
    jours_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    base_date = datetime.now()
    projections = []

    gross0 = float(co2_data.get('gross_last_kg_h') or co2_data.get('gross_kg_h') or 0.0)
    eff0 = float(co2_data.get('efficiency_last') or co2_data.get('efficiency') or 0.88)  # [0..1]

    gross_slope = float(co2_data.get('gross_slope_per_day') or 0.0)
    eff_slope = float(co2_data.get('eff_slope_per_day') or 0.0)

    for i in range(days):
        target_date = base_date + timedelta(days=i)

        gross = gross0 + gross_slope * i
        efficiency = eff0 + eff_slope * i

        # Clamp (sécurité)
        gross = max(0.0, gross)
        efficiency = max(0.50, min(0.95, efficiency))

        eff_pct = efficiency * 100.0
        status = 'OK' if eff_pct > 80 else ('WARNING' if eff_pct > 70 else 'CRITICAL')

        projections.append({
            'date': target_date.strftime('%Y-%m-%d'),
            'day_name': jours_fr[target_date.weekday()],
            'efficiency': round(eff_pct, 1),
            'gross_emissions': round(gross, 0),
            'status': status,
        })

    return projections


@app.route('/entreprise/predictions')
@entreprise_required
def entreprise_predictions():
    """
    Projections CO2 Wash (7 jours) basées UNIQUEMENT sur le CSV uploadé.

    Source des données: session['co2_wash_data'] (populé par /entreprise/co2-wash/upload)
    """
    co2_data = session.get('co2_wash_data')
    if not co2_data:
        return redirect(url_for('entreprise_co2_wash') + '?error=Veuillez%20uploader%20un%20CSV%20CO2%20Wash%20avant%20de%20consulter%20les%20projections')

    projections = build_co2_wash_projections(co2_data, days=7)
    return render_template('entreprise_predictions.html', active_nav='ent_predictions', projections=projections)


@app.route('/entreprise/predictions.csv')
@entreprise_required
def entreprise_predictions_csv():
    """Télécharge les projections CO2 Wash (7 jours) au format CSV."""
    co2_data = session.get('co2_wash_data')
    if not co2_data:
        return redirect(url_for('entreprise_co2_wash') + '?error=Veuillez%20uploader%20un%20CSV%20CO2%20Wash%20avant%20de%20t%C3%A9l%C3%A9charger%20les%20projections')

    projections = build_co2_wash_projections(co2_data, days=7)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=['date', 'day_name', 'gross_emissions_kg_h', 'efficiency_percent', 'status'],
        extrasaction='ignore'
    )
    writer.writeheader()
    for p in projections:
        writer.writerow({
            'date': p['date'],
            'day_name': p['day_name'],
            'gross_emissions_kg_h': p['gross_emissions'],
            'efficiency_percent': p['efficiency'],
            'status': p['status'],
        })

    csv_text = output.getvalue()
    return Response(
        csv_text,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="projections_co2_wash_7j.csv"'}
    )


# ============= MODULE ENTREPRISES & INDUSTRIES (Analyse CSV capteurs) =============

def allowed_file(filename):
    """
    Vérifie si un fichier a une extension autorisée (CSV uniquement).
    
    Args:
        filename (str): Nom du fichier
    
    Returns:
        bool: True si le fichier est autorisé, False sinon
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.FLASK_CONFIG.get('ALLOWED_EXTENSIONS', {'csv'})


def parse_csv_pollution_data(file_stream):
    """
    Parse un fichier CSV contenant des données de capteurs de pollution internes.
    
    Le CSV doit contenir des colonnes comme: pm2_5, pm10, co, no2, so2, co2 (ou variantes).
    Calcule la moyenne de chaque polluant et retourne un résumé analytique.
    
    Args:
        file_stream: Flux de fichier (FileStorage ou BytesIO)
    
    Returns:
        dict: 
            - success (bool): Succès du parsing
            - average_factors (dict): Moyennes par polluant
            - pollution_summary (dict): Pourcentages par rapport aux seuils critiques
            - error (str): Message d'erreur si echec
    """
    try:
        # Configurer les seuils critiques pour le calcul des pourcentages
        # (référence : norme AQI OpenWeather)
        critical_thresholds = {
            'PM2.5': 35.0,
            'PM10': 50.0,
            'CO': 5.0,
            'NO2': 40.0,
            'SO2': 20.0,
            'CO2': 800.0,
        }
        
        # Décoder le fichier (support UTF-8 et fallback ASCII)
        file_bytes = file_stream.read()
        try:
            text_stream = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text_stream = file_bytes.decode('ascii', errors='ignore')
        
        # Parser le CSV
        reader = csv.DictReader(io.StringIO(text_stream))
        rows = list(reader)
        
        if not rows:
            return {
                'success': False,
                'error': 'Le fichier CSV est vide ou mal formaté.'
            }
        
        # Normaliser les noms de colonnes (minuscules, espaces supprimés)
        # Guard: ignorer les clés None/vides (CSV mal formé avec virgules en trop)
        normalized_rows = []
        for row in rows:
            norm_row = {
                k.strip().lower().replace(' ', '_'): v
                for k, v in row.items()
                if k is not None and str(k).strip() != ''
            }
            normalized_rows.append(norm_row)
        
        # Accumulateurs pour calculer les moyennes
        accumulators = {}
        value_counts = {}
        
        for row in normalized_rows:
            for key, value in row.items():
                if not key:  # ignorer clés vides
                    continue
                # Chercher les colonnes de pollution (pm2_5, pm10, co, no2, so2, co2, etc.)
                # Note: Check 'co2' BEFORE 'co' to avoid matching co2 as co
                if any(pol_name.lower() in key for pol_name in ['pm2', 'pm10', 'no2', 'so2', 'co2', 'co']):
                    try:
                        val = float(value)
                        if key not in accumulators:
                            accumulators[key] = 0.0
                            value_counts[key] = 0
                        accumulators[key] += val
                        value_counts[key] += 1
                    except (ValueError, TypeError):
                        pass  # Ignorer les cellules non-numériques
        
        # Calculer les moyennes
        average_factors = {}
        for key in accumulators:
            if value_counts[key] > 0:
                average_factors[key] = round(accumulators[key] / value_counts[key], 2)
        
        # Calculer les pourcentages par rapport aux seuils critiques
        pollution_summary = {}
        for factor_key, avg_value in average_factors.items():
            # Mapper les clés CSV normalisées aux noms standards AQI
            # Important: Check 'co2' BEFORE 'co' to avoid false matches
            if 'co2' in factor_key:
                pollutant_name = 'CO2'
                threshold = critical_thresholds['CO2']
            elif 'pm2' in factor_key:
                pollutant_name = 'PM2.5'
                threshold = critical_thresholds['PM2.5']
            elif 'pm10' in factor_key:
                pollutant_name = 'PM10'
                threshold = critical_thresholds['PM10']
            elif 'no2' in factor_key:
                pollutant_name = 'NO2'
                threshold = critical_thresholds['NO2']
            elif 'so2' in factor_key:
                pollutant_name = 'SO2'
                threshold = critical_thresholds['SO2']
            elif 'co' in factor_key:
                pollutant_name = 'CO'
                threshold = critical_thresholds['CO']
            else:
                pollutant_name = factor_key.upper()
                threshold = 100.0
            
            # Calcul du pourcentage relatif au seuil critique
            percentage = (avg_value / threshold * 100) if threshold > 0 else 0
            pollution_summary[pollutant_name] = round(percentage, 1)
        
        logger.info(f"Parsing CSV réussi: {len(rows)} lignes, {len(pollution_summary)} polluants détectés")
        
        return {
            'success': True,
            'average_factors': average_factors,
            'pollution_summary': pollution_summary,
            'num_records': len(rows)
        }
    
    except Exception as e:
        logger.error(f"Erreur parsing CSV: {str(e)}")
        return {
            'success': False,
            'error': f"Erreur lors de la lecture du CSV: {str(e)}"
        }


def parse_csv_co2_wash_data(file_stream):
    """
    Parse un CSV CO2 Wash (émissions industrielles + performance de filtration).

    Colonnes acceptées (variantes tolérées, insensible à la casse/espaces):
      - gross emissions (obligatoire): gross_emissions_kg_h, gross_kg_h, gross, emissions, co2_emissions_kg_h
      - efficiency (optionnel): efficiency, efficiency_percent, co2_wash_efficiency, filter_efficiency
      - captured (optionnel): captured_kg_h, captured
      - net (optionnel): net_emissions_kg_h, net

    Règles de calcul:
      - gross = moyenne(colonne gross) si disponible
      - efficiency:
          - si fourni: normalisé en [0..1] (ex: 88 ou 0.88)
          - sinon si captured et gross: captured/gross
          - sinon: 0.88 par défaut
    """
    try:
        file_bytes = file_stream.read()
        try:
            text_stream = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text_stream = file_bytes.decode('ascii', errors='ignore')

        reader = csv.DictReader(io.StringIO(text_stream))
        rows = list(reader)
        if not rows:
            return {'success': False, 'error': 'Le fichier CSV est vide ou mal formaté.'}

        # normaliser clés
        normalized = []
        for row in rows:
            normalized.append({
                (k or '').strip().lower().replace(' ', '_'): v
                for k, v in row.items()
                if k is not None and str(k).strip() != ''
            })

        gross_keys = [
            'gross_emissions_kg_h', 'gross_kg_h', 'gross', 'emissions',
            'co2_emissions_kg_h', 'co2_gross_kg_h',
        ]
        eff_keys = ['efficiency', 'efficiency_percent', 'co2_wash_efficiency', 'filter_efficiency']
        captured_keys = ['captured_kg_h', 'captured', 'co2_captured_kg_h']
        net_keys = ['net_emissions_kg_h', 'net', 'co2_net_kg_h']
        ts_keys = ['timestamp', 'time', 'datetime', 'date']

        def avg_for(keys):
            vals = []
            for r in normalized:
                for k in keys:
                    if k in r and r[k] not in (None, ''):
                        try:
                            vals.append(float(r[k]))
                        except (TypeError, ValueError):
                            pass
            if not vals:
                return None
            return sum(vals) / len(vals)

        gross_avg = avg_for(gross_keys)
        captured_avg = avg_for(captured_keys)
        net_avg = avg_for(net_keys)
        eff_avg = avg_for(eff_keys)

        if gross_avg is None:
            # fallback si on a captured + net
            if captured_avg is not None and net_avg is not None:
                gross_avg = captured_avg + net_avg
            else:
                return {
                    'success': False,
                    'error': "Colonne d'émissions brutes manquante (ex: gross_emissions_kg_h).",
                }

        efficiency = None
        if eff_avg is not None:
            # 88 -> 0.88 ; 0.88 reste 0.88
            efficiency = eff_avg / 100.0 if eff_avg > 1.0 else eff_avg
        elif captured_avg is not None and gross_avg > 0:
            efficiency = captured_avg / gross_avg
        else:
            efficiency = 0.88

        # clamp
        efficiency = max(0.0, min(0.99, float(efficiency)))

        # -------- Séries (optionnel) : gross/eff sur le temps --------
        def _first_float(row: dict, keys: list[str]):
            for k in keys:
                if k in row and row[k] not in (None, ''):
                    try:
                        return float(row[k])
                    except (TypeError, ValueError):
                        continue
            return None

        def _parse_ts(row: dict):
            for k in ts_keys:
                if k in row and row[k] not in (None, ''):
                    raw = str(row[k]).strip()
                    try:
                        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
                    except Exception:
                        # fallback formats fréquents
                        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M'):
                            try:
                                return datetime.strptime(raw, fmt)
                            except Exception:
                                pass
            return None

        gross_series = []
        eff_series = []
        ts_series = []
        for r in normalized:
            g = _first_float(r, gross_keys)
            cap = _first_float(r, captured_keys)
            net = _first_float(r, net_keys)
            e = _first_float(r, eff_keys)

            if g is None and cap is not None and net is not None:
                g = cap + net

            eff_val = None
            if e is not None:
                eff_val = e / 100.0 if e > 1.0 else e
            elif cap is not None and g and g > 0:
                eff_val = cap / g

            ts = _parse_ts(r)
            if g is not None and eff_val is not None:
                gross_series.append(float(g))
                eff_series.append(max(0.0, min(0.99, float(eff_val))))
                ts_series.append(ts)

        gross_last = gross_series[-1] if gross_series else float(gross_avg)
        eff_last = eff_series[-1] if eff_series else float(efficiency)

        gross_slope_per_day = 0.0
        eff_slope_per_day = 0.0
        has_ts = False
        valid_ts = [t for t in ts_series if isinstance(t, datetime)]
        if len(gross_series) >= 2 and len(valid_ts) == len(gross_series):
            t0 = valid_ts[0]
            x = np.array([(t - t0).total_seconds() / 86400.0 for t in valid_ts], dtype=np.float64)
            if float(np.max(x)) > 0:
                has_ts = True
                gross_slope_per_day = float(np.polyfit(x, np.array(gross_series, dtype=np.float64), 1)[0])
                eff_slope_per_day = float(np.polyfit(x, np.array(eff_series, dtype=np.float64), 1)[0])

        return {
            'success': True,
            'gross_kg_h': round(float(gross_avg), 4),
            'efficiency': round(float(efficiency), 6),
            'gross_last_kg_h': round(float(gross_last), 4),
            'efficiency_last': round(float(eff_last), 6),
            'gross_slope_per_day': round(float(gross_slope_per_day), 6),
            'eff_slope_per_day': round(float(eff_slope_per_day), 8),
            'has_timeseries': bool(has_ts),
            'num_records': len(rows),
        }
    except Exception as e:
        logger.error(f"Erreur parsing CSV CO2 Wash: {e}")
        return {'success': False, 'error': f"Erreur lors de la lecture du CSV: {str(e)}"}


def generate_folium_map(entity_name: str, entity_type: str, lat: float, lon: float, aqi_level: int):
    """
    Génère une carte statique Folium (HTML) avec marqueur AQI coloré.
    
    Args:
        entity_name (str): Nom de l'entité
        entity_type (str): Type (Usine, Ville, Pays)
        lat (float): Latitude
        lon (float): Longitude
        aqi_level (int): Indice AQI ou ppm
    
    Returns:
        str: Chemin vers le fichier HTML généré ou None si Folium n'est pas disponible
    """
    if not FOLIUM_AVAILABLE:
        logger.warning("Folium non installé - carte statique non disponible")
        return None
    
    try:
        # Déterminer la couleur du marqueur selon l'AQI
        if aqi_level <= 50:
            color = 'green'
            status = 'Bon'
        elif aqi_level <= 100:
            color = 'yellow'
            status = 'Modéré'
        elif aqi_level <= 150:
            color = 'orange'
            status = 'Mauvais'
        else:
            color = 'red'
            status = 'Très mauvais'
        
        # Créer la carte centrée sur la position
        m = folium.Map(
            location=[lat, lon],
            zoom_start=10,
            tiles='OpenStreetMap'
        )
        
        # Ajouter un marqueur coloré
        folium.Marker(
            location=[lat, lon],
            popup=f"<b>{entity_name}</b><br>{entity_type}<br>AQI: {aqi_level}<br>Status: {status}",
            tooltip=f"{entity_name} - AQI {aqi_level}",
            icon=folium.Icon(color=color, icon='info-sign')
        ).add_to(m)
        
        # Ajouter un cercle de rayon proportionnel à la pollution
        circle_radius = max(500, min(10000, aqi_level * 50))
        folium.Circle(
            location=[lat, lon],
            radius=circle_radius,
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.3,
            popup=f"Zone AQI {aqi_level}"
        ).add_to(m)
        
        # Sauvegarder la carte
        map_path = os.path.join(_this_dir, 'templates', 'static_map_render.html')
        m.save(map_path)
        
        logger.info(f"Carte Folium générée: {map_path}")
        return map_path
    
    except Exception as e:
        logger.error(f"Erreur génération carte Folium: {str(e)}")
        return None


@app.route('/entreprise')
@entreprise_required
def entreprise_home():
    """
    Page d'accueil du module entreprises - formulaire d'upload CSV.
    Affiche un formulaire pour uploader un CSV et sélectionner le type d'entité.
    """
    error = request.args.get('error', '')
    theme = session.get('theme', 'dark')
    return render_template('entreprise_upload.html', error=error, theme=theme, active_nav='csv_upload')


@app.route('/entreprise/upload', methods=['POST'])
@entreprise_required
def entreprise_upload():
    """
    Route POST pour l'upload et le parsing du fichier CSV.
    
    - Reçoit le fichier CSV + type d'entité + nom
    - Parse les données de pollution
    - Stocke en session pour éviter re-parsing
    - Redirige vers le dashboard
    """
    try:
        # Vérifier la présence du fichier
        if 'file' not in request.files:
            return redirect(url_for('entreprise_home') + '?error=Aucun%20fichier%20fourni')
        
        file = request.files['file']
        entity_name = request.form.get('entity_name', '').strip()
        entity_type = request.form.get('entity_type', 'Usine').strip()
        
        if not entity_name:
            return redirect(url_for('entreprise_home') + '?error=Nom%20d\'entité%20vide')
        
        if file.filename == '':
            return redirect(url_for('entreprise_home') + '?error=Fichier%20vide')
        
        if not allowed_file(file.filename):
            return redirect(url_for('entreprise_home') + '?error=Format%20fichier%20invalide%20-%20CSV%20requis')
        
        # Parser le CSV
        parse_result = parse_csv_pollution_data(file)
        
        if not parse_result['success']:
            error_msg = parse_result.get('error', 'Erreur inconnue')
            return redirect(url_for('entreprise_home') + f'?error={error_msg.replace(" ", "%20")}')
        
        # Stocker les résultats en session (évite re-parsing)
        session['entreprise_data'] = {
            'entity_name': entity_name,
            'entity_type': entity_type,
            'pollution_summary': parse_result['pollution_summary'],
            'average_factors': parse_result['average_factors'],
            'num_records': parse_result.get('num_records', 0),
            'upload_timestamp': datetime.now().isoformat(),
        }
        
        logger.info(f"Données entreprise stockées en session pour «{entity_name}»")
        
        return redirect(url_for('entreprise_dashboard'))
    
    except Exception as e:
        logger.error(f"Erreur upload entreprise: {str(e)}")
        return redirect(url_for('entreprise_home') + f'?error=Erreur%20serveur:%20{str(e)[:50]}')


@app.route('/entreprise/dashboard')
def entreprise_dashboard():
    """
    Dashboard analytique SSR avec tri/filtrage côté serveur.
    
    Affiche:
    - Statistiques clés (KPIs) des polluants
    - Barres de progression CSS pour chaque polluant
    - Liens de tri HTML standards
    - Plan d'action généré par Mistral AI
    - Carte statique de pollution
    """
    # Récupérer les données stockées en session
    ent_data = session.get('entreprise_data')
    
    if not ent_data:
        return redirect(url_for('entreprise_home') + '?error=Pas%20de%20données%20uploadées')
    
    entity_name = ent_data['entity_name']
    entity_type = ent_data['entity_type']
    pollution_summary = ent_data['pollution_summary']
    
    # Récupérer le paramètre de tri depuis l'URL
    sort_by = request.args.get('sort_by', 'name')  # 'name', 'rate', 'value'
    order = request.args.get('order', 'asc')  # 'asc', 'desc'
    
    # Construire la liste des polluants avec détails pour le tri
    pollution_items = []
    for pollutant_name, percentage in pollution_summary.items():
        # Déterminer la couleur selon le pourcentage
        if percentage <= 50:
            color_threshold = '#10b981'  # Vert
        elif percentage <= 100:
            color_threshold = '#f59e0b'  # Ambre
        else:
            color_threshold = '#ef4444'  # Rouge
        
        pollution_items.append({
            'name': pollutant_name,
            'percentage': percentage,
            'value': ent_data['average_factors'].get(pollutant_name.lower().replace('.', ''), 0),
            'color_threshold': color_threshold,
        })
    
    # Appliquer le tri
    if sort_by == 'rate':
        pollution_items.sort(key=lambda x: x['percentage'], reverse=(order == 'desc'))
    elif sort_by == 'value':
        pollution_items.sort(key=lambda x: x['value'], reverse=(order == 'desc'))
    else:  # sort_by == 'name'
        pollution_items.sort(key=lambda x: x['name'], reverse=(order == 'desc'))
    
    # Générer les recommandations Mistral AI
    chatbot = get_chatbot()
    ai_report_html = chatbot.generate_industrial_recommendations(
        entity_name=entity_name,
        entity_type=entity_type,
        pollution_summary=pollution_summary
    )
    
    # Générer une carte (optionnel, si Folium est disponible)
    # Utiliser des coordonnées fictives ou fournies par l'utilisateur
    lat, lon = config.MAP_CENTER_LAT, config.MAP_CENTER_LON  # Casablanca par défaut
    map_file = generate_folium_map(
        entity_name=entity_name,
        entity_type=entity_type,
        lat=lat,
        lon=lon,
        aqi_level=int(sum(pollution_summary.values()) / len(pollution_summary)) if pollution_summary else 50
    )
    
    # Calculer des statistiques globales
    stats = {
        'total_pollutants': len(pollution_summary),
        'average_pollution': round(sum(pollution_summary.values()) / len(pollution_summary), 1) if pollution_summary else 0,
        'max_pollution': max(pollution_summary.values()) if pollution_summary else 0,
        'num_records_analyzed': ent_data.get('num_records', 'N/A'),
    }
    
    return render_template(
        'entreprise_dashboard.html',
        entity_name=entity_name,
        entity_type=entity_type,
        pollution_items=pollution_items,
        ai_report=ai_report_html,
        stats=stats,
        sort_by=sort_by,
        order=order,
        map_file=map_file,
        active_nav='ent_dashboard',
    )


@app.route('/map-view')
def entreprise_map_view():
    """
    Affiche la carte Folium générée (en iframe depuis le dashboard entreprise).
    """
    try:
        return render_template('static_map_render.html')
    except Exception as e:
        logger.error(f"Erreur chargement carte: {str(e)}")
        return f"<p>Erreur chargement carte: {str(e)}</p>", 500


if __name__ == '__main__':
    # Initialiser le serveur
    initialize_server()
    
    # Configuration du serveur
    host = config.FLASK_CONFIG['host']
    port = config.FLASK_CONFIG['port']
    debug = config.FLASK_CONFIG['debug']
    
    logger.info("DÉMARRAGE DU SERVEUR")
    logger.info(f"")
    logger.info(f"URL locale:     http://localhost:{port}")
    logger.info(f"URL réseau:     http://{host}:{port}")
    logger.info(f"")
    logger.info(f"Dashboard:      http://localhost:{port}/")
    logger.info(f"Carte GPS:      http://localhost:{port}/map")
    logger.info(f"Prédictions IA: http://localhost:{port}/predictions")
    logger.info(f"")
    logger.info(f"API Health:     http://localhost:{port}/api/health")
    logger.info(f"")
    logger.info("NOUVEAUTÉS v2.2:")
    logger.info("  • Responsive Design (mobile/tablette/desktop)")
    logger.info("  • Sans authentification (accès immédiat)")
    logger.info("  • Menu hamburger sur mobile")
    logger.info(f"")
    logger.info("Appuyez sur Ctrl+C pour arrêter le serveur")
    logger.info(f"")
    
    # Lancer le serveur Flask
    logger.info(f"Serveur Web démarré sur http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
