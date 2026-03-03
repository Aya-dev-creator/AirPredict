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
    
    # ============= CONFIGURATION MQTT/IoT =============
    MQTT_CONFIG = {
        'broker': os.getenv('MQTT_BROKER', 'broker.hivemq.com'),
        'port': int(os.getenv('MQTT_PORT', 1883)),
        'topic': os.getenv('MQTT_TOPIC', 'air_quality/sensor_data'),
        'client_id': os.getenv('MQTT_CLIENT_ID', 'raspberry_pi_air_sensor'),
        'username': os.getenv('MQTT_USERNAME', ''),
        'password': os.getenv('MQTT_PASSWORD', ''),
        'keepalive': 60
    }
    
    # ============= CONFIGURATION AWS IoT (Optionnel) =============
    AWS_IOT_CONFIG = {
        'endpoint': os.getenv('AWS_IOT_ENDPOINT', ''),
        'client_id': os.getenv('AWS_IOT_CLIENT_ID', 'raspberry_pi_sensor'),
        'cert_path': os.getenv('AWS_IOT_CERT_PATH', ''),
        'key_path': os.getenv('AWS_IOT_KEY_PATH', ''),
        'root_ca_path': os.getenv('AWS_IOT_ROOT_CA_PATH', '')
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