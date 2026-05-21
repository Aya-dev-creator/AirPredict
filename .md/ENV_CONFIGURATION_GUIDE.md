# Quick Reference: .env Configuration

## 🔑 What You MUST Configure

### 1. **Database** (Already set for SQLite3)
```env
DB_PATH=./data/air_quality.db
```
✅ **No changes needed** - SQLite3 is ready to use

---

### 2. **Sensor GPIO Pins**
```env
DHT11_PIN=4        # Temperature/Humidity sensor
MQ135_PIN=17       # Air quality sensor
GPS_ENABLED=true   # Set to 'false' if no GPS connected
```
✅ **Verify these match your physical connections**

---

### 3. **Reading Interval**
```env
SENSOR_READ_INTERVAL=60
```
- **60** = Read sensors every minute (recommended)
- **30** = Every 30 seconds (more data, more processing)
- **300** = Every 5 minutes (less data, saves power)

---

### 4. **Web Server**
```env
FLASK_HOST=0.0.0.0    # Access from any device on network
FLASK_PORT=5000       # Web interface port
FLASK_DEBUG=false     # Keep false for production
```
✅ **No changes needed** - Default settings work well

---

### 5. **Air Quality Thresholds (PPM)**
```env
THRESHOLD_GOOD=50
THRESHOLD_MODERATE=100
THRESHOLD_UNHEALTHY=150
THRESHOLD_VERY_UNHEALTHY=200
THRESHOLD_HAZARDOUS=300
```
✅ **Optional** - Adjust based on your local air quality standards

---

## 📧 Optional: Email Alerts

**Only configure if you want email notifications:**

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
ALERT_EMAIL=where_to_receive_alerts@example.com
```

### How to get Gmail App Password:
1. Go to: https://myaccount.google.com/apppasswords
2. Sign in to your Google account
3. Click "Generate" and copy the 16-character password
4. Use that password (NOT your regular Gmail password)

**If you don't want email alerts:** Leave these fields empty

---

## ☁️ Optional: MQTT/IoT Cloud

**Default uses free HiveMQ broker (no setup needed):**

```env
MQTT_BROKER=broker.hivemq.com
MQTT_PORT=1883
MQTT_TOPIC=air_quality/sensor_data
MQTT_CLIENT_ID=raspberry_pi_air_sensor
MQTT_USERNAME=
MQTT_PASSWORD=
```

✅ **No changes needed** - Works out of the box

**To use a different MQTT broker:** Update the broker address and credentials

---

---

## 🤖 Assistant IA (Hugging Face)

**Requis pour faire fonctionner le chat intelligent :**

```env
HF_API_KEY=votre_clé_hugging_face
```

### Comment obtenir une clé API :
1. Créez un compte gratuit sur [huggingface.co](https://huggingface.co/).
2. Allez dans **Settings** → **Access Tokens**.
3. Créez un nouveau token de type "Read" et copiez-le dans le fichier `.env`.

---

---

## ✅ Minimal Configuration Checklist

For basic operation, you only need to verify:

- [x] `DB_PATH=./data/air_quality.db` (already set)
- [x] `DHT11_PIN=4` (verify matches your wiring)
- [x] `MQ135_PIN=17` (verify matches your wiring)
- [x] `GPS_ENABLED=true` or `false` (based on hardware)
- [x] `FLASK_HOST=0.0.0.0` (already set)

**That's it!** Everything else is optional.

---

## 🔄 After Editing .env

1. Save the file
2. Restart the system:
   ```bash
   sudo systemctl restart air-quality.service
   ```
   Or if running manually:
   ```bash
   # Stop with Ctrl+C, then:
   python3 main.py
   ```

---

## 📍 Where is the .env file?

```
/home/pi/your-project-folder/versel/.env
```

Edit with:
```bash
nano .env
```

Save with: `Ctrl+O`, `Enter`, `Ctrl+X`
