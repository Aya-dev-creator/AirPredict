"""
Module de gestion des capteurs Raspberry Pi
Gère la lecture des capteurs: MQ-135 (qualité de l'air), DHT11 (température/humidité), GPS NEO-6M
"""
import time
import logging
from datetime import datetime
# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Importation conditionnelle pour permettre le développement hors Raspberry Pi
try:
    import RPi.GPIO as GPIO # type: ignore
    import adafruit_dht # type: ignore
    import board # type: ignore
    RPI_AVAILABLE = True
    logger.info("✓ Modules Raspberry Pi chargés avec succès")
except ImportError:
    RPI_AVAILABLE = False
    logger.warning("⚠ Modules Raspberry Pi non disponibles - Mode simulation activé")
try:
    from gpsd import gps, WATCH_ENABLE # type: ignore
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    logger.warning("⚠ Module GPS non disponible")
    # Ajout au début du fichier après les imports existants
try:
    import board # type: ignore
    import busio # type: ignore
    import adafruit_ads1x15.ads1115 as ADS # type: ignore
    from adafruit_ads1x15.analog_in import AnalogIn # type: ignore
    ADS_AVAILABLE = True
except ImportError:
    ADS_AVAILABLE = False
    logger.warning("⚠ Module ADS1115 non disponible")

# Modification de la classe MQ135Sensor

class MQ135Sensor:
    """
    Classe pour gérer le capteur MQ-135 (qualité de l'air)
    Utilise l'ADS1115 pour la lecture analogique
    """
    def __init__(self, digital_pin=17, adc_channel=0, pin=None):
        """
        Initialise le capteur MQ-135
        Args:
            digital_pin (int): Pin GPIO pour sortie digitale DOUT (par défaut 17)
            adc_channel (int): Canal ADC de l'ADS1115 (0-3, par défaut 0)
        """
        # Compatibilité avec l'ancienne signature MQ135Sensor(pin=17)
        if pin is not None:
            digital_pin = pin

        self.digital_pin = digital_pin
        self.adc_channel = adc_channel
        self.r0 = 10.0  # Résistance de calibration
        self.ads = None
        self.adc_channel_obj = None
        
        # Initialiser l'ADS1115 avec gestion d'erreur améliorée
        if ADS_AVAILABLE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                
                # Attendre que le bus I2C soit disponible
                while not i2c.try_lock():
                    time.sleep(0.1)
                
                # Scanner les adresses I2C disponibles
                logger.info("Scanning I2C bus...")
                addresses = i2c.scan()
                i2c.unlock()
                
                if addresses:
                    logger.info(f"Adresses I2C trouvées: {[hex(addr) for addr in addresses]}")
                else:
                    logger.warning("Aucune adresse I2C trouvée")
                
                # Initialiser ADS1115 avec plusieurs tentatives
                for attempt in range(3):
                    try:
                        self.ads = ADS.ADS1115(i2c, address=0x48)  # Adresse par défaut
                        
                        # Vérifier la configuration des canaux
                        channel_map = {0: ADS.P0, 1: ADS.P1, 2: ADS.P2, 3: ADS.P3}
                        channel_attr = channel_map.get(adc_channel, ADS.P0)
                        
                        self.adc_channel_obj = AnalogIn(self.ads, channel_attr)
                        logger.info(f"✓ ADS1115 initialisé sur canal {adc_channel} (adresse 0x48)")
                        break
                    except ValueError as e:
                        if "0x48" in str(e):
                            logger.warning(f"Tentative {attempt + 1}/3: {e}")
                            time.sleep(1)
                        else:
                            raise
                    except Exception as e:
                        logger.error(f"Erreur initialisation ADS1115: {e}")
                        break
                        
                if self.adc_channel_obj is None:
                    logger.error("Impossible d'initialiser l'ADS1115 après plusieurs tentatives")
                    
            except Exception as e:
                logger.error(f"✗ Erreur initialisation ADS1115/I2C: {e}")
                self.adc_channel_obj = None
        else:
            self.adc_channel_obj = None
            logger.warning("⚠ Mode simulation MQ-135 activé (ADS1115 non disponible)")
            
        # Initialiser le pin digital (optionnel)
        if RPI_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.digital_pin, GPIO.IN)
                logger.info(f"✓ Capteur MQ-135 DOUT initialisé sur GPIO {self.digital_pin}")
            except Exception as e:
                logger.error(f"Erreur initialisation GPIO: {e}")
        else:
            logger.warning("⚠ GPIO non disponible pour MQ-135")
    
    def read_analog_value(self):
        """
        Lit la valeur analogique du capteur MQ-135 via ADS1115
        Returns:
            int: Valeur analogique (0-26400 pour ADS1115 16-bit)
        """
        if not ADS_AVAILABLE or self.adc_channel_obj is None:
            # Mode simulation
            import random
            return random.randint(5000, 20000)
        
        try:
            # Lire la valeur de l'ADS1115
            value = self.adc_channel_obj.value
            voltage = self.adc_channel_obj.voltage
            logger.debug(f"ADS1115 - Raw: {value}, Voltage: {voltage:.3f}V")
            return value
        except Exception as e:
            logger.error(f"✗ Erreur lecture ADS1115: {e}")
            return 0
    
    def read_digital(self):
        """
        Lit la sortie digitale DOUT du MQ-135
        Returns:
            bool: True si seuil dépassé, False sinon
        """
        if not RPI_AVAILABLE:
            return False
        
        try:
            # DOUT est LOW quand le seuil est dépassé
            return GPIO.input(self.digital_pin) == GPIO.LOW
        except Exception as e:
            logger.error(f"✗ Erreur lecture DOUT: {e}")
            return False
    
    def calculate_ppm(self, analog_value):
        """
        Convertit la valeur analogique en PPM
        Args:
            analog_value (int): Valeur de l'ADS1115 (0-26400)
        Returns:
            float: Concentration en PPM
        """
        # Convertir en tension (ADS1115: 16-bit, ±4.096V par défaut)
        voltage = (analog_value / 26400.0) * 4.096
        
        # Éviter division par zéro
        if voltage <= 0.1:
            return 0
        
        # Calculer Rs (résistance du capteur)
        # Circuit: 5V -- RL=10kΩ -- MQ135(Rs) -- GND
        # Voltage mesuré aux bornes de RL
        rs = ((5.0 - voltage) * 10.0) / voltage
        
        if rs <= 0:
            return 0
        
        # Ratio Rs/R0
        ratio = rs / self.r0
        
        # Formule pour CO2 (courbe du datasheet)
        ppm = 116.6020682 * (ratio ** -2.769034857)
        return max(0, ppm)
    
    def read(self):
        """
        Effectue une lecture complète du capteur
        Returns:
            dict: Données du capteur
        """
        try:
            analog_value = self.read_analog_value()
            ppm = self.calculate_ppm(analog_value)
            digital_alert = self.read_digital()
            
            data = {
                'sensor': 'MQ-135',
                'timestamp': datetime.now().isoformat(),
                'raw_value': analog_value,
                'ppm': round(ppm, 2),
                'unit': 'PPM',
                'alert': digital_alert
            }
            
            alert_msg = " ⚠️ ALERTE!" if digital_alert else ""
            logger.info(f"📊 MQ-135: {ppm:.2f} PPM{alert_msg}")
            return data
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture MQ-135: {e}")
            return None
    
    def calibrate(self, clean_air_samples=50):
        """
        Calibre le capteur dans un environnement d'air propre
        """
        logger.info("🔧 Calibration MQ-135 (laissez le capteur dans l'air propre 24h avant)...")
        rs_sum = 0
        
        for i in range(clean_air_samples):
            analog_value = self.read_analog_value()
            voltage = (analog_value / 26400.0) * 4.096
            
            if voltage > 0.1:
                rs = ((5.0 - voltage) * 10.0) / voltage
                rs_sum += rs
            
            if (i + 1) % 10 == 0:
                logger.info(f"Calibration: {i + 1}/{clean_air_samples}")
            time.sleep(0.5)
        
        # R0 = Rs/3.6 (ratio dans l'air propre)
        self.r0 = (rs_sum / clean_air_samples) / 3.6
        logger.info(f"✓ Calibration terminée - R0 = {self.r0:.2f}Ω")
        return self.r0
class DHT11Sensor:
    """
    Classe pour gérer le capteur DHT11 (température et humidité)
    """
    def __init__(self, pin=4):
        """
        Initialise le capteur DHT11
        Args:
            pin (int): Numéro du pin GPIO (par défaut 4)
        """
        self.pin = pin
        if RPI_AVAILABLE:
            try:
                # Essayer d'abord avec board.D4, sinon utiliser le numéro de pin directement
                try:
                    pin_board = getattr(board, f'D{pin}')
                except AttributeError:
                    # Si D4 n'existe pas, utiliser la notation BOARD
                    pin_board = pin
                
                self.sensor = adafruit_dht.DHT11(pin_board)
                logger.info(f"✓ Capteur DHT11 initialisé sur GPIO {self.pin}")
            except Exception as e:
                logger.error(f"✗ Erreur initialisation DHT11: {e}")
                logger.info("Essaie avec l'initialisation alternative...")
                self.sensor = None
        else:
            self.sensor = None
            logger.warning("⚠ Mode simulation DHT11 activé")
    
    def read(self):
        """
        Lit la température et l'humidité du capteur DHT11
        Returns:
            dict: Données de température et humidité
        """
        try:
            if not RPI_AVAILABLE or self.sensor is None:
                # Mode simulation
                import random
                temperature = round(random.uniform(15.0, 35.0), 1)
                humidity = round(random.uniform(30.0, 80.0), 1)
            else:
                # Lecture réelle du capteur avec gestion d'erreur améliorée
                try:
                    temperature = self.sensor.temperature
                    humidity = self.sensor.humidity
                    
                    # Réessayer en cas d'échec
                    if temperature is None or humidity is None:
                        time.sleep(1)
                        temperature = self.sensor.temperature
                        humidity = self.sensor.humidity
                        
                except RuntimeError as e:
                    logger.warning(f"RuntimeError DHT11: {e}, réessai...")
                    time.sleep(2)
                    temperature = self.sensor.temperature
                    humidity = self.sensor.humidity
                    
            # Vérifier la validité des données
            if temperature is None or humidity is None:
                raise Exception("Données DHT11 invalides après plusieurs tentatives")
                
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
            # Retourner des données par défaut au lieu de None
            return {
                'sensor': 'DHT11',
                'timestamp': datetime.now().isoformat(),
                'temperature': None,
                'humidity': None,
                'temp_unit': '°C',
                'humidity_unit': '%'
            }
            logger.info(f"🌡️ DHT11: {temperature}°C, {humidity}%")
            return data
        except Exception as e:
            logger.error(f"✗ Erreur lecture DHT11: {e}")
            return None
    def cleanup(self):
        """Nettoie les ressources du capteur"""
        if RPI_AVAILABLE and self.sensor:
            self.sensor.exit()
class GPSSensor:
    """
    Classe pour gérer le GPS NEO-6M
    """
    def __init__(self):
        """Initialise le GPS NEO-6M"""
        self.gps_session = None
        if GPS_AVAILABLE:
            try:
                self.gps_session = gps(mode=WATCH_ENABLE)
                logger.info("✓ GPS NEO-6M initialisé")
            except Exception as e:
                logger.error(f"✗ Erreur initialisation GPS: {e}")
                self.gps_session = None
        else:
            logger.warning("⚠ Mode simulation GPS activé")
    def read(self):
        """
        Lit les coordonnées GPS actuelles
        Returns:
            dict: Données de position GPS
        """
        try:
            if not GPS_AVAILABLE or self.gps_session is None:
                # Mode simulation - coordonnées d'exemple (Tunis, Tunisie)
                data = {
                    'sensor': 'GPS NEO-6M',
                    'timestamp': datetime.now().isoformat(),
                    'latitude': 36.8065,
                    'longitude': 10.1815,
                    'altitude': 0,
                    'fix': True,
                    'satellites': 0
                }
            else:
                # Lecture réelle du GPS
                report = self.gps_session.next()
                if report['class'] == 'TPV':
                     data = {
                        'sensor': 'GPS NEO-6M',
                        'timestamp': datetime.now().isoformat(),
                        'latitude': getattr(report, 'lat', 0.0),
                        'longitude': getattr(report, 'lon', 0.0),
                        'altitude': getattr(report, 'alt', 0.0),
                        'speed': getattr(report, 'speed', 0.0),
                        'fix': True,
                        'satellites': getattr(report, 'satellites', 0)
                    }
                else:
                    raise Exception("Pas de fix GPS")
            logger.info(f"📍 GPS: {data['latitude']:.6f}, {data['longitude']:.6f}")
            return data
        except Exception as e:
            logger.error(f"✗ Erreur lecture GPS: {e}")
            return {
                'sensor': 'GPS NEO-6M',
                'timestamp': datetime.now().isoformat(),
                'latitude': None,
                'longitude': None,
                'fix': False
            }
class SensorManager:
    """
    Gestionnaire central pour tous les capteurs
    Coordonne la lecture de tous les capteurs et agrège les données
    """
    def __init__(self, mq135_pin=17, dht11_pin=4, gps_enabled=True):
        """
        Initialise tous les capteurs
        Args:
            mq135_pin (int): Pin GPIO pour MQ-135
            dht11_pin (int): Pin GPIO pour DHT11
            gps_enabled (bool): Activer le GPS
        """
        logger.info("🚀 Initialisation du système de capteurs...")
        self.mq135 = MQ135Sensor(mq135_pin)
        self.dht11 = DHT11Sensor(dht11_pin)
        self.gps = GPSSensor() if gps_enabled else None
        logger.info("✓ Tous les capteurs sont initialisés")
    def read_all_sensors(self):
        """
        Lit tous les capteurs et retourne les données agrégées
        Returns:
            dict: Toutes les données des capteurs
        """
        logger.info("📊 Lecture de tous les capteurs...")
        # Lire chaque capteur
        mq135_data = self.mq135.read()
        dht11_data = self.dht11.read()
        gps_data = self.gps.read() if self.gps else None
        # Agréger les données
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
        """Nettoie toutes les ressources des capteurs"""
        logger.info("🧹 Nettoyage des ressources...")
        if RPI_AVAILABLE:
            GPIO.cleanup()
        self.dht11.cleanup()
        logger.info("✓ Nettoyage terminé")
# Test du module si exécuté directement
if __name__ == "__main__":
    print("=== Test du système de capteurs ===\n")
    # Créer le gestionnaire de capteurs
    sensor_manager = SensorManager()
    try:
         # Lire les capteurs 5 fois avec un délai
        for i in range(5):
            print(f"\n--- Lecture {i + 1}/5 ---")
            data = sensor_manager.read_all_sensors()
            print(f"Qualité de l'air: {data['air_quality']['ppm']} PPM")
            print(f"Température: {data['temperature']}°C")
            print(f"Humidité: {data['humidity']}%")
            if data['location']:
                print(f"Position: {data['location']['latitude']}, {data['location']['longitude']}")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n\n⚠ Arrêt demandé par l'utilisateur")
    finally:
        sensor_manager.cleanup()
        print("\n✓ Test terminé")
