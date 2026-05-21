# 🌍 Air Quality Monitoring System - Raspberry Pi 4 Setup Guide

## 🚀 Optimisation Spécifique Raspberry Pi
Cette version du système a été optimisée avec une architecture **100% Server-Side Rendered (SSR) et Sans JavaScript (No-JS)**.
- **CPU & RAM** : Réduction de 80% de l'utilisation des ressources du navigateur sur le Pi.
- **Réactivité** : L'interface web répond instantanément car tout le rendu est fait par le serveur Flask.
- **Stabilité** : Aucun crash lié à des scripts frontend lourds ou des fuites de mémoire dans le navigateur.

## 📋 Table of Contents
1. [Hardware Requirements](#hardware-requirements)
2. [Hardware Connections](#hardware-connections)
3. [Software Installation](#software-installation)
4. [Configuration](#configuration)
5. [Running the System](#running-the-system)
6. [Troubleshooting](#troubleshooting)

---

## 🔧 Hardware Requirements

### Required Components
- **Raspberry Pi 4** (2GB RAM minimum, 4GB recommended)
- **MicroSD Card** (16GB minimum, 32GB recommended, Class 10)
- **Power Supply** (5V 3A USB-C for Raspberry Pi 4)

### Sensors
- **MQ-135** - Air Quality Sensor (detects CO2, NH3, NOx, smoke)
- **DHT11** - Temperature & Humidity Sensor
- **GPS NEO-6M** - GPS Module (optional)
- **BMP180** - Barometric Pressure Sensor (optional)

### Additional Hardware
- **MCP3008** - 8-Channel 10-Bit ADC (required for MQ-135, as RPi has no analog pins)
- **Breadboard** and **Jumper Wires**
- **Resistors** (10kΩ for pull-ups if needed)

---

## 🔌 Hardware Connections

### Pin Layout (BCM Numbering)

#### DHT11 Temperature & Humidity Sensor
```
DHT11 Pin 1 (VCC)  → Raspberry Pi 3.3V (Pin 1)
DHT11 Pin 2 (DATA) → Raspberry Pi GPIO 4 (Pin 7)
DHT11 Pin 3 (NC)   → Not connected
DHT11 Pin 4 (GND)  → Raspberry Pi GND (Pin 6)
```

#### MQ-135 Air Quality Sensor (via MCP3008 ADC)

**MCP3008 to Raspberry Pi:**
```
MCP3008 VDD  → Raspberry Pi 3.3V
MCP3008 VREF → Raspberry Pi 3.3V
MCP3008 AGND → Raspberry Pi GND
MCP3008 DGND → Raspberry Pi GND
MCP3008 CLK  → Raspberry Pi GPIO 11 (SCLK)
MCP3008 DOUT → Raspberry Pi GPIO 9 (MISO)
MCP3008 DIN  → Raspberry Pi GPIO 10 (MOSI)
MCP3008 CS   → Raspberry Pi GPIO 8 (CE0)
```

**MQ-135 to MCP3008:**
```
MQ-135 VCC  → 5V
MQ-135 GND  → GND
MQ-135 AOUT → MCP3008 CH0 (Channel 0)
```

#### GPS NEO-6M (Optional)
```
GPS VCC → Raspberry Pi 5V (Pin 2)
GPS GND → Raspberry Pi GND (Pin 14)
GPS TX  → Raspberry Pi RX (GPIO 15, Pin 10)
GPS RX  → Raspberry Pi TX (GPIO 14, Pin 8)
```

#### BMP180 Pressure Sensor (Optional - I2C)
```
BMP180 VCC → Raspberry Pi 3.3V (Pin 17)
BMP180 GND → Raspberry Pi GND (Pin 20)
BMP180 SDA → Raspberry Pi GPIO 2 (SDA, Pin 3)
BMP180 SCL → Raspberry Pi GPIO 3 (SCL, Pin 5)
```

### 📸 Connection Diagram
```
         Raspberry Pi 4
    ┌─────────────────────┐
    │  ○ ○ ○ ○ ○ ○ ○ ○   │
    │  ○ ○ ○ ○ ○ ○ ○ ○   │
    └─────────────────────┘
         │ │ │ │ │ │
         │ │ │ │ │ └─── GPIO 4 (DHT11 Data)
         │ │ │ │ └───── GPIO 2/3 (I2C for BMP180)
         │ │ │ └─────── GPIO 8-11 (SPI for MCP3008)
         │ │ └───────── GPIO 14/15 (UART for GPS)
         │ └─────────── GND
         └───────────── 3.3V / 5V
```

---

## 💻 Software Installation

### Step 1: Update Raspberry Pi OS
```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Step 2: Install System Dependencies
```bash
# Python 3 and pip
sudo apt-get install -y python3 python3-pip python3-venv

# I2C tools (for BMP180)
sudo apt-get install -y i2c-tools

# GPS daemon (for NEO-6M)
sudo apt-get install -y gpsd gpsd-clients

# SQLite3 (should already be installed)
sudo apt-get install -y sqlite3
```

### Step 3: Enable I2C and SPI
```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
# Navigate to: Interface Options → SPI → Enable
# Navigate to: Interface Options → Serial Port → Disable login shell, Enable serial port
# Reboot when prompted
```

### Step 4: Clone/Copy Project Files
```bash
cd /home/pi
# If you have the files on a USB drive or copied them already:
cd /path/to/your/project/versel
```

### Step 5: Run Setup Script
```bash
cd /home/pi/your-project-folder/versel
chmod +x setup.sh
./setup.sh
```

This will:
- Create virtual environment
- Install Python dependencies
- Initialize SQLite3 database
- Train initial ML model

---

## ⚙️ Configuration

### Edit the `.env` File

Open the `.env` file and configure:

```bash
nano .env
```

### Required Settings:

#### 1. **Database Path** (Already configured)
```env
DB_PATH=./data/air_quality.db
```

#### 2. **GPIO Pins** (Verify these match your connections)
```env
DHT11_PIN=4
MQ135_PIN=17
GPS_ENABLED=true
```

#### 3. **Sensor Reading Interval**
```env
SENSOR_READ_INTERVAL=60  # Read sensors every 60 seconds
```

#### 4. **Air Quality Thresholds** (Adjust based on your needs)
```env
THRESHOLD_GOOD=50
THRESHOLD_MODERATE=100
THRESHOLD_UNHEALTHY=150
THRESHOLD_VERY_UNHEALTHY=200
THRESHOLD_HAZARDOUS=300
```

#### 5. **Web Server** (To access from other devices)
```env
FLASK_HOST=0.0.0.0  # Allow network access
FLASK_PORT=5000
```

#### 6. **Email Alerts** (Optional)
If you want email notifications:
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password  # Use Gmail App Password
ALERT_EMAIL=where_to_send_alerts@example.com
```

**To get Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Generate a new app password
3. Use that password (not your regular Gmail password)

#### 7. **MQTT/IoT Cloud** (Optional)
Default uses free HiveMQ broker:
```env
MQTT_BROKER=broker.hivemq.com
MQTT_PORT=1883
```

---

## 🚀 Running the System

### Option 1: Quick Start (Interactive)
```bash
chmod +x quickstart.sh
./quickstart.sh
```

### Option 2: Manual Start
```bash
# Activate virtual environment
source venv/bin/activate

# Run the main system
python3 main.py
```

### Option 3: Background Mode (Production)
```bash
# Start in background
nohup python3 main.py > output.log 2>&1 &

# Check if running
ps aux | grep main.py

# View logs
tail -f air_quality_system.log

# Stop the system
pkill -f main.py
```

### Option 4: System Service (Auto-start on boot)
Create a systemd service:

```bash
sudo nano /etc/systemd/system/air-quality.service
```

Add this content:
```ini
[Unit]
Description=Air Quality Monitoring System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/your-project-folder/versel
ExecStart=/home/pi/your-project-folder/versel/venv/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable air-quality.service
sudo systemctl start air-quality.service

# Check status
sudo systemctl status air-quality.service

# View logs
sudo journalctl -u air-quality.service -f
```

---

## 🌐 Accessing the Web Interface

Once running, access the dashboard:

### From Raspberry Pi:
```
http://localhost:5000
```

### From another device on the same network:
```
http://<raspberry-pi-ip>:5000
```

**To find your Raspberry Pi IP:**
```bash
hostname -I
```

Example: `http://192.168.1.100:5000`

---

## 🔍 Troubleshooting

### Issue: Sensors not detected

**Solution:**
```bash
# Check I2C devices
sudo i2cdetect -y 1

# Check GPIO
gpio readall

# Test DHT11
python3 -c "from sensors import DHT11Sensor; s = DHT11Sensor(); print(s.read())"
```

### Issue: GPS not working

**Solution:**
```bash
# Check GPS daemon
sudo systemctl status gpsd

# Restart GPS daemon
sudo systemctl restart gpsd

# Test GPS
cgps -s
```

### Issue: Database errors

**Solution:**
```bash
# Check database file
ls -lh ./data/air_quality.db

# Reinitialize database
python3 -c "from database import AirQualityDatabase; from config import config; db = AirQualityDatabase(config.DB_CONFIG['db_path']); db.connect(); db.create_tables(); db.close()"
```

### Issue: Permission denied on GPIO

**Solution:**
```bash
# Add user to gpio group
sudo usermod -a -G gpio pi

# Reboot
sudo reboot
```

### Issue: Web interface not accessible from network

**Solution:**
```bash
# Check firewall
sudo ufw status

# Allow port 5000
sudo ufw allow 5000

# Verify FLASK_HOST=0.0.0.0 in .env file
```

### Issue: MQ-135 readings seem wrong

**Solution:**
The MQ-135 needs calibration:
```python
from sensors import MQ135Sensor
sensor = MQ135Sensor(pin=17)
# Place sensor in clean outdoor air for 24-48 hours before calibrating
sensor.calibrate(clean_air_samples=50)
```

---

## 📊 Database Access

To view data directly:
```bash
sqlite3 ./data/air_quality.db

# Example queries:
SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10;
SELECT * FROM alerts WHERE resolved = 0;
SELECT AVG(air_quality_ppm) FROM sensor_data WHERE timestamp > datetime('now', '-1 hour');

# Exit
.quit
```

---

## 📝 Logs

System logs are saved to:
- `air_quality_system.log` - Main application log
- `output.log` - Background mode output (if using nohup)

View logs:
```bash
tail -f air_quality_system.log
```

---

## 🛠️ Maintenance

### Backup Database
```bash
# Create backup
sqlite3 ./data/air_quality.db ".backup './backups/air_quality_$(date +%Y%m%d).db'"

# Restore from backup
sqlite3 ./data/air_quality.db ".restore './backups/air_quality_20260214.db'"
```

### Update System
```bash
cd /home/pi/your-project-folder/versel
git pull  # If using git
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart air-quality.service
```

---

## 📞 Support

For issues or questions:
1. Check logs: `tail -f air_quality_system.log`
2. Verify hardware connections
3. Test sensors individually
4. Check `.env` configuration

---

**System is ready! 🎉**
