"""
Configuration centrale du système de surveillance de qualité de l'air
Gère toutes les variables d'environnement et paramètres du système
"""
import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

class Config:
    """Classe de configuration principale pour tout le système"""
    
    # ============= CONFIGURATION BASE DE DONNÉES (SQLite3) =============
    DB_CONFIG = {
        'db_path': os.getenv('DB_PATH', './data/air_quality.db')
    }
    
    # ============= CONFIGURATION DES CAPTEURS (GPIO) =============
    SENSOR_CONFIG = {
        'dht11_pin': int(os.getenv('DHT11_PIN', 4)),
        'mq135_pin': int(os.getenv('MQ135_PIN', 17)),
        'gps_enabled': os.getenv('GPS_ENABLED', 'true').lower() == 'true',
        'read_interval': int(os.getenv('SENSOR_READ_INTERVAL', 60))
    }
    
    # ============= SEUILS DE QUALITÉ DE L'AIR =============
    # Basés sur l'indice de qualité de l'air (AQI)
    AIR_QUALITY_THRESHOLDS = {
        'good': int(os.getenv('THRESHOLD_GOOD', 50)),
        'moderate': int(os.getenv('THRESHOLD_MODERATE', 100)),
        'unhealthy': int(os.getenv('THRESHOLD_UNHEALTHY', 150)),
        'very_unhealthy': int(os.getenv('THRESHOLD_VERY_UNHEALTHY', 200)),
        'hazardous': int(os.getenv('THRESHOLD_HAZARDOUS', 300))
    }
    
    # ============= CONFIGURATION SERVEUR WEB =============
    FLASK_CONFIG = {
        'host': os.getenv('FLASK_HOST', '0.0.0.0'),
        'port': int(os.getenv('FLASK_PORT', 5000)),
        'debug': os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        'secret_key': os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    }
    
    # ============= CONFIGURATION EMAIL (ALERTES) =============
    EMAIL_CONFIG = {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', 587)),
        'username': os.getenv('SMTP_USERNAME', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'alert_email': os.getenv('ALERT_EMAIL', ''),
        'enabled': bool(os.getenv('SMTP_USERNAME'))
    }
    
    # ============= LOCALISATION (carte / météo par défaut) =============
    # Centre carte : météo OpenWeather (ville ci-dessous) sauf si MAP_FOLLOW_GPS=true
    WEATHER_DEFAULT_QUERY = os.getenv('WEATHER_DEFAULT_QUERY', 'Casablanca,MA')
    MAP_CENTER_LAT = float(os.getenv('MAP_CENTER_LAT', '33.5731'))
    MAP_CENTER_LON = float(os.getenv('MAP_CENTER_LON', '-7.5898'))
    # true = toujours centrer sur le GPS capteur (même si incohérent)
    MAP_FOLLOW_GPS = os.getenv('MAP_FOLLOW_GPS', 'false').lower() in ('1', 'true', 'yes')
    # Si le GPS est à plus de X km du centre météo / ville, on ignore le GPS (ex. faux fix Tunis)
    MAP_GPS_MAX_DISTANCE_KM = float(os.getenv('MAP_GPS_MAX_DISTANCE_KM', '320'))

    # ============= PARAMÈTRES DU MODÈLE ML =============
    ML_CONFIG = {
        'model_path': './models/air_quality_model.pkl',
        'scaler_path': './models/scaler.pkl',
        'training_data_path': './data/training_data.csv',
        'retrain_interval_hours': 24,
        'prediction_window_hours': 24
    }

    # ============= CONFIGURATION NASA (Données environnementales) =============
    NASA_CONFIG = {
        # Essayez d'abord une variable standard, puis retombez sur l'entrée existante du .env
        'api_key': os.getenv('NASA_API_KEY', os.getenv('nasaapi', ''))
    }
    
    # ============= CONFIGURATION HUGGING FACE (Assistant IA) =============
    # Modèle : carte Hub « Inference » / petits instruct (voir https://huggingface.co/models )
    # Défaut : SmolLM2-1.7B-Instruct — léger, adapté au routeur serverless HF.
    HF_CONFIG = {
        'api_key': os.getenv('HF_API_KEY', ''),
        'chat_model': os.getenv(
            'HF_CHAT_MODEL',
            'HuggingFaceTB/SmolLM2-1.7B-Instruct',
        ),
        'chat_url': os.getenv(
            'HF_CHAT_URL',
            'https://router.huggingface.co/v1/chat/completions',
        ),
    }

    # ============= OPENAI (repli assistant si Hugging Face renvoie 404 / erreur) =============
    OPENAI_CONFIG = {
        'api_key': os.getenv('OPENAI_API_KEY', ''),
        'chat_model': os.getenv('OPENAI_CHAT_MODEL', 'gpt-4o-mini'),
        'chat_url': os.getenv(
            'OPENAI_CHAT_URL',
            'https://api.openai.com/v1/chat/completions',
        ),
    }

    # Groq (API compatible OpenAI, compte gratuit sur console.groq.com) — utile si HF renvoie 404
    GROQ_CONFIG = {
        'api_key': os.getenv('GROQ_API_KEY', ''),
        'chat_model': os.getenv('GROQ_CHAT_MODEL', 'llama-3.1-70b-versatile'),
        'chat_url': os.getenv(
            'GROQ_CHAT_URL',
            'https://api.groq.com/openai/v1/chat/completions',
        ),
    }
    
    @staticmethod
    def get_air_quality_level(value):
        """
        Détermine le niveau de qualité de l'air basé sur la valeur mesurée
        
        Args:
            value (float): Valeur mesurée par le capteur MQ-135 (PPM)
        
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
                'color': '#FFFF00',
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