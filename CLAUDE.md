# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🛠️ Development Commands

### Environment Setup
1. Clone the repository (if not already done)
2. Navigate to the project root:
   ```bash
   cd /path/to/versel
   ```
3. Create and activate a Python virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Linux/macOS/Raspberry Pi
   .\venv\Scripts\activate    # Windows
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the System
- **Full System (Sensors + Database + ML + Web Interface)**:
  ```bash
  python3 main.py
  ```
  This starts the main orchestrator which reads sensors, stores data, runs ML predictions, triggers alerts, and serves the web interface.

- **Web Interface Only** (useful for testing/development without hardware):
  ```bash
  python3 web_server.py
  ```
  Serves the Flask-based SSR web interface at http://localhost:5000.

- **Background/Production Mode**:
  ```bash
  nohup python3 main.py > output.log 2>&1 &
  ```
  Checks status with `ps aux | grep main.py`; view logs with `tail -f air_quality_system.log`; stop with `pkill -f main.py`.

- **Train/Retrain ML Model**:
  ```bash
  python3 ml_model.py
  ```
  Trains the model using synthetic data (or loads existing data) and saves the model to `./models/air_quality_model.pkl`.

### Utility Scripts
- `quickstart.sh` – Interactive script that sets up the environment, initializes the database, trains the ML model, and starts the system in your chosen mode.
- `setup.sh` – Non-interactive setup that creates directories, virtual environment, installs dependencies, initializes the database, and trains the ML model.

### Configuration
- Edit `.env` file to set API keys and other parameters:
  - `OPENWEATHER_API_KEY` – Required for weather features (free tier available at https://openweathermap.org/api)
  - `HF_API_KEY` – Optional, for the Hugging Face-powered environmental assistant
  - `SMTP_USERNAME` / `SMTP_PASSWORD` – Optional, for email alerts
  - Sensor GPIO pins, read intervals, default location, etc.
- See `config.py` for all configurable options and their defaults.

### Code Quality & Testing
- The project does not currently include automated unit tests or linting tools.
- Verify changes by running the system manually and checking logs (`air_quality_system.log`).
- For web interface changes, refresh the browser and inspect the rendered HTML (no JavaScript is used).

## 🏗️ High-Level Architecture

The AirWatch system follows a **server‑side rendered (SSR)**, **zero‑JavaScript** architecture designed for stability and low resource consumption on devices like the Raspberry Pi 4.

### Core Components
1. **`main.py`** – Main orchestrator:
   - Initializes all subsystems (database, sensors, ML model, alert system, optional web server).
   - Schedules periodic tasks using the `schedule` library:
     - Sensor reads (configurable interval, default 60 s)
     - ML predictions (hourly)
     - Alert cleanup (every 6 h)
     - Daily summary email (08:00)
   - Runs a blocking loop that executes pending scheduled tasks.
   - Handles graceful shutdown on SIGINT (Ctrl+C).

2. **`web_server.py`** – Flask web application:
   - Provides SSR HTML pages (dashboard, map, news, predictions, analytics, chat).
   - Exposes a lightweight REST API (`/api/*`) used by the server‑side templates to fetch data.
   - Integrates with:
     - OpenWeatherMap API (current weather & 5‑day forecast)
     - NASA EONET API (environmental events such as fires, dust storms)
     - NewsData.io / RSS feeds (environmental news)
     - Hugging Face Inference API (fallback to Groq/OpenAI/Ollama) for the environmental assistant chat.
   - Uses Jinja2 templates located in `templates/`; static CSS in `static/css/`.
   - Theme (dark/light) is stored in Flask session and toggled via `/toggle-theme`.

3. **`database.py`** – SQLite3 wrapper:
   - Manages connection to `./data/air_quality.db`.
   - Creates tables for sensor readings, predictions, alerts, etc.
   - Provides CRUD‑style methods used by `main.py` and `web_server.py`.

4. **`sensors2.py`** – Hardware abstraction layer:
   - Reads from MQ‑135 (air quality), DHT11 (temperature/humidity), and optional GPS module.
   - Returns a dictionary with processed values.
   - Includes cleanup() to release GPIO pins.

5. **`ml_model.py`** – Machine learning model:
   - Uses a RandomForestRegressor (scikit‑learn) to predict AQI (PPM) for the next 24 hours.
   - Includes functions to load/save the model (`joblib`), generate synthetic training data, train, predict, and detect pollution peaks.
   - Model and scaler are stored in `./models/`.

6. **`alert_system.py`** – Alerting logic:
   - Checks sensor readings and ML predictions against configurable thresholds.
   - Stores alerts in the database; can send emails via SMTP.
   - Provides methods to retrieve active alerts and send daily summaries.

7. **`config.py`** – Central configuration:
   - Loads environment variables from `.env` via `python‑dotenv`.
   - Provides structured dictionaries for DB, sensors, Flask, email, ML, NASA, Hugging Face, OpenAI, Groq.
   - Includes `get_air_quality_level(value)` to map raw PPM to AQI level, color, and description.

### Data Flow
- **Sensor → Database**: `main.py` reads sensors via `SensorManager`, inserts rows into `sensor_data` table.
- **Database → Web**: Flask routes query the latest readings, statistics, predictions, alerts, etc., and inject them into Jinja2 templates.
- **ML Prediction**: `main.py` calls `AirQualityPredictor.predict()` on the latest sensor reading; predictions are stored in the `predictions` table.
- **Alerts**: `AlertSystem` checks thresholds and inserts rows into the `alerts` table; web interface shows active alerts.
- **Assistant Chat**: User submits a message via `/chat` (POST); backend augments the message with current sensor/weather context and queries the Hugging Face router (with fallbacks) to generate a reply.

### Deployment Notes
- The system is intended to run 24/7 on a Raspberry Pi 4 (or similar SBC).
- Sensor reading interval can be increased to reduce CPU/power usage.
- The web interface is lightweight (< 50 KB HTML + CSS) and works without JavaScript, ensuring compatibility with old browsers and reducing attack surface.
- All API keys should be kept in `.env` (which is excluded from version control by `.gitignore`).

## 📂 Directory Overview (Key Files)
```
versel/
├── main.py                 # System orchestrator
├── web_server.py           # Flask SSR web server + API
├── database.py             # SQLite3 wrapper
├── sensors2.py             # Sensor drivers (MQ‑135, DHT11, GPS)
├── ml_model.py             # ML model training & prediction
├── alert_system.py         # Alert logic & notifications
├── config.py               # Central configuration (.env loader)
├── requirements.txt        # Python dependencies
├── quickstart.sh           # Interactive setup & launcher
├── setup.sh                # Automated setup script
├── .env.example            # Template for environment variables
├── README.md               # Project overview & features
├── templates/              # Jinja2 HTML pages (dashboard, map, …)
├── static/css/             # CSS (responsive, dark/light themes)
├── models/                 # Trained ML model & scaler (generated)
├── data/                   # SQLite database file
└── logs/                   # Runtime logs (air_quality_system.log)
```

## 📝 Notes for Future Claude Code Sessions
- When starting work, first check if a virtual environment is active; if not, activate it.
- To experiment with changes to the web UI, edit the relevant Jinja2 template in `templates/` and refresh the page.
- To modify sensor reading frequency, adjust `SENSOR_CONFIG['read_interval']` in `.env` or `config.py`.
- To add a new API endpoint, add a function in `web_server.py` decorated with `@app.route` and update the corresponding template if needed.
- Remember that the system is deliberately **zero‑JS**; avoid adding `<script>` tags or inline JavaScript to templates.
