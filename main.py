#!/usr/bin/env python3
"""
Système Principal de Surveillance et Prédiction de la Qualité de l'Air
Projet PFE - Raspberry Pi 4 + IoT + Machine Learning

Ce script orchestre tous les composants du système:
- Lecture des capteurs (MQ-135, DHT11, GPS)
- Stockage en base de données SQLite3
- Prédictions ML
- Alertes en temps réel
- Alertes en temps réel
- Serveur web pour visualisation

Auteur: Projet PFE 2024
"""
import sys
import time
import signal
import logging
import schedule
import threading
from datetime import datetime

# Imports des modules du projet
from config import config
from database import AirQualityDatabase
from sensors2 import SensorManager
from ml_model import AirQualityPredictor, generate_synthetic_training_data
# from iot_cloud import IoTCloudManager
from alert_system import AlertSystem

# Import du serveur web (optionnel)
try:
    from web_server import app, initialize_server
    WEB_SERVER_AVAILABLE = True
except ImportError:
    WEB_SERVER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠ Module web_server non disponible - Interface web désactivée")

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('air_quality_system.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class AirQualitySystem:
    """
    Classe principale qui orchestre tout le système de surveillance
    """
    
    def __init__(self):
        """Initialise tous les composants du système"""
        logger.info("="*60)
        logger.info("🚀 DÉMARRAGE DU SYSTÈME DE SURVEILLANCE DE QUALITÉ DE L'AIR")
        logger.info("="*60)
        
        # Variables de contrôle
        self.running = False
        self.web_server_thread = None
        
        # Initialiser les composants
        try:
            # Base de données SQLite3
            logger.info("📊 Initialisation de la base de données SQLite3...")
            db_path = config.DB_CONFIG['db_path']
            self.db = AirQualityDatabase(db_path=db_path)
            if self.db.connect():
                self.db.create_tables()
                logger.info(f"✓ Base de données prête: {db_path}")
            else:
                logger.error("✗ Échec connexion base de données")
            
            # Capteurs
            logger.info("🔌 Initialisation des capteurs...")
            self.sensors = SensorManager(
                mq135_pin=config.SENSOR_CONFIG['mq135_pin'],
                dht11_pin=config.SENSOR_CONFIG['dht11_pin'],
                gps_enabled=config.SENSOR_CONFIG['gps_enabled']
            )
            logger.info("✓ Capteurs initialisés")
            
            # Modèle ML
            logger.info("🤖 Initialisation du modèle ML...")
            self.predictor = AirQualityPredictor()
            
            # Charger ou entraîner le modèle
            if not self.predictor.load_model():
                logger.warning("⚠ Modèle non trouvé - Entraînement avec données synthétiques...")
                training_data = generate_synthetic_training_data(num_samples=2000)
                self.predictor.train_model(training_data)
            
            logger.info("✓ Modèle ML prêt")
            
            # Cloud IoT désactivé (Hébergement Cloudflare)
            self.iot = None
            
            # Système d'alertes
            logger.info("⚠️ Initialisation système d'alertes...")
            self.alert_system = AlertSystem(db_manager=self.db, iot_manager=self.iot)
            logger.info("✓ Système d'alertes prêt")
            
            logger.info("="*60)
            logger.info("✓ TOUS LES COMPOSANTS SONT INITIALISÉS")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'initialisation: {e}")
            raise
    
    def read_and_process_sensors(self):
        """
        Lit tous les capteurs et traite les données
        Cette fonction est appelée périodiquement
        """
        try:
            logger.info("\n" + "="*60)
            logger.info("📊 CYCLE DE LECTURE DES CAPTEURS")
            logger.info("="*60)
            
            # Lire tous les capteurs
            sensor_data = self.sensors.read_all_sensors()
            
            if not sensor_data:
                logger.error("✗ Échec lecture capteurs")
                return
            
            # Extraire les données
            air_quality = sensor_data['air_quality']['ppm']
            temperature = sensor_data['temperature']
            humidity = sensor_data['humidity']
            location = sensor_data.get('location')
            
            latitude = location['latitude'] if location else None
            longitude = location['longitude'] if location else None
            
            logger.info(f"📊 Qualité air: {air_quality:.2f} PPM")
            logger.info(f"🌡️ Température: {temperature}°C")
            logger.info(f"💧 Humidité: {humidity}%")
            if latitude and longitude:
                logger.info(f"📍 Position: {latitude:.6f}, {longitude:.6f}")
            
            # Enregistrer dans la base de données
            record_id = self.db.insert_sensor_data(
                air_quality=air_quality,
                temperature=temperature,
                humidity=humidity,
                latitude=latitude,
                longitude=longitude
            )
            
            if record_id:
                logger.info(f"✓ Données enregistrées (ID: {record_id})")
            
            # Publication cloud désactivée
            
            # Diffuser aux clients web désactivé (No-JS)
            if WEB_SERVER_AVAILABLE:
                logger.debug("✓ Données prêtes pour interface web (SSR)")
            
            # Vérifier les seuils et déclencher des alertes
            alerts = self.alert_system.check_air_quality(
                air_quality_value=air_quality,
                location={'latitude': latitude, 'longitude': longitude}
            )
            
            if alerts:
                logger.warning(f"⚠️ {len(alerts)} alerte(s) déclenchée(s)")
                if WEB_SERVER_AVAILABLE:
                    logger.warning("⚠️ Alerte générée (SSR)")
            
            logger.info("="*60)
            logger.info("✓ CYCLE TERMINÉ\n")
            
        except Exception as e:
            logger.error(f"✗ Erreur traitement capteurs: {e}")
    
    def make_predictions(self):
        """
        Fait des prédictions ML et détecte les pics futurs
        Cette fonction est appelée périodiquement (moins fréquemment)
        """
        try:
            logger.info("\n" + "="*60)
            logger.info("🔮 GÉNÉRATION DES PRÉDICTIONS ML")
            logger.info("="*60)
            
            # Récupérer les dernières données
            latest_readings = self.db.get_latest_readings(limit=1)
            
            if not latest_readings:
                logger.warning("⚠ Pas de données pour faire des prédictions")
                return
            
            current_data = {
                'air_quality_ppm': latest_readings[0]['air_quality_ppm'],
                'temperature': latest_readings[0]['temperature'],
                'humidity': latest_readings[0]['humidity']
            }
            
            # Faire des prédictions pour les 24 prochaines heures
            predictions = self.predictor.predict(current_data, hours_ahead=24)
            
            # Détecter les pics de pollution
            peaks = self.predictor.detect_pollution_peak(predictions)
            
            if peaks:
                logger.warning(f"⚠️ {len(peaks)} pic(s) de pollution prévu(s)")
                # Créer des alertes pour les pics prévus
                alerts = self.alert_system.check_predictions(predictions)
                pass
            else:
                logger.info("✓ Aucun pic de pollution prévu")
            
            # Enregistrer quelques prédictions clés dans la DB
            for i in [0, 6, 12, 18, 23]:  # Prédictions toutes les 6h
                if i < len(predictions):
                    pred = predictions[i]
                    self.db.insert_prediction(
                        predicted_for=datetime.fromisoformat(pred['timestamp']),
                        predicted_aqi=pred['predicted_aqi'],
                        confidence=pred['confidence'],
                        model_version='RF_v1.0'
                    )
            
            # Publication cloud désactivée
            
            logger.info("="*60)
            logger.info("✓ PRÉDICTIONS TERMINÉES\n")
            
        except Exception as e:
            logger.error(f"✗ Erreur génération prédictions: {e}")
    
    def send_daily_summary(self):
        """Envoie un résumé quotidien par email"""
        try:
            logger.info("📧 Génération du résumé quotidien...")
            statistics = self.db.get_statistics(hours=24)
            
            if statistics:
                self.alert_system.send_daily_summary(statistics)
                logger.info("✓ Résumé quotidien envoyé")
            else:
                logger.warning("⚠ Pas de données pour le résumé")
                
        except Exception as e:
            logger.error(f"✗ Erreur envoi résumé: {e}")
    
    def schedule_tasks(self):
        """Configure les tâches planifiées"""
        logger.info("⏰ Configuration des tâches planifiées...")
        
        # Lecture des capteurs toutes les X secondes (configuré dans .env)
        interval = config.SENSOR_CONFIG['read_interval']
        schedule.every(interval).seconds.do(self.read_and_process_sensors)
        logger.info(f"  ✓ Lecture capteurs: toutes les {interval}s")
        
        # Prédictions ML toutes les heures
        schedule.every().hour.do(self.make_predictions)
        logger.info("  ✓ Prédictions ML: toutes les heures")
        
        # Nettoyage des anciennes alertes toutes les 6 heures
        schedule.every(6).hours.do(lambda: self.alert_system.clear_old_alerts())
        logger.info("  ✓ Nettoyage alertes: toutes les 6h")
        
        # Résumé quotidien à 8h du matin
        schedule.every().day.at("08:00").do(self.send_daily_summary)
        logger.info("  ✓ Résumé quotidien: 8h00")
    
    def start_web_server(self):
        """Démarre le serveur web Flask dans un thread séparé"""
        if not WEB_SERVER_AVAILABLE:
            logger.warning("⚠ Module web_server non disponible - Serveur web non démarré")
            return
        
        try:
            logger.info("🌐 Démarrage du serveur web...")
            
            # Initialiser le serveur web avec la base de données existante
            initialize_server()
            
            def run_server():
                host = config.FLASK_CONFIG['host']
                port = config.FLASK_CONFIG['port']
                logger.info(f"✓ Serveur web démarré sur http://{host}:{port}")
                logger.info(f"📱 Accessible depuis n'importe quel appareil sur le réseau")
                logger.info(f"🌍 Interface web: http://{host}:{port}/")
                app.run(
                    host=host,
                    port=port,
                    debug=False
                )
            
            self.web_server_thread = threading.Thread(target=run_server, daemon=True)
            self.web_server_thread.start()
            
            # Attendre que le serveur démarre
            time.sleep(2)
            logger.info("✓ Serveur web opérationnel")
            
        except Exception as e:
            logger.error(f"✗ Erreur démarrage serveur web: {e}")
    
    def run(self):
        """Boucle principale du système"""
        logger.info("\n" + "="*60)
        logger.info("▶️ DÉMARRAGE DU SYSTÈME")
        logger.info("="*60)
        
        self.running = True
        
        # Configurer les tâches planifiées
        self.schedule_tasks()
        
        # Démarrer le serveur web
        self.start_web_server()
        
        # Faire une première lecture immédiate
        logger.info("📊 Lecture initiale des capteurs...")
        self.read_and_process_sensors()
        
        # Faire des prédictions initiales
        logger.info("🔮 Prédictions initiales...")
        self.make_predictions()
        
        logger.info("\n" + "="*60)
        logger.info("✓ SYSTÈME OPÉRATIONNEL")
        logger.info("="*60)
        logger.info("Appuyez sur Ctrl+C pour arrêter le système\n")
        
        # Boucle principale
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n⚠️ Arrêt demandé par l'utilisateur")
            self.stop()
    
    def stop(self):
        """Arrête proprement le système"""
        logger.info("\n" + "="*60)
        logger.info("🛑 ARRÊT DU SYSTÈME")
        logger.info("="*60)
        
        self.running = False
        
        # Nettoyer les ressources
        logger.info("🧹 Nettoyage des ressources...")
        
        if self.sensors:
            self.sensors.cleanup()
            logger.info("✓ Capteurs nettoyés")
        
        # if self.iot:
        #     self.iot.disconnect()
        #     logger.info("✓ Cloud déconnecté")
        
        if self.db:
            self.db.close()
            logger.info("✓ Base de données fermée")
        
        logger.info("="*60)
        logger.info("✓ SYSTÈME ARRÊTÉ")
        logger.info("="*60)


# ============================================
# Point d'entrée principal
# ============================================

def signal_handler(sig, frame):
    """Gère les signaux d'arrêt (Ctrl+C)"""
    logger.info("\n⚠️ Signal d'arrêt reçu")
    sys.exit(0)


if __name__ == "__main__":
    # Configurer le gestionnaire de signaux
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Créer et démarrer le système
        system = AirQualitySystem()
        system.run()
        
    except Exception as e:
        logger.error(f"✗ Erreur fatale: {e}")
        sys.exit(1)