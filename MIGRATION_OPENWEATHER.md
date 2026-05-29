# ✅ Migration vers OpenWeather API - Suppression des Capteurs Physiques

**Date:** 29 mai 2026
**Statut:** ✅ Complété et testé

## 📋 Résumé des Modifications

Le projet a été modifié pour supprimer la dépendance aux capteurs physiques Raspberry Pi et utiliser uniquement l'**API OpenWeatherMap** pour obtenir les données de qualité de l'air et météorologiques.

## 🔄 Changements Effectués

### 1. Nouveau Fichier: `openweather_data_provider.py`
- ✅ Crée une nouvelle classe `OpenWeatherDataProvider` qui récupère les données depuis OpenWeatherMap API
- ✅ Interface compatible avec l'ancienne classe `SensorManager` de `sensors.py`
- ✅ Récupère automatiquement:
  - **Qualité de l'air** (AQI, composants polluants: CO, NO₂, O₃, SO₂, PM 2.5, PM 10)
  - **Données météorologiques** (température, humidité, pression)
  - **Localisation** (latitude, longitude)
- ✅ Mode données de test si l'API n'est pas accessible

### 2. Modifications: `main.py`
- ✅ Changement d'import: `from sensors` → `from openweather_data_provider`
- ✅ Initialisation du `SensorManager` avec les paramètres OpenWeather (lat, lon, city)
- ✅ Mise à jour des commentaires et docstrings pour refléter l'utilisation de l'API
- ✅ Message de démarrage mis à jour

### 3. Modifications: `requirements.txt`
- ✅ **Supprimées** dépendances Raspberry Pi non utilisées:
  - `RPi.GPIO`
  - `adafruit-circuitpython-dht`
  - `adafruit-blinka`
  - `adafruit-circuitpython-ads1x15`
- ✅ Conservées: `requests` (pour appels API), `mistralai` (chatbot), `flask` (serveur web)
- ✅ Conservées: `scikit-learn`, `pandas`, `numpy`, `joblib` (ML)

### 4. Fichiers Non Modifiés Mais Dépréciés
- `sensors.py` - Peut être supprimé (non utilisé)
- `sensors2_new.py` - Peut être supprimé (non utilisé)
- Configuration GPIO dans `config.py` - Peut être ignorée

## 🎯 Bénéfices

| Aspect | Avant | Après |
|--------|-------|-------|
| **Dépendances système** | Complexe (GPIO, I2C, capteurs) | Simple (HTTP) |
| **Calibration matérielle** | Requise (R0, pins GPIO) | Aucune |
| **Disponibilité de l'API** | Dépend du matériel | 24/7 (OpenWeather) |
| **Données fiables** | Varie selon capteur | Validées par OpenWeather |
| **Déploiement** | Limité à Raspberry Pi | N'importe quel serveur |
| **Coût** | Matériel + développement | Gratuit (plan free) |

## ⚙️ Configuration Requise

Pour utiliser ce système, vous devez:

1. **Avoir une clé API OpenWeatherMap**:
   ```bash
   # Créez un compte gratuit sur https://openweathermap.org/
   # Obtenez une clé API (gratuit jusqu'à 1,000 requêtes/jour)
   ```

2. **Définir la variable d'environnement dans `.env`**:
   ```
   OPENWEATHER_API_KEY=your_api_key_here
   ```

3. **Définir la localisation par défaut** (optionnel):
   ```
   # Par défaut: Casablanca, MA (33.5731, -7.5898)
   # Modifiable dans .env via WEATHER_DEFAULT_QUERY
   ```

## 📊 Format des Données

Le système continue de fournir les mêmes données que l'ancien système:

```python
{
    'timestamp': '2026-05-29T12:34:56.789012',
    'air_quality': {
        'ppm': 75.0,              # Qualité de l'air en PPM approximatif
        'raw_value': 2,           # AQI brut (1-5)
        'aqi': 2,                 # Air Quality Index
        'components': {
            'co': 500,            # Monoxyde de carbone
            'no2': 100,           # Dioxyde d'azote
            'o3': 80,             # Ozone
            'so2': 50,            # Dioxyde de soufre
            'pm2_5': 15,          # Particules fines
            'pm10': 35            # Particules
        }
    },
    'temperature': 25.0,          # Température en °C
    'humidity': 60,               # Humidité en %
    'pressure': {
        'pa': 101325,             # Pression en Pascal
        'hpa': 1013.25,           # Pression en hPa
        'altitude': 0             # Altitude
    },
    'location': {
        'latitude': 33.5731,      # Latitude
        'longitude': -7.5898,     # Longitude
        'fix': True               # GPS fix disponible
    }
}
```

## ✅ Tests Effectués

- ✅ Serveur web démarre correctement
- ✅ Base de données SQLite3 fonctionne
- ✅ Modèle ML chargé
- ✅ API OpenWeather accessible
- ✅ Données récupérées et formatées correctement
- ✅ Compatibilité maintenue avec le reste du système

## 🚀 Utilisation

Démarrer le système:

```bash
# Avec le serveur web
python -m dotenv run python web_server.py

# Ou avec le système complet (main.py)
python -m dotenv run python main.py
```

Accéder à l'interface:
- Dashboard: http://localhost:5000/
- Chatbot: http://localhost:5000/chatbot
- Carte: http://localhost:5000/map
- Prédictions: http://localhost:5000/predictions

## 📝 Notes Importantes

1. **Compatibilité Totale**: L'interface du `SensorManager` est identique, donc aucun code dépendant n'a besoin de modification.

2. **Fallback Automatique**: Si l'API OpenWeather n'est pas disponible, des données de test sont générées automatiquement.

3. **Localisation**: Par défaut, la localisation est définie sur Casablanca (33.5731, -7.5898). Vous pouvez la modifier via les paramètres `lat`, `lon`, ou `city`.

4. **Mise en Cache**: Les appels API sont optimisés pour éviter de surcharger OpenWeather (cache dans `web_server.py`).

5. **Suppression de fichiers**: Vous pouvez supprimer en toute sécurité:
   - `sensors.py`
   - `sensors2_new.py`
   - Toute configuration GPIO dans `config.py` si elle n'est plus utilisée

## 🔗 Références

- [OpenWeatherMap API Documentation](https://openweathermap.org/api)
- [Air Pollution API](https://openweathermap.org/api/air-pollution)
- [Plan Gratuit](https://openweathermap.org/price)

---

**Résumé**: ✅ Migration complétée avec succès. Le système fonctionne maintenant avec OpenWeatherMap API au lieu des capteurs physiques.
