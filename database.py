"""
Module de gestion de la base de données SQLite3
Gère toutes les opérations CRUD pour les données de qualité de l'air
"""
import sqlite3
from datetime import datetime, timedelta
import logging
from config import config

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AirQualityDatabase:
    """Classe pour gérer toutes les interactions avec la base de données"""
    
    def __init__(self, db_path='air_quality.db'):
        """
        Initialise la connexion à la base de données
        Args:
            db_path (str): Chemin vers le fichier de base de données SQLite
        """
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """Établit la connexion à la base de données SQLite"""
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            # Activer les clés étrangères
            self.connection.execute("PRAGMA foreign_keys = ON")
            # Retourner les résultats comme dictionnaires
            self.connection.row_factory = sqlite3.Row
            logger.info("✓ Connexion à la base de données établie avec succès")
            return True
        except Exception as e:
            logger.error(f"✗ Erreur de connexion à la base de données: {e}")
            return False
    
    def create_tables(self):
        """
        Crée toutes les tables nécessaires pour le système
        Tables: sensor_data, predictions, alerts, calibration
        """
        try:
            cursor = self.connection.cursor()
            
            # Table principale des données capteurs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    air_quality_ppm REAL NOT NULL,
                    temperature REAL NOT NULL,
                    humidity REAL NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    air_quality_level TEXT,
                    air_quality_color TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table des prédictions ML
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_time TIMESTAMP NOT NULL,
                    predicted_for TIMESTAMP NOT NULL,
                    predicted_aqi REAL NOT NULL,
                    confidence_score REAL,
                    model_version TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Table des alertes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    air_quality_value REAL,
                    latitude REAL,
                    longitude REAL,
                    resolved INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP
                );
            """)
            
            # Table de calibration des capteurs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calibration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_type TEXT NOT NULL,
                    calibration_factor REAL NOT NULL,
                    offset REAL DEFAULT 0,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Créer des index pour améliorer les performances
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sensor_timestamp
                ON sensor_data(timestamp DESC);
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_predictions_time
                ON predictions(predicted_for DESC);
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_created
                ON alerts(created_at DESC);
            """)
            
            self.connection.commit()
            logger.info("✓ Toutes les tables ont été créées avec succès")
            return True
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la création des tables: {e}")
            self.connection.rollback()
            return False
    
    def upsert_user(self, name, email):
        """
        Crée ou met à jour un utilisateur (identifié par email).
        
        Args:
            name (str): Nom complet de l'utilisateur
            email (str): Adresse email (unique)
        
        Returns:
            int: ID de l'utilisateur inséré ou mis à jour
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            cursor.execute("""
                INSERT INTO users (name, email)
                VALUES (?, ?)
                ON CONFLICT(email) DO UPDATE SET name=excluded.name;
            """, (name, email))
            
            self.connection.commit()
            user_id = cursor.lastrowid
            logger.info(f"✓ Utilisateur enregistré/ajouté: {email}")
            return user_id
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'enregistrement de l'utilisateur: {e}")
            self.connection.rollback()
            return None
    
    def insert_sensor_data(self, air_quality, temperature, humidity, latitude=None, longitude=None):
        """
        Insère une nouvelle lecture de capteur dans la base de données
        
        Args:
            air_quality (float): Valeur du capteur MQ-135 (PPM)
            temperature (float): Température en °C
            humidity (float): Humidité en %
            latitude (float): Latitude GPS (optionnel)
            longitude (float): Longitude GPS (optionnel)
        
        Returns:
            int: ID de l'enregistrement inséré, ou None si erreur
        """
        try:
            cursor = self.connection.cursor()
            
            # Déterminer le niveau de qualité de l'air
            quality_info = config.get_air_quality_level(air_quality)
            
            query = """
                INSERT INTO sensor_data
                (air_quality_ppm, temperature, humidity, latitude, longitude,
                 air_quality_level, air_quality_color)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """
            
            cursor.execute(query, (
                air_quality,
                temperature,
                humidity,
                latitude,
                longitude,
                quality_info['level'],
                quality_info['color']
            ))
            
            record_id = cursor.lastrowid
            self.connection.commit()
            
            logger.info(f"✓ Données capteur insérées avec ID: {record_id}")
            return record_id
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'insertion des données: {e}")
            self.connection.rollback()
            return None
    
    def get_latest_readings(self, limit=10):
        """
        Récupère les dernières lectures des capteurs
        
        Args:
            limit (int): Nombre de lectures à récupérer
        
        Returns:
            list: Liste des dernières lectures
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                SELECT * FROM sensor_data
                ORDER BY timestamp DESC
                LIMIT ?;
            """
            
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la récupération des données: {e}")
            return []
    
    def get_readings_by_timerange(self, start_time, end_time):
        """
        Récupère les lectures dans un intervalle de temps
        
        Args:
            start_time (datetime): Début de l'intervalle
            end_time (datetime): Fin de l'intervalle
        
        Returns:
            list: Liste des lectures dans l'intervalle
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                SELECT * FROM sensor_data
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC;
            """
            
            cursor.execute(query, (start_time, end_time))
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la récupération par intervalle: {e}")
            return []
    
    def get_statistics(self, hours=24):
        """
        Calcule des statistiques sur les dernières heures
        
        Args:
            hours (int): Nombre d'heures à analyser
        
        Returns:
            dict: Statistiques (moyenne, min, max, etc.)
        """
        try:
            cursor = self.connection.cursor()
            start_time = datetime.now() - timedelta(hours=hours)
            
            query = """
                SELECT
                    AVG(air_quality_ppm) as avg_aqi,
                    MIN(air_quality_ppm) as min_aqi,
                    MAX(air_quality_ppm) as max_aqi,
                    AVG(temperature) as avg_temp,
                    AVG(humidity) as avg_humidity,
                    COUNT(*) as total_readings
                FROM sensor_data
                WHERE timestamp >= ?;
            """
            
            cursor.execute(query, (start_time,))
            result = cursor.fetchone()
            
            return dict(result) if result else {}
            
        except Exception as e:
            logger.error(f"✗ Erreur lors du calcul des statistiques: {e}")
            return {}
    
    def insert_prediction(self, predicted_for, predicted_aqi, confidence, model_version):
        """
        Insère une prédiction ML dans la base de données
        
        Args:
            predicted_for (datetime): Heure pour laquelle la prédiction est faite
            predicted_aqi (float): Valeur AQI prédite
            confidence (float): Score de confiance du modèle
            model_version (str): Version du modèle utilisé
        
        Returns:
            int: ID de la prédiction insérée
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                INSERT INTO predictions
                (prediction_time, predicted_for, predicted_aqi, confidence_score, model_version)
                VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?);
            """
            
            cursor.execute(query, (predicted_for, predicted_aqi, confidence, model_version))
            prediction_id = cursor.lastrowid
            self.connection.commit()
            
            logger.info(f"✓ Prédiction insérée avec ID: {prediction_id}")
            return prediction_id
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'insertion de la prédiction: {e}")
            self.connection.rollback()
            return None
    
    def insert_alert(self, alert_type, severity, message, air_quality_value=None, lat=None, lon=None):
        """
        Insère une alerte dans la base de données
        
        Args:
            alert_type (str): Type d'alerte (ex: 'HIGH_POLLUTION', 'SENSOR_ERROR')
            severity (str): Sévérité ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
            message (str): Message descriptif de l'alerte
            air_quality_value (float): Valeur qui a déclenché l'alerte
            lat (float): Latitude
            lon (float): Longitude
        
        Returns:
            int: ID de l'alerte insérée
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                INSERT INTO alerts
                (alert_type, severity, message, air_quality_value, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?);
            """
            
            cursor.execute(query, (alert_type, severity, message, air_quality_value, lat, lon))
            alert_id = cursor.lastrowid
            self.connection.commit()
            
            logger.info(f"✓ Alerte créée avec ID: {alert_id} - Sévérité: {severity}")
            return alert_id
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la création de l'alerte: {e}")
            self.connection.rollback()
            return None
    
    def get_active_alerts(self):
        """
        Récupère toutes les alertes actives (non résolues)
        
        Returns:
            list: Liste des alertes actives
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                SELECT * FROM alerts
                WHERE resolved = 0
                ORDER BY created_at DESC;
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la récupération des alertes: {e}")
            return []
    
    def get_recent_alerts(self, limit=10):
        """Récupère les alertes les plus récentes (résolues ou non)"""
        try:
            cursor = self.connection.cursor()
            query = """
                SELECT * FROM alerts
                ORDER BY created_at DESC
                LIMIT ?;
            """
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"✗ Erreur get_recent_alerts: {e}")
            return []
    
    def resolve_alert(self, alert_id):
        """
        Marque une alerte comme résolue
        
        Args:
            alert_id (int): ID de l'alerte à résoudre
        
        Returns:
            bool: True si succès, False sinon
        """
        try:
            cursor = self.connection.cursor()
            
            query = """
                UPDATE alerts
                SET resolved = 1, resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """
            
            cursor.execute(query, (alert_id,))
            self.connection.commit()
            
            logger.info(f"✓ Alerte {alert_id} marquée comme résolue")
            return True
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de la résolution de l'alerte: {e}")
            self.connection.rollback()
            return False
    
    def close(self):
        """Ferme la connexion à la base de données"""
        if self.connection:
            self.connection.close()
            logger.info("✓ Connexion à la base de données fermée")

# Instance globale de la base de données
db = AirQualityDatabase()