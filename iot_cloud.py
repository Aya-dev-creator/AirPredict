"""
Module IoT Cloud pour la connexion MQTT
Permet de publier les données vers le cloud et de les rendre accessibles depuis n'importe quel appareil
Supporte: HiveMQ, AWS IoT Core, Azure IoT Hub, Google Cloud IoT
"""
import json
import logging
import time
from datetime import datetime
import paho.mqtt.client as mqtt
from config import config
# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class IoTCloudManager:
    """
    Gestionnaire de connexion IoT Cloud via MQTT
    Permet de publier les données capteurs et de recevoir des commandes
    """
    def __init__(self, broker=None, port=None, topic=None):
        """
        Initialise le gestionnaire IoT Cloud
        Args:
            broker (str): Adresse du broker MQTT (si None, utilise config)
            port (int): Port du broker (si None, utilise config)
            topic (str): Topic MQTT de base (si None, utilise config)
        """
        self.mqtt_config = config.MQTT_CONFIG
        self.broker = broker or self.mqtt_config['broker']
        self.port = port or self.mqtt_config['port']
        self.topic = topic or self.mqtt_config['topic']
        self.client_id = self.mqtt_config['client_id']
        # Créer le client MQTT
        self.client = mqtt.Client(client_id=self.client_id)
        # Configurer les callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_message = self._on_message
        # Configuration authentification si nécessaire
        if self.mqtt_config['username']:
            self.client.username_pw_set(
                self.mqtt_config['username'],
                self.mqtt_config['password']
            )
        self.connected = False
        self.message_count = 0
        logger.info(f"✓ IoT Cloud Manager initialisé - Broker: {self.broker}")
    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback appelé lors de la connexion au broker MQTT
        Args:
            rc (int): Code de retour de connexion (0 = succès)
        """
        if rc == 0:
            self.connected = True
            logger.info(f"✓ Connecté au broker MQTT: {self.broker}:{self.port}")
            # S'abonner aux topics de commandes
            command_topic = f"{self.topic}/commands/#"
            self.client.subscribe(command_topic)
            logger.info(f"✓ Abonné au topic: {command_topic}")
        else:
            self.connected = False
            error_messages = {
                1: "Protocole incorrect",
                2: "Client ID rejeté",
                3: "Serveur indisponible",
                4: "Identifiants incorrects",
                5: "Non autorisé"
            }
            logger.error(f"✗ Échec de connexion MQTT: {error_messages.get(rc, f'Code {rc}')}")
    def _on_disconnect(self, client, userdata, rc):
        """Callback appelé lors de la déconnexion"""
        self.connected = False
        if rc != 0:
            logger.warning(f"⚠️ Déconnexion inattendue du broker MQTT (code: {rc})")
        else:
            logger.info("✓ Déconnecté du broker MQTT")
    def _on_publish(self, client, userdata, mid):
        """Callback appelé après publication réussie"""
        self.message_count += 1
        logger.debug(f"✓ Message publié (ID: {mid})")
    def _on_message(self, client, userdata, msg):
        """
        Callback appelé lors de la réception d'un message
        Args:
            msg: Message MQTT reçu
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.info(f"📨 Message reçu sur {topic}: {payload}")
            # Parser le payload JSON
            data = json.loads(payload)
            # Gérer les commandes
            if 'command' in data:
                self._handle_command(data['command'], data.get('params', {}))
        except Exception as e:
            logger.error(f"✗ Erreur traitement message: {e}")
    def _handle_command(self, command, params):
        """
        Gère les commandes reçues via MQTT
        Args:
            command (str): Nom de la commande
            params (dict): Paramètres de la commande
        """
        logger.info(f"🔧 Commande reçue: {command} - Params: {params}")
        # Exemples de commandes possibles:
        commands = {
            'calibrate': self._command_calibrate,
            'change_interval': self._command_change_interval,
            'reboot': self._command_reboot,
            'get_status': self._command_get_status
        }
        if command in commands:
            commands[command](params)
        else:
            logger.warning(f"⚠️ Commande inconnue: {command}")
    def _command_calibrate(self, params):
        """Commande de calibration des capteurs"""
        logger.info("🔧 Démarrage de la calibration...")
        # Implémenter la logique de calibration
    def _command_change_interval(self, params):
        """Commande pour changer l'intervalle de lecture"""
        new_interval = params.get('interval', 60)
        logger.info(f"🔧 Changement de l'intervalle à {new_interval}s")
        # Implémenter la logique de changement d'intervalle
    def _command_reboot(self, params):
        """Commande de redémarrage du système"""
        logger.info("🔧 Redémarrage du système demandé...")
        # Implémenter la logique de redémarrage
    def _command_get_status(self, params):
        """Commande pour obtenir le statut du système"""
        status = {
            'status': 'online',
            'uptime': time.time(),
            'messages_sent': self.message_count
        }
        self.publish_status(status)
    def connect(self, retry=True, max_retries=5):
        """
        Se connecte au broker MQTT
        Args:
            retry (bool): Réessayer en cas d'échec
            max_retries (int): Nombre maximum de tentatives
        Returns:
            bool: True si connexion réussie
        """
        logger.info(f"🔌 Connexion au broker MQTT: {self.broker}:{self.port}")
        attempt = 0
        while attempt < max_retries:
            try:
                self.client.connect(
                    self.broker,
                    self.port,
                    keepalive=self.mqtt_config['keepalive']
                )
                # Démarrer la boucle réseau dans un thread séparé
                self.client.loop_start()
                # Attendre la confirmation de connexion
                timeout = 10
                elapsed = 0
                while not self.connected and elapsed < timeout:
                    time.sleep(0.5)
                    elapsed += 0.5
                if self.connected:
                    return True
            except Exception as e:
                logger.error(f"✗ Erreur de connexion (tentative {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if retry and attempt < max_retries:
                logger.info(f"⏳ Nouvelle tentative dans 5 secondes...")
                time.sleep(5)
        return False
    def publish_sensor_data(self, sensor_data):
        """
        Publie les données capteurs sur le cloud
        Args:
            sensor_data (dict): Données des capteurs à publier
        Returns:
            bool: True si publication réussie
        """
        if not self.connected:
            logger.error("✗ Non connecté au broker MQTT")
            return False
        try:
            # Préparer le payload
            payload = {
                'timestamp': sensor_data.get('timestamp', datetime.now().isoformat()),
                'device_id': self.client_id,
                'data': {
                    'air_quality_ppm': sensor_data.get('air_quality', {}).get('ppm'),
                    'temperature': sensor_data.get('temperature'),
                    'humidity': sensor_data.get('humidity'),
                    'location': sensor_data.get('location')
                }
            }
            # Publier sur le topic principal
            topic = f"{self.topic}/data"
            payload_json = json.dumps(payload)
            result = self.client.publish(
                topic,
                payload_json,
                qos=1  # Au moins une fois
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📤 Données publiées sur {topic}")
                return True
            else:
                logger.error(f"✗ Échec de publication (code: {result.rc})")
                return False
        except Exception as e:
            logger.error(f"✗ Erreur lors de la publication: {e}")
            return False
    def publish_prediction(self, predictions):
        """
        Publie les prédictions ML sur le cloud
        Args:
            predictions (list): Liste des prédictions
        Returns:
            bool: True si publication réussie
        """
        if not self.connected:
            logger.error("✗ Non connecté au broker MQTT")
            return False
        try:
            payload = {
                'timestamp': datetime.now().isoformat(),
                'device_id': self.client_id,
                'predictions': predictions
            }
            topic = f"{self.topic}/predictions"
            payload_json = json.dumps(payload)
            result = self.client.publish(topic, payload_json, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📤 Prédictions publiées sur {topic}")
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"✗ Erreur publication prédictions: {e}")
            return False
    def publish_alert(self, alert_data):
        """
        Publie une alerte sur le cloud
        Args:
            alert_data (dict): Données de l'alerte
        Returns:
            bool: True si publication réussie
        """
        if not self.connected:
            logger.error("✗ Non connecté au broker MQTT")
            return False
        try:
            payload = {
                'timestamp': datetime.now().isoformat(),
                'device_id': self.client_id,
                'alert': alert_data
            }
            topic = f"{self.topic}/alerts"
            payload_json = json.dumps(payload)
            result = self.client.publish(topic, payload_json, qos=2)  # Exactement une fois
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.warning(f"⚠️ Alerte publiée sur {topic}: {alert_data.get('message')}")
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"✗ Erreur publication alerte: {e}")
            return False
    def publish_status(self, status_data):
        """
        Publie le statut du système
        Args:
            status_data (dict): Données de statut
        Returns:
            bool: True si publication réussie
        """
        if not self.connected:
            return False
        try:
            payload = {
                'timestamp': datetime.now().isoformat(),
                'device_id': self.client_id,
                'status': status_data
            }
            topic = f"{self.topic}/status"
            payload_json = json.dumps(payload)
            result = self.client.publish(topic, payload_json, qos=0)  # Au plus une fois
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"✗ Erreur publication statut: {e}")
            return False
    def disconnect(self):
        """Déconnecte proprement du broker MQTT"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("✓ Déconnecté du broker MQTT")
    def is_connected(self):
        """
        Vérifie l'état de connexion
        Returns:
            bool: True si connecté
        """
        return self.connected
# Test du module si exécuté directement
if __name__ == "__main__":
    print("=== Test du système IoT Cloud ===\n")
    # Créer le gestionnaire IoT
    iot_manager = IoTCloudManager()
    # Se connecter
    if iot_manager.connect():
        print("✓ Connexion réussie au broker MQTT\n")
        # Publier des données de test
        test_data = {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {'ppm': 95.5},
            'temperature': 25.3,
            'humidity': 62.0,
            'location': {
                'latitude': 36.8065,
                'longitude': 10.1815
            }
        }
        print("Publication de données test...")
        iot_manager.publish_sensor_data(test_data)
        # Publier une alerte de test
        test_alert = {
            'type': 'HIGH_POLLUTION',
            'severity': 'MEDIUM',
            'message': 'Qualité de l\'air dégradée',
            'value': 95.5
        }
        print("Publication d'alerte test...")
        iot_manager.publish_alert(test_alert)
        # Attendre un peu pour voir les messages
        time.sleep(5)
        # Déconnexion
        iot_manager.disconnect()
        print("\n✓ Test terminé")
    else:
        print("✗ Échec de connexion au broker MQTT")