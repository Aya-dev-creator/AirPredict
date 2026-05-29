#!/usr/bin/env python3
"""
Système Principal de Surveillance et Prédiction de la Qualité de l'Air
Projet PFE - OpenWeather API + Machine Learning

Ce script est le point d'entrée principal du système. Il orchestre tous les composants:
- Récupération des données depuis l'API OpenWeatherMap (qualité de l'air + météo)
- Stockage des données en base de données SQLite3
- Prédictions ML avec RandomForest pour anticiper la qualité de l'air
- Système d'alertes en temps réel stockées en base de données
- Serveur web Flask pour visualisation des données (interface SSR sans JavaScript)

Architecture:
1. AirQualitySystem: Classe principale qui gère tous les composants
2. Tâches planifiées: Récupération données API, prédictions ML, nettoyage alertes, résumé quotidien
3. Thread séparé: Serveur web Flask tourne en parallèle
4. Gestion propre de l'arrêt: Nettoyage des ressources sur Ctrl+C

Auteur: Projet PFE 2024
"""

# ============= IMPORTS STANDARD =============
import sys  # Module système pour les arguments de ligne de commande et la sortie du programme
import time  # Module pour les pauses et le temps (time.sleep)
import signal  # Module pour gérer les signaux système (Ctrl+C)
import logging  # Module pour la journalisation (logs) du système
import schedule  # Bibliothèque pour planifier des tâches périodiques
import threading  # Module pour exécuter le serveur web dans un thread séparé
from datetime import datetime  # Module pour manipuler les dates et heures

# ============= IMPORTS DES MODULES DU PROJET =============
from config import config  # Configuration centrale (variables d'environnement, seuils, etc.)
from database import AirQualityDatabase  # Gestion de la base de données SQLite3
from openweather_data_provider import OpenWeatherDataProvider
from ml_model import AirQualityPredictor, generate_synthetic_training_data  # Modèle ML de prédiction
# from iot_cloud import IoTCloudManager  # Gestion MQTT pour le cloud IoT (désactivé)
# from alert_system import AlertSystem  # Système d'alertes par email et MQTT (désactivé)

# ============= IMPORT DU SERVEUR WEB (OPTIONNEL) =============
# Le serveur web est optionnel car il nécessite des dépendances supplémentaires
# Si l'import échoue, le système fonctionne quand même mais sans interface web
try:
    from web_server import app, initialize_server
    WEB_SERVER_AVAILABLE = True
except ImportError:
    WEB_SERVER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Module web_server non disponible - Interface web désactivée")

# ============= CONFIGURATION DU LOGGING =============
# Le logging permet de suivre ce que fait le système et de détecter les erreurs
# Les logs sont écrits dans un fichier et affichés dans la console
logging.basicConfig(
    level=logging.INFO,  # Niveau de log: INFO (normal), DEBUG (détaillé), WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Format des messages de log
    handlers=[
        logging.FileHandler('air_quality_system.log'),  # Écriture dans un fichier
        logging.StreamHandler(sys.stdout)  # Affichage dans la console
    ]
)
logger = logging.getLogger(__name__)  # Création du logger pour ce module


class AirQualitySystem:
    """
    Classe principale qui orchestre tout le système de surveillance
    
    Cette classe est le cœur du système. Elle initialise et coordonne tous les composants:
    - Base de données pour le stockage
    - OpenWeather API pour la collecte de données
    - Modèle ML pour les prédictions
    - Système d'alertes pour les notifications
    - Serveur web pour l'interface utilisateur
    
    Méthodes principales:
    - __init__: Initialisation de tous les composants
    - read_and_process_weather: Lecture et traitement des données OpenWeather
    - make_predictions: Génération des prédictions ML
    - schedule_tasks: Configuration des tâches planifiées
    - start_web_server: Démarrage du serveur web
    - run: Boucle principale du système
    - stop: Arrêt propre du système
    """
    
    def __init__(self):
        """
        Initialise tous les composants du système
        
        Cette méthode est appelée au démarrage du système. Elle:
        1. Initialise la base de données SQLite3
        2. Configure le fournisseur OpenWeather
        3. Charge ou entraîne le modèle ML
        4. Initialise le système d'alertes
        5. Prépare le serveur web
        
        Si une erreur survient lors de l'initialisation, le programme s'arrête.
        """
        logger.info("DÉMARRAGE DU SYSTÈME DE SURVEILLANCE DE QUALITÉ DE L'AIR")
        # ============= VARIABLES DE CONTRÔLE =============
        self.running = False  # Flag indiquant si le système est en cours d'exécution
        self.web_server_thread = None  # Thread pour le serveur web (exécution parallèle)
        
        # ============= INITIALISATION DES COMPOSANTS =============
        try:
            # ---------- 1. BASE DE DONNÉES SQLITE3 ----------
            # SQLite est une base de données légère stockée dans un fichier
            # Idéale pour Raspberry Pi car elle ne nécessite pas de serveur séparé
            logger.info("Initialisation de la base de données SQLite3...")
            db_path = config.DB_CONFIG['db_path']  # Chemin du fichier DB (ex: ./data/air_quality.db)
            self.db = AirQualityDatabase(db_path=db_path)  # Création de l'instance DB
            if self.db.connect():  # Tentative de connexion à la base de données
                self.db.create_tables()  # Création des tables si elles n'existent pas
                logger.info(f"Base de données prête: {db_path}")
            else:
                logger.error("Échec connexion base de données")
            
            # ---------- 2. SOURCE DE DONNÉES (OPENWEATHER API) ----------
            logger.info("Initialisation de la source de données OpenWeatherMap...")
            self.weather_provider = OpenWeatherDataProvider(
                city=config.WEATHER_DEFAULT_QUERY,
            )
            logger.info("Source de données OpenWeatherMap prête")
            
            # ---------- 3. MODÈLE MACHINE LEARNING ----------
            # Le modèle ML utilise RandomForest pour prédire la qualité de l'air
            # Il est entraîné sur des données historiques et sauvegardé dans un fichier .pkl
            logger.info("Initialisation du modèle ML...")
            self.predictor = AirQualityPredictor()  # Création de l'instance du prédicteur
            
            # Charger le modèle existant ou en entraîner un nouveau
            if not self.predictor.load_model():  # Tentative de chargement du modèle sauvegardé
                logger.warning("Modèle non trouvé - Entraînement avec données synthétiques...")
                # Si aucun modèle n'existe, générer des données synthétiques et entraîner
                training_data = generate_synthetic_training_data(num_samples=2000)
                self.predictor.train_model(training_data)
            
            logger.info("Modèle ML prêt")
            
            # ---------- 4. CLOUD IOT (DÉSACTIVÉ) ----------
            # Le cloud IoT (MQTT) est désactivé car l'application est hébergée sur Cloudflare
            # self.iot = IoTCloudManager(...)  # Non utilisé dans cette version
            self.iot = None
            
            # ---------- 5. SYSTÈME D'ALERTES (DÉSACTIVÉ) ----------
            # Le système d'alertes par email et MQTT est désactivé
            # self.alert_system = AlertSystem(db_manager=self.db, iot_manager=self.iot)
            self.alert_system = None
            
            logger.info("TOUS LES COMPOSANTS SONT INITIALISÉS")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation: {e}")
            raise  # Propager l'erreur pour arrêter le programme
    
    def read_and_process_weather(self):
        """
        Récupère les données OpenWeatherMap et les enregistre en base.
        Planifiée via schedule.every().seconds.do().
        """
        try:
            logger.info("CYCLE DE RÉCUPÉRATION OPENWEATHER")

            weather_snapshot = self.weather_provider.fetch()

            if not weather_snapshot:
                logger.error("Échec récupération OpenWeather")
                return

            air_quality = weather_snapshot['air_quality']['ppm']
            temperature = weather_snapshot['temperature']
            humidity = weather_snapshot['humidity']
            location = weather_snapshot.get('location')

            latitude = location['latitude'] if location else None
            longitude = location['longitude'] if location else None

            logger.info(f"Qualité air: {air_quality:.2f} PPM")
            logger.info(f"Température: {temperature}°C")
            logger.info(f"Humidité: {humidity}%")
            if latitude and longitude:
                logger.info(f"Position: {latitude:.6f}, {longitude:.6f}")

            if temperature is None or humidity is None:
                logger.error("Température ou humidité manquante; données non enregistrées")
                return
            record_id = self.db.insert_sensor_data(
                air_quality=air_quality,
                temperature=temperature,
                humidity=humidity,
                latitude=latitude,
                longitude=longitude
            )
            
            if record_id:
                logger.info(f"Données enregistrées (ID: {record_id})")
            
            # ============= 4. PUBLICATION CLOUD (DÉSACTIVÉ) =============
            # La publication MQTT vers le cloud est désactivée
            # self.iot.publish_sensor_data(...)  # Non utilisé
            
            # ============= 5. DIFFUSION WEB (DÉSACTIVÉ) =============
            # La diffusion en temps réel aux clients web est désactivée
            # L'interface web utilise le rendu serveur (SSR) sans JavaScript
            if WEB_SERVER_AVAILABLE:
                logger.debug("Données prêtes pour interface web (SSR)")
            
            # ============= 6. VÉRIFICATION DES SEUILS D'ALERTE (DÉSACTIVÉ) =============
            # La vérification des seuils d'alerte est désactivée
            # alerts = self.alert_system.check_air_quality(...)
            # if alerts:
            #     logger.warning(f"{len(alerts)} alerte(s) déclenchée(s)")
            
            logger.info("CYCLE TERMINÉ\n")
            
        except Exception as e:
            logger.error(f"Erreur traitement OpenWeather: {e}")
    
    def make_predictions(self):
        """
        Fait des prédictions ML et détecte les pics futurs
        
        Cette méthode est appelée périodiquement (toutes les heures).
        Elle effectue les opérations suivantes:
        1. Récupération des dernières données de capteurs
        2. Génération de prédictions pour les 24 prochaines heures
        3. Détection des pics de pollution prévus
        4. Enregistrement des prédictions dans la base de données
        5. Déclenchement d'alertes si des pics sont détectés
        
        Cette méthode est planifiée par schedule.every().hour.do()
        """
        try:
            logger.info("GÉNÉRATION DES PRÉDICTIONS ML")
            
            # ============= 1. RÉCUPÉRATION DES DERNIÈRES DONNÉES =============
            # Récupérer la lecture la plus récente
            # Ces données servent de point de départ pour les prédictions
            latest_readings = self.db.get_latest_readings(limit=1)
            
            if not latest_readings:
                logger.warning("Pas de données pour faire des prédictions")
                return  # Arrêter si aucune donnée n'est disponible
            
            # Extraire les données actuelles pour les prédictions
            current_data = {
                'air_quality_ppm': latest_readings[0]['air_quality_ppm'],
                'temperature': latest_readings[0]['temperature'],
                'humidity': latest_readings[0]['humidity']
            }
            
            # ============= 2. GÉNÉRATION DES PRÉDICTIONS =============
            # Utiliser le modèle ML pour prédire la qualité de l'air
            # pour les 24 prochaines heures (une prédiction par heure)
            predictions = self.predictor.predict(current_data, hours_ahead=24)
            
            # ============= 3. DÉTECTION DES PICS DE POLLUTION =============
            # Analyser les prédictions pour détecter les pics de pollution
            # Un pic est défini comme une valeur dépassant un seuil critique
            peaks = self.predictor.detect_pollution_peak(predictions)
            
            if peaks:
                logger.warning(f"{len(peaks)} pic(s) de pollution prévu(s)")
                # Les alertes pour les pics sont désactivées
                # alerts = self.alert_system.check_predictions(predictions)
            else:
                logger.info("Aucun pic de pollution prévu")
            
            # ============= 4. ENREGISTREMENT DES PRÉDICTIONS =============
            # Enregistrer quelques prédictions clés dans la base de données
            # On enregistre les prédictions toutes les 6h (0h, 6h, 12h, 18h, 23h)
            # pour éviter de surcharger la base de données
            for i in [0, 6, 12, 18, 23]:  # Indices des prédictions à enregistrer
                if i < len(predictions):
                    pred = predictions[i]
                    self.db.insert_prediction(
                        predicted_for=datetime.fromisoformat(pred['timestamp']),
                        predicted_aqi=pred['predicted_aqi'],
                        confidence=pred['confidence'],
                        model_version='RF_v1.0'  # Version du modèle (Random Forest v1.0)
                    )
            
            # ============= 5. PUBLICATION CLOUD (DÉSACTIVÉ) =============
            # La publication MQTT vers le cloud est désactivée
            # self.iot.publish_predictions(...)  # Non utilisé
            
            logger.info("PRÉDICTIONS TERMINÉES\n")
            
        except Exception as e:
            logger.error(f"Erreur génération prédictions: {e}")
    
    def send_daily_summary(self):
        """
        Envoie un résumé quotidien par email (DÉSACTIVÉ)
        
        Cette méthode est désactivée car les alertes par email sont désactivées.
        """
        # Désactivé - les alertes par email sont supprimées
        pass
    
    def schedule_tasks(self):
        """
        Configure les tâches planifiées
        
        Cette méthode configure toutes les tâches périodiques du système
        en utilisant la bibliothèque 'schedule'. Chaque tâche est exécutée
        automatiquement à intervalles réguliers.
        
        Tâches configurées:
        1. Récupération OpenWeather: toutes les X secondes (configuré dans .env)
        2. Prédictions ML: toutes les heures
        3. Nettoyage des alertes: toutes les 6 heures
        4. Résumé quotidien: tous les jours à 8h00
        
        La boucle principale (run()) exécute ces tâches via schedule.run_pending()
        """
        logger.info("Configuration des tâches planifiées...")
        
        # ============= 1. RÉCUPÉRATION OPENWEATHER =============
        interval = config.WEATHER_DATA_CONFIG['read_interval']
        schedule.every(interval).seconds.do(self.read_and_process_weather)
        logger.info(f"  Récupération OpenWeather: toutes les {interval}s")
        
        # ============= 2. PRÉDICTIONS ML =============
        # Génération des prédictions ML toutes les heures
        # Le modèle prédit la qualité de l'air pour les 24 prochaines heures
        schedule.every().hour.do(self.make_predictions)
        logger.info("  Prédictions ML: toutes les heures")
        
        # ============= 3. NETTOYAGE DES ALERTES (DÉSACTIVÉ) =============
        # Le nettoyage des alertes est désactivé car les alertes sont supprimées
        # schedule.every(6).hours.do(lambda: self.alert_system.clear_old_alerts())
        # logger.info("   Nettoyage alertes: toutes les 6h")
        
        # ============= 4. RÉSUMÉ QUOTIDIEN (DÉSACTIVÉ) =============
        # Le résumé quotidien par email est désactivé
        # schedule.every().day.at("08:00").do(self.send_daily_summary)
        # logger.info("   Résumé quotidien: 8h00")
    
    def start_web_server(self):
        """
        Démarre le serveur web Flask dans un thread séparé
        
        Cette méthode lance le serveur web Flask dans un thread séparé (daemon)
        pour qu'il tourne en parallèle avec les autres tâches du système.
        
        Le serveur web fournit:
        - Interface web pour visualiser les données (dashboard, carte, prédictions)
        - API REST pour accéder aux données
        - Assistant IA pour répondre aux questions
        
        Le thread est daemon=True pour qu'il s'arrête automatiquement
        quand le programme principal s'arrête.
        """
        if not WEB_SERVER_AVAILABLE:
            logger.warning("Module web_server non disponible - Serveur web non démarré")
            return  # Arrêter si le module web_server n'est pas disponible
        
        try:
            logger.info("Démarrage du serveur web...")
            
            # ============= 1. INITIALISATION DU SERVEUR WEB =============
            # Initialiser le serveur web avec la base de données existante
            # Cela crée les connexions DB nécessaires pour le serveur web
            initialize_server()
            
            # ============= 2. FONCTION DE LANCEMENT DU SERVEUR =============
            # Cette fonction sera exécutée dans le thread séparé
            def run_server():
                host = config.FLASK_CONFIG['host']  # Adresse IP (ex: 0.0.0.0 pour toutes les interfaces)
                port = config.FLASK_CONFIG['port']  # Port TCP (ex: 5000)
                logger.info(f"Serveur web démarré sur http://{host}:{port}")
                logger.info(f"Accessible depuis n'importe quel appareil sur le réseau")
                logger.info(f"Interface web: http://{host}:{port}/")
                
                # Lancer l'application Flask
                app.run(
                    host=host,
                    port=port,
                    debug=False  # Mode debug désactivé en production
                )
            
            # ============= 3. CRÉATION DU THREAD =============
            # Créer un thread daemon pour exécuter le serveur web
            # Daemon=True: le thread s'arrête automatiquement quand le programme principal s'arrête
            self.web_server_thread = threading.Thread(target=run_server, daemon=True)
            self.web_server_thread.start()  # Démarrer le thread
            
            # ============= 4. ATTENTE DU DÉMARRAGE =============
            # Attendre 2 secondes pour que le serveur ait le temps de démarrer
            time.sleep(2)
            logger.info("Serveur web opérationnel")
            
        except Exception as e:
            logger.error(f"Erreur démarrage serveur web: {e}")
    
    def run(self):
        """
        Boucle principale du système
        
        Cette méthode est le point d'entrée principal du système après l'initialisation.
        Elle effectue les opérations suivantes:
        1. Configure les tâches planifiées
        2. Démarre le serveur web
        3. Effectue une première lecture des capteurs
        4. Effectue des prédictions initiales
        5. Lance la boucle principale qui exécute les tâches planifiées
        
        La boucle principale tourne indéfiniment jusqu'à ce que:
        - L'utilisateur appuie sur Ctrl+C (KeyboardInterrupt)
        - Le flag self.running est mis à False
        
        Dans la boucle principale:
        - schedule.run_pending() exécute les tâches planifiées si leur heure est venue
        - time.sleep(1) attend 1 seconde avant de vérifier à nouveau
        """
        logger.info("DÉMARRAGE DU SYSTÈME")
        
        self.running = True  # Activer le flag de fonctionnement
        
        # ============= 1. CONFIGURATION DES TÂCHES PLANIFIÉES =============
        # Configurer toutes les tâches périodiques (OpenWeather, prédictions, etc.)
        self.schedule_tasks()
        
        # ============= 2. DÉMARRAGE DU SERVEUR WEB =============
        # Démarrer le serveur web dans un thread séparé
        self.start_web_server()
        
        logger.info("Récupération initiale OpenWeather...")
        self.read_and_process_weather()
        
        # ============= 4. PRÉDICTIONS INITIALES =============
        # Effectuer des prédictions initiales au démarrage
        # Cela permet d'avoir des prédictions dès le début
        logger.info("Prédictions initiales...")
        self.make_predictions()
        
        logger.info("SYSTÈME OPÉRATIONNEL")
        logger.info("Appuyez sur Ctrl+C pour arrêter le système\n")
        
        # ============= 5. BOUCLE PRINCIPALE =============
        # Boucle infinie qui exécute les tâches planifiées
        try:
            while self.running:  # Tant que le système est en cours d'exécution
                schedule.run_pending()  # Exécuter les tâches planifiées si leur heure est venue
                time.sleep(1)  # Attendre 1 seconde avant de vérifier à nouveau
        except KeyboardInterrupt:  # Si l'utilisateur appuie sur Ctrl+C
            logger.info("\n Arrêt demandé par l'utilisateur")
            self.stop()  # Arrêter proprement le système
    
    def stop(self):
        """
        Arrête proprement le système
        
        Cette méthode est appelée quand l'utilisateur appuie sur Ctrl+C ou
        quand le système doit s'arrêter. Elle effectue un nettoyage propre
        de toutes les ressources pour éviter les fuites de mémoire et
        les problèmes de fermeture.
        
        Opérations de nettoyage:
        1. Désactiver le flag de fonctionnement
        2. Arrêter le fournisseur OpenWeather
        3. Déconnecter le cloud IoT (si activé)
        4. Fermer la base de données
        """
        logger.info("ARRÊT DU SYSTÈME")
        
        self.running = False  # Désactiver le flag de fonctionnement
        
        # ============= NETTOYAGE DES RESSOURCES =============
        logger.info("Nettoyage des ressources...")
        
        if self.weather_provider:
            self.weather_provider.cleanup()
            logger.info("Fournisseur OpenWeather arrêté")
        
        # Déconnecter le cloud IoT (si activé)
        # if self.iot:
        #     self.iot.disconnect()
        #     logger.info("✓ Cloud déconnecté")
        
        # Fermer la base de données
        if self.db:
            self.db.close()  # Fermer la connexion à la base de données
            logger.info("Base de données fermée")
        
        logger.info("SYSTÈME ARRÊTÉ")


# ============================================
# Point d'entrée principal du programme
# ============================================

def signal_handler(sig, frame):
    """
    Gère les signaux d'arrêt (Ctrl+C)
    
    Cette fonction est appelée quand l'utilisateur appuie sur Ctrl+C
    (signal SIGINT). Elle permet un arrêt propre du système.
    
    Args:
        sig: Le signal reçu (ex: signal.SIGINT pour Ctrl+C)
        frame: Le frame d'exécution actuel (non utilisé ici)
    
    Note:
        Cette fonction est enregistrée via signal.signal() au début du programme.
    """
    logger.info("\n Signal d'arrêt reçu")
    sys.exit(0)  # Sortir du programme avec le code de succès (0)


if __name__ == "__main__":
    """
    Point d'entrée principal du programme
    
    Ce bloc est exécuté uniquement lorsque le script est lancé directement
    (pas lorsqu'il est importé comme module). Il:
    1. Configure le gestionnaire de signaux pour Ctrl+C
    2. Crée une instance du système AirQualitySystem
    3. Lance la boucle principale du système
    4. Gère les erreurs fatales
    
    Pour lancer le système:
        python3 main.py
    """
    # ============= 1. CONFIGURATION DU GESTIONNAIRE DE SIGNAUX =============
    # Enregistrer la fonction signal_handler pour le signal SIGINT (Ctrl+C)
    # Cela permet un arrêt propre quand l'utilisateur appuie sur Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # ============= 2. CRÉATION ET DÉMARRAGE DU SYSTÈME =============
        # Créer une instance de la classe AirQualitySystem
        # Cela initialise tous les composants (DB, OpenWeather, ML, alertes, web)
        system = AirQualitySystem()
        
        # Lancer la boucle principale du système
        # Cela démarre les tâches planifiées et le serveur web
        system.run()
        
    except Exception as e:
        # ============= 3. GESTION DES ERREURS FATALES =============
        # Si une erreur fatale survient, la logger et sortir avec le code d'erreur (1)
        logger.error(f"Erreur fatale: {e}")
        sys.exit(1)  # Sortir avec le code d'erreur (1 = échec)