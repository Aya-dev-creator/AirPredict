"""
Module de gestion des capteurs Raspberry Pi
Gère la lecture des capteurs: MQ-135 (qualité de l'air), DHT11 (température/humidité), GPS NEO-6M, BMP180 (pression/température)
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

try:
    import smbus # type: ignore
    BMP180_AVAILABLE = True
except ImportError:
    BMP180_AVAILABLE = False
    logger.warning("⚠ Module BMP180 (smbus) non disponible")


class MQ135Sensor:
    """
    Classe pour gérer le capteur MQ-135 (qualité de l'air)
    Ce capteur détecte: CO2, NH3, NOx, alcool, benzène, fumée, CO
    """
    def __init__(self, pin=17):
        """
        Initialise le capteur MQ-135
        Args:
            pin (int): Numéro du pin GPIO (par défaut 17)
        """
        self.pin = pin
        self.r0 = 10.0  # Résistance de calibration (à ajuster selon votre capteur)
        
        if RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN)
            logger.info(f"✓ Capteur MQ-135 initialisé sur GPIO {self.pin}")
        else:
            logger.warning("⚠ Mode simulation MQ-135 activé")
    
    def read_analog_value(self):
        """
        Lit la valeur analogique du capteur MQ-135
        Note: Le MQ-135 nécessite un convertisseur ADC (comme MCP3008) car le Raspberry Pi
        n'a pas d'entrées analogiques natives
        
        Returns:
            int: Valeur analogique (0-1023)
        """
        if not RPI_AVAILABLE:
            # Simulation: génère une valeur aléatoire
            import random
            return random.randint(200, 800)
        
        # TODO: Implémenter la lecture via ADC (MCP3008)
        try:
            value = GPIO.input(self.pin)
            return value * 512
        except Exception as e:
            logger.error(f"✗ Erreur lecture MQ-135: {e}")
            return 0
    
    def calculate_ppm(self, analog_value):
        """
        Convertit la valeur analogique en PPM (parties par million)
        
        Args:
            analog_value (int): Valeur analogique du capteur
        
        Returns:
            float: Concentration en PPM
        """
        voltage = (analog_value / 1023.0) * 5.0
        rs = ((5.0 * 10.0) / voltage) - 10.0
        
        if rs <= 0:
            return 0
        
        ratio = rs / self.r0
        ppm = 116.6020682 * (ratio ** -2.769034857)
        
        return max(0, ppm)
    
    def read(self):
        """
        Effectue une lecture complète du capteur
        
        Returns:
            dict: Données du capteur avec valeur brute et PPM
        """
        try:
            analog_value = self.read_analog_value()
            ppm = self.calculate_ppm(analog_value)
            
            data = {
                'sensor': 'MQ-135',
                'timestamp': datetime.now().isoformat(),
                'raw_value': analog_value,
                'ppm': round(ppm, 2),
                'unit': 'PPM'
            }
            
            logger.info(f"📊 MQ-135: {ppm:.2f} PPM")
            return data
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture MQ-135: {e}")
            return None
    
    def calibrate(self, clean_air_samples=50):
        """
        Calibre le capteur dans un environnement d'air propre
        À exécuter au premier démarrage dans un environnement extérieur propre
        
        Args:
            clean_air_samples (int): Nombre d'échantillons pour la calibration
        
        Returns:
            float: Valeur R0 calibrée
        """
        logger.info("🔧 Début de la calibration MQ-135 (gardez le capteur dans l'air propre)...")
        rs_sum = 0
        
        for i in range(clean_air_samples):
            analog_value = self.read_analog_value()
            voltage = (analog_value / 1023.0) * 5.0
            rs = ((5.0 * 10.0) / voltage) - 10.0
            rs_sum += rs
            
            if (i + 1) % 10 == 0:
                logger.info(f"Calibration: {i + 1}/{clean_air_samples} échantillons")
            time.sleep(0.5)
        
        self.r0 = (rs_sum / clean_air_samples) / 3.6
        logger.info(f"✓ Calibration terminée - R0 = {self.r0:.2f}")
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
            pin_board = getattr(board, f'D{pin}')
            self.sensor = adafruit_dht.DHT11(pin_board)
            logger.info(f"✓ Capteur DHT11 initialisé sur GPIO {self.pin}")
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
                import random
                temperature = round(random.uniform(15.0, 35.0), 1)
                humidity = round(random.uniform(30.0, 80.0), 1)
            else:
                temperature = self.sensor.temperature
                humidity = self.sensor.humidity
                
                if temperature is None or humidity is None:
                    logger.warning("⚠ Échec de lecture DHT11, réessai...")
                    time.sleep(2)
                    temperature = self.sensor.temperature
                    humidity = self.sensor.humidity
            
            if temperature is None or humidity is None:
                raise Exception("Données DHT11 invalides")
            
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
            return None
    
    def cleanup(self):
        """Nettoie les ressources du capteur"""
        if RPI_AVAILABLE and self.sensor:
            self.sensor.exit()


class BMP180Sensor:
    """
    Classe pour gérer le capteur BMP180 (pression atmosphérique et température)
    Le BMP180 communique via I2C
    """
    # Adresse I2C par défaut du BMP180
    BMP180_ADDRESS = 0x77
    
    # Registres du BMP180
    REG_CONTROL = 0xF4
    REG_RESULT = 0xF6
    REG_CALIB = 0xAA
    
    # Commandes
    CMD_TEMP = 0x2E
    CMD_PRESSURE = 0x34
    
    def __init__(self, address=0x77, bus=1):
        """
        Initialise le capteur BMP180
        
        Args:
            address (int): Adresse I2C du capteur (par défaut 0x77)
            bus (int): Numéro du bus I2C (par défaut 1)
        """
        self.address = address
        self.bus_number = bus
        self.bus = None
        
        # Coefficients de calibration
        self.cal_ac1 = 0
        self.cal_ac2 = 0
        self.cal_ac3 = 0
        self.cal_ac4 = 0
        self.cal_ac5 = 0
        self.cal_ac6 = 0
        self.cal_b1 = 0
        self.cal_b2 = 0
        self.cal_mb = 0
        self.cal_mc = 0
        self.cal_md = 0
        
        if BMP180_AVAILABLE and RPI_AVAILABLE:
            try:
                self.bus = smbus.SMBus(bus)
                self._read_calibration_data()
                logger.info(f"✓ Capteur BMP180 initialisé sur I2C {hex(self.address)}")
            except Exception as e:
                logger.error(f"✗ Erreur initialisation BMP180: {e}")
                self.bus = None
        else:
            logger.warning("⚠ Mode simulation BMP180 activé")
    
    def _read_calibration_data(self):
        """Lit les données de calibration depuis le capteur"""
        if self.bus is None:
            return
        
        try:
            # Lire les coefficients de calibration (22 octets à partir de 0xAA)
            cal_data = self.bus.read_i2c_block_data(self.address, self.REG_CALIB, 22)
            
            # Conversion des octets en valeurs signées/non signées
            self.cal_ac1 = self._bytes_to_int(cal_data[0], cal_data[1], signed=True)
            self.cal_ac2 = self._bytes_to_int(cal_data[2], cal_data[3], signed=True)
            self.cal_ac3 = self._bytes_to_int(cal_data[4], cal_data[5], signed=True)
            self.cal_ac4 = self._bytes_to_int(cal_data[6], cal_data[7], signed=False)
            self.cal_ac5 = self._bytes_to_int(cal_data[8], cal_data[9], signed=False)
            self.cal_ac6 = self._bytes_to_int(cal_data[10], cal_data[11], signed=False)
            self.cal_b1 = self._bytes_to_int(cal_data[12], cal_data[13], signed=True)
            self.cal_b2 = self._bytes_to_int(cal_data[14], cal_data[15], signed=True)
            self.cal_mb = self._bytes_to_int(cal_data[16], cal_data[17], signed=True)
            self.cal_mc = self._bytes_to_int(cal_data[18], cal_data[19], signed=True)
            self.cal_md = self._bytes_to_int(cal_data[20], cal_data[21], signed=True)
            
            logger.info("✓ Données de calibration BMP180 chargées")
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture calibration BMP180: {e}")
    
    def _bytes_to_int(self, msb, lsb, signed=False):
        """
        Convertit deux octets en entier
        
        Args:
            msb: Octet de poids fort
            lsb: Octet de poids faible
            signed: Si True, traite comme un entier signé
        
        Returns:
            int: Valeur convertie
        """
        value = (msb << 8) | lsb
        if signed and value >= 0x8000:
            value -= 0x10000
        return value
    
    def _read_raw_temperature(self):
        """
        Lit la température brute du capteur
        
        Returns:
            int: Valeur brute de température
        """
        if self.bus is None:
            return 0
        
        try:
            # Démarrer la mesure de température
            self.bus.write_byte_data(self.address, self.REG_CONTROL, self.CMD_TEMP)
            time.sleep(0.005)  # Attendre 4.5ms
            
            # Lire le résultat
            data = self.bus.read_i2c_block_data(self.address, self.REG_RESULT, 2)
            return self._bytes_to_int(data[0], data[1])
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture température brute BMP180: {e}")
            return 0
    
    def _read_raw_pressure(self, oversampling=3):
        """
        Lit la pression brute du capteur
        
        Args:
            oversampling: Mode de suréchantillonnage (0-3, défaut 3 pour haute résolution)
        
        Returns:
            int: Valeur brute de pression
        """
        if self.bus is None:
            return 0
        
        try:
            # Démarrer la mesure de pression
            cmd = self.CMD_PRESSURE + (oversampling << 6)
            self.bus.write_byte_data(self.address, self.REG_CONTROL, cmd)
            
            # Attendre selon le mode de suréchantillonnage
            delays = [0.005, 0.008, 0.014, 0.026]
            time.sleep(delays[oversampling])
            
            # Lire le résultat (3 octets)
            data = self.bus.read_i2c_block_data(self.address, self.REG_RESULT, 3)
            raw_pressure = ((data[0] << 16) | (data[1] << 8) | data[2]) >> (8 - oversampling)
            return raw_pressure
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture pression brute BMP180: {e}")
            return 0
    
    def read_temperature(self):
        """
        Calcule la température compensée en °C
        
        Returns:
            float: Température en degrés Celsius
        """
        if self.bus is None:
            # Mode simulation
            import random
            return round(random.uniform(15.0, 35.0), 1)
        
        try:
            ut = self._read_raw_temperature()
            
            # Calcul de la température selon la datasheet BMP180
            x1 = ((ut - self.cal_ac6) * self.cal_ac5) >> 15
            x2 = (self.cal_mc << 11) // (x1 + self.cal_md)
            b5 = x1 + x2
            temperature = ((b5 + 8) >> 4) / 10.0
            
            return round(temperature, 1)
            
        except Exception as e:
            logger.error(f"✗ Erreur calcul température BMP180: {e}")
            return None
    
    def read_pressure(self, oversampling=3):
        """
        Calcule la pression compensée en Pa
        
        Args:
            oversampling: Mode de suréchantillonnage (0-3)
        
        Returns:
            float: Pression en Pascals
        """
        if self.bus is None:
            # Mode simulation
            import random
            return round(random.uniform(99000, 102000), 0)
        
        try:
            # Lire température d'abord pour la compensation
            ut = self._read_raw_temperature()
            up = self._read_raw_pressure(oversampling)
            
            # Calcul de b5 pour la compensation
            x1 = ((ut - self.cal_ac6) * self.cal_ac5) >> 15
            x2 = (self.cal_mc << 11) // (x1 + self.cal_md)
            b5 = x1 + x2
            
            # Calcul de la pression selon la datasheet
            b6 = b5 - 4000
            x1 = (self.cal_b2 * ((b6 * b6) >> 12)) >> 11
            x2 = (self.cal_ac2 * b6) >> 11
            x3 = x1 + x2
            b3 = (((self.cal_ac1 * 4 + x3) << oversampling) + 2) // 4
            
            x1 = (self.cal_ac3 * b6) >> 13
            x2 = (self.cal_b1 * ((b6 * b6) >> 12)) >> 16
            x3 = ((x1 + x2) + 2) >> 2
            b4 = (self.cal_ac4 * (x3 + 32768)) >> 15
            b7 = (up - b3) * (50000 >> oversampling)
            
            if b7 < 0x80000000:
                pressure = (b7 * 2) // b4
            else:
                pressure = (b7 // b4) * 2
            
            x1 = (pressure >> 8) * (pressure >> 8)
            x1 = (x1 * 3038) >> 16
            x2 = (-7357 * pressure) >> 16
            pressure = pressure + ((x1 + x2 + 3791) >> 4)
            
            return float(pressure)
            
        except Exception as e:
            logger.error(f"✗ Erreur calcul pression BMP180: {e}")
            return None
    
    def calculate_altitude(self, pressure, sea_level_pressure=101325):
        """
        Calcule l'altitude approximative en fonction de la pression
        
        Args:
            pressure: Pression mesurée en Pa
            sea_level_pressure: Pression au niveau de la mer en Pa (défaut 101325)
        
        Returns:
            float: Altitude en mètres
        """
        if pressure is None or pressure <= 0:
            return None
        
        altitude = 44330.0 * (1.0 - pow(pressure / sea_level_pressure, 0.1903))
        return round(altitude, 1)
    
    def read(self):
        """
        Effectue une lecture complète du capteur BMP180
        
        Returns:
            dict: Données de température, pression et altitude
        """
        try:
            temperature = self.read_temperature()
            pressure = self.read_pressure()
            altitude = self.calculate_altitude(pressure) if pressure else None
            
            data = {
                'sensor': 'BMP180',
                'timestamp': datetime.now().isoformat(),
                'temperature': temperature,
                'pressure': round(pressure, 2) if pressure else None,
                'pressure_hpa': round(pressure / 100, 2) if pressure else None,
                'altitude': altitude,
                'temp_unit': '°C',
                'pressure_unit': 'Pa',
                'altitude_unit': 'm'
            }
            
            if pressure:
                logger.info(f"🌡️ BMP180: {temperature}°C, {pressure/100:.2f} hPa")
            
            return data
            
        except Exception as e:
            logger.error(f"✗ Erreur lecture BMP180: {e}")
            return None


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
    def __init__(self, mq135_pin=17, dht11_pin=4, gps_enabled=True, bmp180_enabled=True):
        """
        Initialise tous les capteurs
        
        Args:
            mq135_pin (int): Pin GPIO pour MQ-135
            dht11_pin (int): Pin GPIO pour DHT11
            gps_enabled (bool): Activer le GPS
            bmp180_enabled (bool): Activer le BMP180
        """
        logger.info("🚀 Initialisation du système de capteurs...")
        
        self.mq135 = MQ135Sensor(mq135_pin)
        self.dht11 = DHT11Sensor(dht11_pin)
        self.gps = GPSSensor() if gps_enabled else None
        self.bmp180 = BMP180Sensor() if bmp180_enabled else None
        
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
        bmp180_data = self.bmp180.read() if self.bmp180 else None
        
        # Agréger les données
        aggregated_data = {
            'timestamp': datetime.now().isoformat(),
            'air_quality': {
                'ppm': mq135_data['ppm'] if mq135_data else None,
                'raw_value': mq135_data['raw_value'] if mq135_data else None
            },
            'temperature': dht11_data['temperature'] if dht11_data else None,
            'humidity': dht11_data['humidity'] if dht11_data else None,
            'pressure': {
                'pa': bmp180_data['pressure'] if bmp180_data else None,
                'hpa': bmp180_data['pressure_hpa'] if bmp180_data else None,
                'altitude': bmp180_data['altitude'] if bmp180_data else None
            } if bmp180_data else None,
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
            
            if data['pressure']:
                print(f"Pression: {data['pressure']['hpa']} hPa")
                print(f"Altitude: {data['pressure']['altitude']} m")
            
            if data['location']:
                print(f"Position: {data['location']['latitude']}, {data['location']['longitude']}")
            
            time.sleep(3)
            
    except KeyboardInterrupt:
        print("\n\n⚠ Arrêt demandé par l'utilisateur")
    finally:
        sensor_manager.cleanup()
        print("\n✓ Test terminé")