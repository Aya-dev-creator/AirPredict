"""
Configuration centrale du système de surveillance de qualité de l'air
Gère toutes les variables d'environnement et paramètres du système

Ce fichier est le point central de configuration pour toute l'application.
Il charge les variables depuis le fichier .env et fournit des valeurs par défaut.
Chaque section du fichier correspond à un composant du système.
"""
import os  # Module pour accéder aux variables d'environnement du système
from dotenv import load_dotenv  # Bibliothèque pour charger les variables depuis .env

# Charger les variables d'environnement depuis le fichier .env
# Le fichier .env contient les clés API, mots de passe, et configurations sensibles
# qui ne doivent pas être commités dans Git (voir .gitignore)
load_dotenv()

class Config:
    """
    Classe de configuration principale pour tout le système
    
    Cette classe contient tous les paramètres de configuration sous forme de
    dictionnaires et variables de classe. Chaque section correspond à un
    composant du système (base de données, capteurs, web, email, etc.)
    """
    
    # ============= CONFIGURATION BASE DE DONNÉES (SQLite3) =============
    # SQLite est une base de données légère qui stocke tout dans un seul fichier
    # Idéale pour Raspberry Pi car elle ne nécessite pas de serveur séparé
    DB_CONFIG = {
        # Chemin vers le fichier de base de données
        # Par défaut: ./data/air_quality.db (dans le dossier data du projet)
        'db_path': os.getenv('DB_PATH', './data/air_quality.db')
    }
    
    # ============= CONFIGURATION OPENWEATHER (collecte périodique) =============
    WEATHER_DATA_CONFIG = {
        # Intervalle entre deux récupérations API (secondes)
        'read_interval': int(os.getenv(
            'WEATHER_FETCH_INTERVAL',
            os.getenv('SENSOR_READ_INTERVAL', 60),
        )),
    }
    
    # ============= SEUILS DE QUALITÉ DE L'AIR =============
    # Ces seuils définissent les niveaux de qualité de l'air basés sur l'AQI (Air Quality Index)
    # L'AQI est une échelle internationale pour mesurer la pollution atmosphérique
    # Valeurs en PPM (parts per million), dérivées de l'AQI OpenWeather
    AIR_QUALITY_THRESHOLDS = {
        # Seuil pour qualité "Bon" (0-50 PPM)
        # Air satisfaisant, pollution faible ou nulle
        'good': int(os.getenv('THRESHOLD_GOOD', 50)),
        
        # Seuil pour qualité "Modéré" (51-100 PPM)
        # Qualité acceptable, pollution modérée
        'moderate': int(os.getenv('THRESHOLD_MODERATE', 100)),
        
        # Seuil pour qualité "Mauvais pour groupes sensibles" (101-150 PPM)
        # Les personnes sensibles (asthme, allergies) peuvent ressentir des effets
        'unhealthy': int(os.getenv('THRESHOLD_UNHEALTHY', 150)),
        
        # Seuil pour qualité "Mauvais" (151-200 PPM)
        # Tout le monde peut commencer à ressentir des effets
        'very_unhealthy': int(os.getenv('THRESHOLD_VERY_UNHEALTHY', 200)),
        
        # Seuil pour qualité "Très mauvais" (201-300 PPM)
        # Alerte sanitaire, effets plus graves pour la population
        'hazardous': int(os.getenv('THRESHOLD_HAZARDOUS', 300))
    }
    
    # ============= CONFIGURATION SERVEUR WEB =============
    # Configuration du serveur Flask qui fournit l'interface web et l'API REST
    FLASK_CONFIG = {
        # Adresse IP sur laquelle le serveur écoute
        # '0.0.0.0' = écoute sur toutes les interfaces (accessible depuis le réseau)
        # '127.0.0.1' = écoute uniquement en local (localhost)
        'host': os.getenv('FLASK_HOST', '0.0.0.0'),
        
        # Port TCP sur lequel le serveur écoute
        # Par défaut: 5000 (port standard pour Flask en développement)
        'port': int(os.getenv('FLASK_PORT', 5000)),
        
        # Mode debug: active le rechargement automatique et les messages d'erreur détaillés
        # 'true' = mode développement (NE PAS utiliser en production)
        # 'false' = mode production
        'debug': os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        
        # Clé secrète pour sécuriser les sessions Flask
        # DOIT être changée en production pour éviter les attaques
        'secret_key': os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production'),

        # ---- Module Entreprises & Industries ----
        # Extensions de fichiers autorisées pour l'upload (uniquement CSV)
        'ALLOWED_EXTENSIONS': {'csv'},

        # Dossier temporaire de stockage des fichiers CSV uploadés
        # Ce dossier doit exister avant le démarrage du serveur
        'UPLOAD_FOLDER': os.getenv('UPLOAD_FOLDER', './data/uploads')
    }
    
    # ============= LOCALISATION (carte / météo par défaut) =============
    # Ces paramètres définissent la localisation par défaut pour la carte et la météo
    # Centre carte : météo OpenWeather (ville ci-dessous) sauf si MAP_FOLLOW_GPS=true
    WEATHER_DEFAULT_QUERY = os.getenv('WEATHER_DEFAULT_QUERY', 'Casablanca,MA')
    # Coordonnées GPS du centre de la carte (latitude, longitude)
    # Par défaut: Casablanca, Maroc (33.5731°N, 7.5898°W)
    MAP_CENTER_LAT = float(os.getenv('MAP_CENTER_LAT', '33.565318'))
    MAP_CENTER_LON = float(os.getenv('MAP_CENTER_LON', '-7.663939'))
    
    # Si 'true', la carte suit les coordonnées des dernières mesures enregistrées
    MAP_FOLLOW_GPS = os.getenv('MAP_FOLLOW_GPS', 'false').lower() in ('1', 'true', 'yes')
    
    # Distance maximale (en km) entre la position mesurée et le centre de la ville
    MAP_GPS_MAX_DISTANCE_KM = float(os.getenv('MAP_GPS_MAX_DISTANCE_KM', '320'))

    # ============= PARAMÈTRES DU MODÈLE ML =============
    # Configuration pour le modèle de Machine Learning qui prédit la qualité de l'air
    ML_CONFIG = {
        # Chemin vers le fichier du modèle ML entraîné (format pickle)
        # Le modèle est sauvegardé après l'entraînement pour être réutilisé
        'model_path': './models/air_quality_model.pkl',
        
        # Chemin vers le fichier du scaler (normalisation des données)
        # Le scaler transforme les données pour qu'elles soient sur la même échelle
        'scaler_path': './models/scaler.pkl',
        
        # Chemin vers le fichier de données d'entraînement (format CSV)
        # Contient les données historiques utilisées pour entraîner le modèle
        'training_data_path': './data/training_data.csv',
        
        # Intervalle de ré-entraînement du modèle en heures
        # Le modèle est ré-entraîné périodiquement avec les nouvelles données
        # Par défaut: toutes les 24 heures
        'retrain_interval_hours': 24,
        
        # Fenêtre de prédiction en heures
        # Le modèle prédit la qualité de l'air pour les X prochaines heures
        # Par défaut: prédiction sur 24 heures
        'prediction_window_hours': 24
    }

    # ============= CONFIGURATION NASA (Données environnementales) =============
    # Configuration pour l'API NASA EONET (Earth Observatory Natural Event Tracker)
    # Fournit des données sur les événements environnementaux (feux, tempêtes, etc.)
    NASA_CONFIG = {
        # Clé API pour accéder à l'API NASA
        # Essayez d'abord la variable standard NASA_API_KEY, puis l'ancienne variable nasaapi
        # Si aucune n'est configurée, la chaîne vide est utilisée (pas d'accès à l'API)
        'api_key': os.getenv('NASA_API_KEY', os.getenv('nasaapi', ''))
    }
    

    
    @staticmethod
    def get_air_quality_level(value):
        """
        Détermine le niveau de qualité de l'air basé sur la valeur mesurée
        
        Args:
            value (float): Indice qualité de l'air (PPM, dérivé de l'AQI)
        
        Returns:
            dict: Niveau, couleur et description de la qualité
        """
        try:
            value = float(value) if value is not None else 0
        except (TypeError, ValueError):
            value = 0
        thresholds = Config.AIR_QUALITY_THRESHOLDS
        
        if value <= thresholds['good']:
            return {
                'level': 'Bon',
                'color': '#00E400',
                'description': 'Qualité de l\'air satisfaisante, pollution faible ou nulle'
            }
        elif value <= thresholds['moderate']:
            return {
                'level': 'Modéré',
                'color': '#B45309',
                'description': 'Qualité acceptable, pollution modérée'
            }
        elif value <= thresholds['unhealthy']:
            return {
                'level': 'Mauvais pour groupes sensibles',
                'color': '#FF7E00',
                'description': 'Les personnes sensibles peuvent ressentir des effets'
            }
        elif value <= thresholds['very_unhealthy']:
            return {
                'level': 'Mauvais',
                'color': '#FF0000',
                'description': 'Tout le monde peut commencer à ressentir des effets'
            }
        elif value <= thresholds['hazardous']:
            return {
                'level': 'Très mauvais',
                'color': '#8F3F97',
                'description': 'Alerte sanitaire, effets plus graves'
            }
        else:
            return {
                'level': 'Dangereux',
                'color': '#7E0023',
                'description': 'Alerte d\'urgence, toute la population est affectée'
            }

# Instance globale de configuration
config = Config()
