"""
Module de gestion des capteurs Raspberry Pi
Gère la lecture des capteurs: MQ-135 (qualité de l'air), DHT11 (température/humidité), Localisation

Ce module fournit une interface pour interagir avec les capteurs physiques connectés
au Raspberry Pi 4. Les capteurs MQ-135 et DHT11 nécessitent le matériel Raspberry Pi.
La localisation utilise l'API de géolocalisation IP (pas de capteur GPS physique).

Capteurs supportés:
1. MQ-135: Capteur de qualité de l'air (détecte CO2, fumée, gaz combustibles)
   - Utilise l'ADC ADS1115 pour la lecture analogique
   - Fournit une sortie digitale DOUT pour les alertes de seuil
2. DHT11: Capteur de température et d'humidité
   - Lecture numérique via protocole propriétaire
   - Précision: ±2°C pour la température, ±5% pour l'humidité
3. Localisation: Géolocalisation IP du device
   - Utilise l'API ipinfo.io pour obtenir la position
   - Pas de matériel GPS requis

Architecture:
- MQ135Sensor: Classe pour le capteur MQ-135
- DHT11Sensor: Classe pour le capteur DHT11
- GPSSensor: Classe pour la localisation IP
- SensorManager: Gestionnaire central qui coordonne tous les capteurs
"""

# ============= IMPORTS SYSTÈME =============
import os
import platform
import time  # Module pour les pauses et le temps
from datetime import datetime  # Module pour manipuler les dates et heures
import logging  # Module pour la journalisation (logs) du système

# ============= IMPORTS POUR LA GÉOLOCALISATION =============
import requests  # Bibliothèque pour les requêtes HTTP (géolocalisation IP)
from config import config

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= IMPORTS RASPBERRY PI (OPTIONNELS) =============
# Ces imports sont requis uniquement sur un Raspberry Pi réel
# Sur Windows ou un environnement de développement, ils sont ignorés
IS_RPI = platform.system() == "Linux" and platform.machine().lower().startswith(("arm", "aarch64"))
board = None
busio = None
adafruit_dht = None
GPIO = None
ADS = None
AnalogIn = None
HARDWARE_AVAILABLE = False

if IS_RPI:
    try:
        import board  # Bibliothèque pour les broches GPIO (Adafruit)
        import busio  # Bibliothèque pour le bus I2C
        import adafruit_dht  # Bibliothèque pour le capteur DHT11
        import RPi.GPIO as GPIO  # Bibliothèque pour le contrôle GPIO
        import adafruit_ads1x15.ads1115 as ADS  # Bibliothèque pour l'ADC ADS1115
        from adafruit_ads1x15.analog_in import AnalogIn  # Classe pour les entrées analogiques
        HARDWARE_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Raspberry Pi hardware libraries unavailable: {e}")
        HARDWARE_AVAILABLE = False
else:
    logger.warning("Raspberry Pi hardware libraries are unavailable on this platform. Sensor hardware will run in fallback mode.")

logger.info(f"Platform detection: system={platform.system()}, machine={platform.machine()}, IS_RPI={IS_RPI}, HARDWARE_AVAILABLE={HARDWARE_AVAILABLE}")
        self.ads = None  # Instance de l'ADC ADS1115
        self.adc_channel_obj = None  # Objet du canal ADC
        self.available = HARDWARE_AVAILABLE  # Indique si le hardware Raspberry Pi est disponible

        if not self.available:
            logger.warning("MQ-135 hardware unavailable; fonction de lecture en mode simulation.")
            return

        # ============= INITIALISATION DE L'ADS1115 (ADC) =============
        # L'ADS1115 est un convertisseur analogique-numérique 16-bit
        # Il communique via le bus I2C (adresse par défaut: 0x48)
        # Il a 4 canaux analogiques (A0, A1, A2, A3)
        try:
            # Initialiser le bus I2C
            # SCL: Serial Clock (horloge), SDA: Serial Data (données)
            i2c = busio.I2C(board.SCL, board.SDA)
            
            # Attendre que le bus I2C soit disponible
            while not i2c.try_lock():
                time.sleep(0.1)
            
            # Scanner les adresses I2C disponibles pour vérifier la connexion
            logger.info("Scanning I2C bus...")
            addresses = i2c.scan()
            i2c.unlock()
            
            if addresses:
                logger.info(f"Adresses I2C trouvées: {[hex(addr) for addr in addresses]}")
            else:
                logger.warning("Aucune adresse I2C trouvée")
            
            # Initialiser ADS1115 avec plusieurs tentatives (gestion d'erreur robuste)
            for attempt in range(3):
                try:
                    self.ads = ADS.ADS1115(i2c, address=0x48)  # Adresse par défaut de l'ADS1115
                    
                    # Mapper le canal ADC (0-3) à l'attribut correspondant (ADS.P0-ADS.P3)
                    channel_map = {0: ADS.P0, 1: ADS.P1, 2: ADS.P2, 3: ADS.P3}
                    channel_attr = channel_map.get(adc_channel, ADS.P0)
                    
                    # Créer l'objet de lecture analogique pour le canal spécifié
                    self.adc_channel_obj = AnalogIn(self.ads, channel_attr)
                    logger.info(f"✓ ADS1115 initialisé sur canal {adc_channel} (adresse 0x48)")
                    break  # Sortir de la boucle si l'initialisation a réussi
                except ValueError as e:
                    if "0x48" in str(e):
                        logger.warning(f"Tentative {attempt + 1}/3: {e}")
                        time.sleep(1)  # Attendre avant de réessayer
                    else:
                        raise  # Propager l'erreur si ce n'est pas une erreur d'adresse
                except Exception as e:
                    logger.error(f"Erreur initialisation ADS1115: {e}")
                    break  # Sortir de la boucle en cas d'erreur
                    
            if self.adc_channel_obj is None:
                logger.error("Impossible d'initialiser l'ADS1115 après plusieurs tentatives")
                self.available = False
                return
                
        except Exception as e:
            logger.error(f"✗ Erreur initialisation ADS1115/I2C: {e}")
            self.available = False
            return  # Basculer en mode simulation si l'ADS1115 ne peut pas être initialisé
            
        # ============= INITIALISATION DU PIN DIGITAL DOUT =============
        # La sortie DOUT passe à LOW quand le seuil de gaz est dépassé
        # Ce seuil est réglable via le potentiomètre sur le module MQ-135
        try:
            GPIO.setmode(GPIO.BCM)  # Utiliser la numérotation BCM des broches
            GPIO.setup(self.digital_pin, GPIO.IN)  # Configurer la broche en entrée
            logger.info(f"✓ Capteur MQ-135 DOUT initialisé sur GPIO {self.digital_pin}")
        except Exception as e:
            logger.error(f"Erreur initialisation GPIO: {e}")
            self.available = False
            return  # Basculer en mode simulation si le GPIO ne peut pas être initialisé
    
    def read_analog_value(self):
        """
        Lit la valeur analogique du capteur MQ-135 via ADS1115
        
        Cette méthode lit la valeur analogique brute du capteur MQ-135 via l'ADC ADS1115.
        L'ADS1115 est un convertisseur analogique-numérique 16-bit qui retourne
        des valeurs entre 0 et 26400 (pour la plage ±4.096V par défaut).
        
        Returns:
            int: Valeur analogique (0-26400 pour ADS1115 16-bit)
                  Retourne 0 en cas d'erreur
        """
        if self.adc_channel_obj is None:
            logger.error("ADS1115 channel object unavailable; cannot read analog value.")
            return 0

        try:
            # Lire la valeur brute de l'ADS1115
            value = self.adc_channel_obj.value  # Valeur brute (0-26400)
            voltage = self.adc_channel_obj.voltage  # Tension correspondante (0-4.096V)
            logger.debug(f"ADS1115 - Raw: {value}, Voltage: {voltage:.3f}V")
            return value
        except Exception as e:
            logger.error(f"✗ Erreur lecture ADS1115: {e}")
            return 0
    
    def read_digital(self):
        """
        Lit la sortie digitale DOUT du MQ-135
        
        La sortie DOUT du MQ-135 passe à LOW quand le seuil de gaz est dépassé.
        Ce seuil est réglable via le potentiomètre sur le module MQ-135.
        Quand la concentration de gaz dépasse le seuil, DOUT = LOW (0).
        Quand la concentration est sous le seuil, DOUT = HIGH (1).
        
        Returns:
            bool: True si le seuil est dépassé (DOUT = LOW), False sinon
                  Retourne False en cas d'erreur
        """
        if not getattr(self, 'available', False):
            logger.warning("MQ-135 digital read unavailable; returning False.")
            return False

        try:
            # DOUT est LOW quand le seuil de gaz est dépassé
            return GPIO.input(self.digital_pin) == GPIO.LOW
        except Exception as e:
            logger.error(f"✗ Erreur lecture DOUT: {e}")
            return False
    
    def calculate_ppm(self, analog_value):
        """
        Convertit la valeur analogique en PPM (parts per million)
        
        Cette méthode convertit la valeur analogique brute de l'ADS1115 en une
        concentration de gaz en PPM en utilisant la courbe de calibration du
        capteur MQ-135.
        
        Le calcul se fait en plusieurs étapes:
        1. Conversion de la valeur analogique en tension
        2. Calcul de la résistance du capteur (Rs)
        3. Calcul du ratio Rs/R0
        4. Application de la formule empirique pour obtenir la concentration en PPM
        
        La formule utilisée est basée sur la courbe du datasheet du MQ-135 pour le CO2.
        
        Args:
            analog_value (int): Valeur de l'ADS1115 (0-26400)
        
        Returns:
            float: Concentration en PPM (parts per million)
                   Retourne 0 si la tension est trop basse ou si Rs <= 0
        """
        # ============= 1. CONVERSION EN TENSION =============
        # Convertir la valeur brute (0-26400) en tension (0-4.096V)
        # ADS1115: 16-bit, plage ±4.096V par défaut
        voltage = (analog_value / 26400.0) * 4.096
        
        # ============= 2. VALIDATION DE LA TENSION =============
        # Éviter la division par zéro et les valeurs invalides
        if voltage <= 0.1:
            return 0  # Tension trop basse, retourner 0
        
        # ============= 3. CALCUL DE RS (RÉSISTANCE DU CAPTEUR) =============
        # Circuit: 5V -- RL=10kΩ -- MQ135(Rs) -- GND
        # La tension mesurée est aux bornes de RL (résistance de charge)
        # Formule: Rs = ((Vcc - Vout) * RL) / Vout
        rs = ((5.0 - voltage) * 10.0) / voltage
        
        if rs <= 0:
            return 0  # Résistance invalide, retourner 0
        
        # ============= 4. CALCUL DU RATIO RS/R0 =============
        # R0 est la résistance du capteur dans l'air pur (valeur de calibration)
        # Le ratio Rs/R0 est utilisé pour normaliser la mesure
        ratio = rs / self.r0
        
        # ============= 5. CONVERSION EN PPM =============
        # Formule empirique basée sur la courbe du datasheet du MQ-135 pour le CO2
        # ppm = 116.6020682 * (ratio ^ -2.769034857)
        ppm = 116.6020682 * (ratio ** -2.769034857)
        
        # S'assurer que la valeur est positive
        return max(0, ppm)
    
    def read(self):
        """
        Effectue une lecture complète du capteur MQ-135
        
        Cette méthode effectue une lecture complète du capteur en:
        1. Lisant la valeur analogique via l'ADS1115
        2. Convertissant la valeur analogique en PPM
        3. Lisant la sortie digitale DOUT pour vérifier si le seuil est dépassé
        4. Retournant un dictionnaire avec toutes les données
        
        Returns:
            dict: Dictionnaire contenant les données du capteur:
                  - sensor: Nom du capteur ('MQ-135')
                  - timestamp: Heure de la lecture (ISO format)
                  - raw_value: Valeur analogique brute
                  - ppm: Concentration en PPM
                  - unit: Unité de mesure ('PPM')
                  - alert: True si le seuil est dépassé, False sinon
                  Retourne None en cas d'erreur
        """
        if not getattr(self, 'available', False):
            logger.warning("MQ-135 hardware unavailable, renvoyant valeurs par défaut.")
            return {
                'sensor': 'MQ-135',
                'timestamp': datetime.now().isoformat(),
                'raw_value': None,
                'ppm': None,
                'unit': 'PPM',
                'alert': False
            }

        try:
            # Lire la valeur analogique brute
            analog_value = self.read_analog_value()
            
            # Convertir en PPM
            ppm = self.calculate_ppm(analog_value)
            
            # Lire la sortie digitale DOUT
            digital_alert = self.read_digital()
            
            # Construire le dictionnaire de données
            data = {
                'sensor': 'MQ-135',
                'timestamp': datetime.now().isoformat(),
                'raw_value': analog_value,
                'ppm': round(ppm, 2),
                'unit': 'PPM',
                'alert': digital_alert
            }
            
            # Afficher les données dans les logs
            alert_msg = " ⚠️ ALERTE!" if digital_alert else ""
            logger.info(f"📊 MQ-135: {ppm:.2f} PPM{alert_msg}")
            return data
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture MQ-135: {e}")
            return None
    
    def calibrate(self, clean_air_samples=50):
        """
        Calibre le capteur MQ-135 dans un environnement d'air propre
        
        La calibration est essentielle pour obtenir des mesures précises.
        Le capteur MQ-135 doit être calibré dans un environnement d'air propre
        (sans fumée, sans gaz, sans pollution) pour déterminer R0, la résistance
        du capteur dans l'air pur.
        
        Recommandations:
        - Laisser le capteur chauffer pendant au moins 24 heures avant la calibration
        - Effectuer la calibration dans un environnement bien ventilé
        - Éviter toute source de gaz ou de fumée pendant la calibration
        
        Le processus de calibration:
        1. Prendre plusieurs échantillons de lecture dans l'air propre
        2. Calculer la résistance moyenne Rs
        3. Calculer R0 = Rs / 3.6 (ratio typique dans l'air pur selon le datasheet)
        
        Args:
            clean_air_samples (int): Nombre d'échantillons à prendre (défaut: 50)
        
        Returns:
            float: La nouvelle valeur de R0 calculée
        """
        logger.info("🔧 Calibration MQ-135 (laissez le capteur dans l'air propre 24h avant)...")
        rs_sum = 0  # Somme des résistances Rs mesurées
        
        # Prendre plusieurs échantillons pour calculer la moyenne
        for i in range(clean_air_samples):
            # Lire la valeur analogique
            analog_value = self.read_analog_value()
            
            # Convertir en tension
            voltage = (analog_value / 26400.0) * 4.096
            
            # Calculer Rs si la tension est valide
            if voltage > 0.1:
                rs = ((5.0 - voltage) * 10.0) / voltage
                rs_sum += rs
            
            # Afficher la progression tous les 10 échantillons
            if (i + 1) % 10 == 0:
                logger.info(f"Calibration: {i + 1}/{clean_air_samples}")
            
            # Attendre entre chaque lecture
            time.sleep(0.5)
        
        # Calculer R0 = Rs_moyenne / 3.6
        # Le ratio 3.6 est typique pour l'air pur selon le datasheet du MQ-135
        self.r0 = (rs_sum / clean_air_samples) / 3.6
        logger.info(f"✓ Calibration terminée - R0 = {self.r0:.2f}Ω")
        return self.r0
class DHT11Sensor:
    """
    Classe pour gérer le capteur DHT11 (température et humidité)
    
    Le capteur DHT11 est un capteur numérique de température et d'humidité.
    Caractéristiques:
    - Plage de température: 0°C à 50°C (précision: ±2°C)
    - Plage d'humidité: 20% à 90% (précision: ±5%)
    - Fréquence d'échantillonnage: 1 Hz (une lecture par seconde maximum)
    - Communication: Protocole propriétaire sur une seule broche de données
    
    Fonctionnement:
    - Le capteur utilise un protocole de communication numérique propriétaire
    - La bibliothèque adafruit_dht gère ce protocole automatiquement
    - Le capteur doit être alimenté en 3.3V ou 5V
    - Une résistance de pull-up (10kΩ) est recommandée sur la broche de données
    
    Note:
    - Le capteur DHT11 est lent et ne peut être lu qu'une fois par seconde
    - Des lectures fréquentes peuvent causer des erreurs
    - Le capteur a besoin de temps pour se stabiliser après le démarrage
    """
    
    def __init__(self, pin=4):
        """
        Initialise le capteur DHT11
        
        Cette méthode configure le capteur DHT11 sur la broche GPIO spécifiée.
        La broche par défaut est GPIO 4 (broche physique 7 sur Raspberry Pi).
        
        Args:
            pin (int): Numéro du pin GPIO (défaut: 4)
                      Sur Raspberry Pi, GPIO 4 est couramment utilisé pour le DHT11
        """
        self.pin = pin  # Stocker le numéro de broche GPIO
        self.available = HARDWARE_AVAILABLE
        self.sensor = None

        if not self.available:
            logger.warning("DHT11 hardware unavailable; lecture en mode simulation.")
            return

        # Essayer d'abord avec board.D4, sinon utiliser le numéro de pin directement
        # board.D4 est la notation préférée pour la bibliothèque adafruit_dht
        try:
            pin_board = getattr(board, f'D{pin}')
        except AttributeError:
            # Si D4 n'existe pas, utiliser la notation BOARD directe
            pin_board = pin
        
        # Initialiser le capteur DHT11 avec la bibliothèque adafruit_dht
        try:
            self.sensor = adafruit_dht.DHT11(pin_board)
            logger.info(f"✓ Capteur DHT11 initialisé sur GPIO {self.pin}")
        except Exception as e:
            logger.error(f"Erreur initialisation DHT11: {e}")
            self.available = False
            self.sensor = None
            logger.warning("DHT11 hardware unavailable; lecture en mode simulation.")
    
    def read(self):
        """
        Lit la température et l'humidité du capteur DHT11
        
        Cette méthode lit les données de température et d'humidité du capteur DHT11.
        Elle inclut une gestion d'erreur robuste avec plusieurs tentatives de lecture
        car le capteur DHT11 est connu pour être instable.
        
        Returns:
            dict: Dictionnaire contenant les données du capteur:
                  - sensor: Nom du capteur ('DHT11')
                  - timestamp: Heure de la lecture (ISO format)
                  - temperature: Température en °C (None si erreur)
                  - humidity: Humidité en % (None si erreur)
                  - temp_unit: Unité de température ('°C')
                  - humidity_unit: Unité d'humidité ('%')
                  Retourne un dictionnaire avec None pour les valeurs en cas d'erreur
        """
        if not getattr(self, 'available', False):
            return {
                'sensor': 'DHT11',
                'timestamp': datetime.now().isoformat(),
                'temperature': None,
                'humidity': None,
                'temp_unit': '°C',
                'humidity_unit': '%'
            }

        try:
            # Lecture réelle du capteur avec gestion d'erreur améliorée
            try:
                # Première tentative de lecture
                temperature = self.sensor.temperature
                humidity = self.sensor.humidity
                
                # Réessayer si la lecture a échoué (valeurs None)
                if temperature is None or humidity is None:
                    time.sleep(1)  # Attendre avant de réessayer
                    temperature = self.sensor.temperature
                    humidity = self.sensor.humidity
                    
            except RuntimeError as e:
                # RuntimeError est courant avec le DHT11 (timeout, checksum error, etc.)
                logger.warning(f"RuntimeError DHT11: {e}, réessai...")
                time.sleep(2)  # Attendre plus longtemps avant de réessayer
                temperature = self.sensor.temperature
                humidity = self.sensor.humidity
                
            # Vérifier la validité des données après toutes les tentatives
            if temperature is None or humidity is None:
                raise Exception("Données DHT11 invalides après plusieurs tentatives")
                
            # Construire le dictionnaire de données
            data = {
                'sensor': 'DHT11',
                'timestamp': datetime.now().isoformat(),
                'temperature': round(temperature, 1),
                'humidity': round(humidity, 1),
                'temp_unit': '°C',
                'humidity_unit': '%'
            }
            logger.info(f"🌡️ DHT11: {temperature}°C, {humidity}%")
            return data
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture DHT11: {e}")
            # Retourner des données par défaut avec None au lieu de None complet
            # Cela permet au système de continuer à fonctionner même si le capteur échoue
            return {
                'sensor': 'DHT11',
                'timestamp': datetime.now().isoformat(),
                'temperature': None,
                'humidity': None,
                'temp_unit': '°C',
                'humidity_unit': '%'
            }
    def cleanup(self):
        """
        Nettoie les ressources du capteur DHT11
        
        Cette méthode libère les ressources GPIO utilisées par le capteur DHT11.
        Elle doit être appelée avant de terminer le programme pour éviter
        les problèmes de verrouillage des broches GPIO.
        """
        if self.sensor is not None:
            self.sensor.exit()  # Libérer les ressources du capteur

class GPSSensor:
    """
    Classe pour gérer la localisation du device
    
    Au lieu d'utiliser un capteur GPS physique (NEO-6M), cette classe
    utilise la géolocalisation basée sur l'adresse IP du device.
    Cela permet d'obtenir la localisation sans matériel GPS supplémentaire.
    
    Fonctionnement:
    - Utilise une API de géolocalisation IP (ex: ipinfo.io)
    - Retourne la latitude et longitude approximatives du device
    - La précision dépend de la précision de l'IP géolocalisation
    - En mode simulation, retourne des coordonnées par défaut
    
    Note:
    - La précision de la géolocalisation IP est généralement de quelques kilomètres
    - Pour une précision GPS exacte, un capteur GPS physique serait nécessaire
    - L'interface web peut utiliser l'API de géolocalisation du navigateur pour une meilleure précision
    """
    
    def __init__(self):
        """
        Initialise le capteur de localisation
        
        Cette méthode initialise le capteur de localisation basé sur IP.
        Aucun matériel GPS n'est requis.
        """
        self.gps_session = None  # Pas de session GPS (utilise IP géolocalisation)
        logger.info("✓ Localisation basée sur IP initialisée")
    def read(self):
        """
        Lit les coordonnées de localisation du device
        
        Cette méthode utilise la géolocalisation IP pour obtenir la position
        approximative du device. Elle tente de contacter une API de géolocalisation
        (ex: ipinfo.io) pour obtenir la latitude et longitude.
        
        En cas d'échec ou en mode simulation, retourne None pour les coordonnées.
        L'interface web peut utiliser l'API de géolocalisation du navigateur pour
        une meilleure précision.
        
        Returns:
            dict: Dictionnaire contenant les données de localisation:
                  - sensor: Nom du capteur ('Device Location')
                  - timestamp: Heure de la lecture (ISO format)
                  - latitude: Latitude en degrés décimaux (None si erreur)
                  - longitude: Longitude en degrés décimaux (None si erreur)
                  - fix: True si localisation obtenue, False sinon
                  Retourne un dictionnaire avec None pour latitude/longitude si erreur
        """
        try:
            # Essayer d'obtenir la localisation via IP
            # Utiliser une API de géolocalisation IP gratuite
            import requests
            
            try:
                # Utiliser l'API ipinfo.io (gratuit, sans clé pour usage limité)
                response = requests.get('https://ipinfo.io/json', timeout=5)
                
                if response.status_code == 200:
                    ip_data = response.json()
                    
                    # Extraire la localisation (format: "lat,lon")
                    loc = ip_data.get('loc', '')
                    if loc:
                        lat_str, lon_str = loc.split(',')
                        latitude = float(lat_str)
                        longitude = float(lon_str)
                        
                        data = {
                            'sensor': 'Device Location',
                            'timestamp': datetime.now().isoformat(),
                            'latitude': latitude,
                            'longitude': longitude,
                            'altitude': 0,
                            'fix': True,
                            'satellites': 0
                        }
                        logger.info(f"📍 Localisation IP: {latitude:.6f}, {longitude:.6f}")
                        return data
            except Exception as e:
                logger.warning(f"⚠ Erreur géolocalisation IP: {e}")
            
            # En cas d'échec, retourner None pour les coordonnées
            # L'interface web peut utiliser la géolocalisation du navigateur
            logger.info("📍 Localisation non disponible (sera obtenue via navigateur)")
            return {
                'sensor': 'Device Location',
                'timestamp': datetime.now().isoformat(),
                'latitude': None,
                'longitude': None,
                'fix': False
            }
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture localisation: {e}")
            # Retourner des données par défaut avec fix=False
            return {
                'sensor': 'Device Location',
                'timestamp': datetime.now().isoformat(),
                'latitude': None,
                'longitude': None,
                'fix': False
            }
class SensorManager:
    """
    Gestionnaire central pour tous les capteurs
    
    Cette classe coordonne la lecture de tous les capteurs et agrège les données
    dans un format unifié. Elle agit comme une interface unique pour accéder
    à tous les capteurs du système.
    
    Capteurs gérés:
    - MQ135Sensor: Capteur de qualité de l'air
    - DHT11Sensor: Capteur de température et d'humidité
    - GPSSensor: Module GPS pour la localisation
    
    Fonctionnement:
    - Initialise tous les capteurs au démarrage
    - Lit tous les capteurs simultanément
    - Agrège les données dans un dictionnaire structuré
    - Gère le nettoyage des ressources à l'arrêt
    
    Avantages:
    - Interface unifiée pour tous les capteurs
    - Gestion centralisée des erreurs
    - Format de données cohérent
    - Facile à étendre avec de nouveaux capteurs
    """
    
    def __init__(self, mq135_pin=17, dht11_pin=4, gps_enabled=True):
        """
        Initialise tous les capteurs
        
        Cette méthode initialise tous les capteurs du système avec leurs
        configurations respectives (broches GPIO, activation/désactivation).
        
        Args:
            mq135_pin (int): Pin GPIO pour le MQ-135 (défaut: GPIO 17)
            dht11_pin (int): Pin GPIO pour le DHT11 (défaut: GPIO 4)
            gps_enabled (bool): Activer ou désactiver le GPS (défaut: True)
                             Le GPS peut être désactivé si non utilisé
        """
        logger.info("🚀 Initialisation du système de capteurs...")
        logger.info(f"SensorManager config: mq135_pin={mq135_pin}, dht11_pin={dht11_pin}, gps_enabled={gps_enabled}, HARDWARE_AVAILABLE={HARDWARE_AVAILABLE}")
        
        # Initialiser chaque capteur
        self.mq135 = MQ135Sensor(mq135_pin)  # Capteur de qualité de l'air
        self.dht11 = DHT11Sensor(dht11_pin)  # Capteur de température/humidité
        self.gps = GPSSensor() if gps_enabled else None  # GPS (optionnel)
        
        logger.info("✓ Tous les capteurs sont initialisés")
    
    def read_all_sensors(self):
        """
        Lit tous les capteurs et retourne les données agrégées
        
        Cette méthode lit tous les capteurs simultanément et agrège les données
        dans un dictionnaire structuré. Si un capteur échoue, sa valeur est
        définie à None mais le système continue de fonctionner.
        
        Returns:
            dict: Dictionnaire contenant toutes les données des capteurs:
                  - timestamp: Heure de la lecture (ISO format)
                  - air_quality: Dictionnaire avec ppm et raw_value
                  - temperature: Température en °C (None si erreur)
                  - humidity: Humidité en % (None si erreur)
                  - location: Dictionnaire avec latitude, longitude, fix (None si GPS désactivé)
        """
        logger.info("📊 Lecture de tous les capteurs...")
        
        # Lire chaque capteur individuellement
        mq135_data = self.mq135.read()  # Lire le MQ-135
        dht11_data = self.dht11.read()  # Lire le DHT11
        gps_data = self.gps.read() if self.gps else None  # Lire le GPS si activé
        
        # Agréger les données dans un dictionnaire structuré
        aggregated_data = {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {
                'ppm': mq135_data['ppm'] if mq135_data else None,
                'raw_value': mq135_data['raw_value'] if mq135_data else None
            },
            'temperature': dht11_data['temperature'] if dht11_data else None,
            'humidity': dht11_data['humidity'] if dht11_data else None,
            'location': {
                'latitude': gps_data['latitude'] if gps_data else None,
                'longitude': gps_data['longitude'] if gps_data else None,
                'fix': gps_data['fix'] if gps_data else False
            } if gps_data else None
        }
        
        logger.info("✓ Lecture de tous les capteurs terminée")
        return aggregated_data
    
    def cleanup(self):
        """
        Nettoie toutes les ressources des capteurs
        
        Cette méthode libère toutes les ressources GPIO utilisées par les capteurs.
        Elle doit être appelée avant de terminer le programme pour éviter
        les problèmes de verrouillage des broches GPIO.
        
        Opérations de nettoyage:
        - Nettoyage des broches GPIO (GPIO.cleanup())
        - Libération des ressources du DHT11 (sensor.exit())
        """
        logger.info("🧹 Nettoyage des ressources...")
        
        GPIO.cleanup()  # Libérer toutes les broches GPIO
        
        self.dht11.cleanup()  # Libérer les ressources du DHT11
        
        logger.info("✓ Nettoyage terminé")
# ============= TEST DU MODULE =============
# Ce bloc de code est exécuté uniquement si le script est lancé directement
# (pas lorsqu'il est importé comme module). Il permet de tester les capteurs
# individuellement sans lancer le système complet.

if __name__ == "__main__":
    print("=== Test du système de capteurs ===\n")
    
    # Créer le gestionnaire de capteurs avec les broches par défaut
    sensor_manager = SensorManager()
    
    try:
        # Lire les capteurs 5 fois avec un délai de 3 secondes entre chaque lecture
        for i in range(5):
            print(f"\n--- Lecture {i + 1}/5 ---")
            
            # Lire tous les capteurs
            data = sensor_manager.read_all_sensors()
            
            # Afficher les données de chaque capteur
            print(f"Qualité de l'air: {data['air_quality']['ppm']} PPM")
            print(f"Température: {data['temperature']}°C")
            print(f"Humidité: {data['humidity']}%")
            
            # Afficher les coordonnées GPS si disponibles
            if data['location']:
                print(f"Position: {data['location']['latitude']}, {data['location']['longitude']}")
            
            # Attendre 3 secondes avant la prochaine lecture
            time.sleep(3)
            
    except KeyboardInterrupt:
        # Gérer l'interruption par Ctrl+C
        print("\n\n⚠ Arrêt demandé par l'utilisateur")
    finally:
        # Nettoyer les ressources avant de quitter
        sensor_manager.cleanup()
        print("\n✓ Test terminé")
