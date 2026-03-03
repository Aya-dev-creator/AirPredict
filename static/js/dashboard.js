// Dashboard JavaScript - Air Quality Monitor
// Handles data fetching, real-time updates, and chart rendering

// Global variables
let aqiGaugeChart = null;
let socket = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Dashboard initializing...');
    
    // Initialize WebSocket connection
    initializeWebSocket();
    
    // Fetch initial data
    fetchCurrentData();
    fetchWeatherData();
    fetchForecast();
    fetchStatistics();
    fetchAlerts();
    
    setInterval(() => {
        fetchCurrentData();
        fetchWeatherData();
    }, 60000);
    
    setupThemeToggle();
    setupNotifications();
    setupProfilePanel();
    
    // Update current date
    updateCurrentDate();
    setInterval(updateCurrentDate, 60000);
});

// WebSocket Connection
function initializeWebSocket() {
    try {
        socket = io();
        
        socket.on('connect', () => {
            console.log('✓ WebSocket connected');
        });
        
        socket.on('sensor_update', (data) => {
            console.log('📊 Real-time sensor update', data);
            updateDashboardWithSensorData(data);
        });
        
        socket.on('alert', (alert) => {
            console.log('🔔 New alert', alert);
            showNotification(alert);
            fetchAlerts(); // Refresh alerts list
        });
        
        socket.on('disconnect', () => {
            console.log('⚠ WebSocket disconnected');
        });
    } catch (error) {
        console.error('WebSocket error:', error);
    }
}

// Fetch current sensor data
async function fetchCurrentData() {
    try {
        const response = await fetch('/api/current');
        const data = await response.json();
        
        if (data.success) {
            updateAQIDisplay(data.air_quality);
            updateMetrics(data);
            updateWeatherFromSensor(data);
            if (data.weather) updateWeatherDisplay(data.weather);
        } else {
            showNoSensorData();
            var t = (data.temperature != null) ? data.temperature : '--';
            var h = (data.humidity != null) ? data.humidity : '--';
            updateWeatherFromSensor({ temperature: t, humidity: h });
            if (data.weather) updateWeatherDisplay(data.weather);
        }
    } catch (error) {
        console.error('Error fetching current data:', error);
        showNoSensorData();
        updateWeatherFromSensor({ temperature: '--', humidity: '--' });
    }
}

// Always set main weather card temperature & humidity from sensor (or fallback)
function updateWeatherFromSensor(data) {
    const loc = document.getElementById('locationName');
    const temp = document.getElementById('temperature');
    const hum = document.getElementById('humidity');
    const desc = document.getElementById('weatherDesc');
    var t = data.temperature;
    var h = data.humidity;
    if (loc && (t == null || t === '--') && (h == null || h === '--')) loc.textContent = 'Casablanca';
    if (temp) temp.textContent = (t != null && t !== '--') ? t : '--';
    if (hum) hum.textContent = (h != null && h !== '--') ? (typeof h === 'number' ? h + '%' : h) : '--%';
    if (desc && (t != null && t !== '--')) desc.textContent = 'Depuis le capteur';
}

// Show "no sensor data" state in UI
function showNoSensorData() {
    const aqiValue = document.getElementById('aqiValue');
    const aqiLabel = document.getElementById('aqiLabel');
    const aqiDescription = document.getElementById('aqiDescription');
    if (aqiValue) aqiValue.textContent = '--';
    if (aqiLabel) aqiLabel.textContent = 'Aucune donnée';
    if (aqiDescription) aqiDescription.textContent = 'En attente des données des capteurs. Vérifiez le Raspberry Pi et les capteurs.';
    if (!aqiGaugeChart) {
        createAQIGauge(0, 'rgba(100, 116, 139, 0.5)');
    } else {
        updateAQIGauge(0, 'rgba(100, 116, 139, 0.5)');
    }
}

// Fetch weather data
async function fetchWeatherData() {
    try {
        const response = await fetch('/api/weather');
        const data = await response.json();
        
        if (data.success && data.weather) {
            updateWeatherDisplay(data.weather);
        }
    } catch (error) {
        console.error('Error fetching weather:', error);
    }
}

// Fetch weather forecast
async function fetchForecast() {
    try {
        const response = await fetch('/api/forecast?days=5');
        const data = await response.json();
        
        if (data.success && data.forecasts) {
            updateForecastDisplay(data.forecasts);
        }
    } catch (error) {
        console.error('Error fetching forecast:', error);
    }
}

// Fetch statistics
async function fetchStatistics() {
    try {
        const response = await fetch('/api/statistics?hours=24');
        const data = await response.json();
        
        if (data.success) {
            updateStatistics(data.statistics);
        }
    } catch (error) {
        console.error('Error fetching statistics:', error);
    }
}

// Fetch active alerts
async function fetchAlerts() {
    try {
        const response = await fetch('/api/alerts');
        const data = await response.json();
        
        if (data.success) {
            updateAlertsDisplay(data.alerts);
        }
    } catch (error) {
        console.error('Error fetching alerts:', error);
    }
}

// Update AQI display
function updateAQIDisplay(airQuality) {
    if (!airQuality) return;
    
    const aqiValue = document.getElementById('aqiValue');
    const aqiLabel = document.getElementById('aqiLabel');
    const aqiDescription = document.getElementById('aqiDescription');
    
    if (aqiValue) aqiValue.textContent = Math.round(airQuality.value);
    if (aqiLabel) aqiLabel.textContent = airQuality.level;
    if (aqiDescription) aqiDescription.textContent = airQuality.description;
    
    // Update gauge chart
    if (!aqiGaugeChart) {
        createAQIGauge(airQuality.value, airQuality.color);
    } else {
        updateAQIGauge(airQuality.value, airQuality.color);
    }
}

// Create AQI Gauge Chart
function createAQIGauge(value, color) {
    const ctx = document.getElementById('aqiGauge');
    if (!ctx) return;
    
    aqiGaugeChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [value, 300 - value],
                backgroundColor: [color, 'rgba(100, 116, 139, 0.2)'],
                borderWidth: 0
            }]
        },
        options: {
            cutout: '80%',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        }
    });
}

// Update AQI Gauge
function updateAQIGauge(value, color) {
    if (!aqiGaugeChart) return;
    
    aqiGaugeChart.data.datasets[0].data = [value, 300 - value];
    aqiGaugeChart.data.datasets[0].backgroundColor = [color, 'rgba(100, 116, 139, 0.2)'];
    aqiGaugeChart.update();
}

// Update weather display
function updateWeatherDisplay(weather) {
    const elements = {
        locationName: document.getElementById('locationName'),
        temperature: document.getElementById('temperature'),
        weatherDesc: document.getElementById('weatherDesc'),
        weatherIcon: document.getElementById('weatherIcon'),
        windSpeed: document.getElementById('windSpeed'),
        humidity: document.getElementById('humidity'),
        sunrise: document.getElementById('sunrise'),
        sunset: document.getElementById('sunset'),
        metricPressure: document.getElementById('metricPressure'),
        metricVisibility: document.getElementById('metricVisibility')
    };
    
    if (elements.locationName) elements.locationName.textContent = `${weather.city}, ${weather.country}`;
    if (elements.weatherDesc) elements.weatherDesc.textContent = weather.description;
    if (elements.weatherIcon) elements.weatherIcon.src = `https://openweathermap.org/img/wn/${weather.icon}@2x.png`;
    if (elements.windSpeed) elements.windSpeed.textContent = `${weather.wind_speed} km/h`;
    if (elements.sunrise) elements.sunrise.textContent = weather.sunrise;
    if (elements.sunset) elements.sunset.textContent = weather.sunset;
    if (elements.metricPressure) elements.metricPressure.textContent = `${weather.pressure} hPa`;
    if (elements.metricVisibility) elements.metricVisibility.textContent = `${weather.visibility} km`;
}

// Update metrics
function updateMetrics(data) {
    const metricTemp = document.getElementById('metricTemp');
    const metricHumidity = document.getElementById('metricHumidity');
    
    if (metricTemp && data.temperature) {
        metricTemp.textContent = `${data.temperature}°C`;
    }
    if (metricHumidity && data.humidity) {
        metricHumidity.textContent = `${data.humidity}%`;
    }
}

// Update forecast display
function updateForecastDisplay(forecasts) {
    const forecastList = document.getElementById('forecastList');
    if (!forecastList) return;
    
    forecastList.innerHTML = forecasts.map(forecast => `
        <div class="forecast-item">
            <div class="forecast-date">
                <img src="https://openweathermap.org/img/wn/${forecast.icon}.png" alt="" class="forecast-icon">
                <div>
                    <div class="forecast-day">${forecast.day_name}</div>
                    <div class="forecast-desc">${forecast.description}</div>
                </div>
            </div>
            <div class="forecast-temp">
                <div class="temp-high">${forecast.temp_max}°</div>
                <div class="temp-low">${forecast.temp_min}°</div>
            </div>
        </div>
    `).join('');
}

// Update statistics
function updateStatistics(stats) {
    const avgAqi = document.getElementById('avgAqi');
    const minAqi = document.getElementById('minAqi');
    const maxAqi = document.getElementById('maxAqi');
    const totalReadings = document.getElementById('totalReadings');
    
    if (avgAqi && stats.air_quality) avgAqi.textContent = stats.air_quality.average.toFixed(1);
    if (minAqi && stats.air_quality) minAqi.textContent = stats.air_quality.min.toFixed(1);
    if (maxAqi && stats.air_quality) maxAqi.textContent = stats.air_quality.max.toFixed(1);
    if (totalReadings) totalReadings.textContent = stats.total_readings;
}

// Update alerts display
function updateAlertsDisplay(alerts) {
    const alertsList = document.getElementById('alertsList');
    const notifBadge = document.getElementById('notifBadge');
    if (notifBadge) {
        notifBadge.textContent = alerts.length;
        notifBadge.style.display = alerts.length > 0 ? 'flex' : 'none';
    }
    if (!alertsList) return;
    
    if (!alerts || alerts.length === 0) {
        alertsList.innerHTML = `
            <div class="empty-state">
                <span class="empty-icon">✓</span>
                <p>Aucune alerte active</p>
                <p class="metric-label" style="margin-top: var(--spacing-sm);">Les alertes apparaîtront lorsque la qualité de l'air dépassera les seuils définis.</p>
            </div>
        `;
        return;
    }
    
    alertsList.innerHTML = alerts.map(alert => {
        const severityClass = (alert.severity || '').toLowerCase();
        const severityIcon = getSeverityIcon(alert.severity);
        const timeAgo = getTimeAgo(new Date(alert.created_at || Date.now()));
        return `
            <div class="alert-item ${severityClass}">
                <span class="alert-icon">${severityIcon}</span>
                <div class="alert-content">
                    <div class="alert-header">
                        <span class="alert-title">${(alert.type || '').replace(/_/g, ' ')}</span>
                        <span class="alert-time">${timeAgo}</span>
                    </div>
                    <p class="alert-message">${alert.message || ''}</p>
                </div>
            </div>
        `;
    }).join('');
}

// Helper: Get severity icon
function getSeverityIcon(severity) {
    const icons = {
        'CRITICAL': '🔴',
        'HIGH': '🚨',
        'MEDIUM': '⚠️',
        'LOW': 'ℹ️'
    };
    return icons[severity] || '📢';
}

// Helper: Get time ago
function getTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    
    if (seconds < 60) return 'À l’instant';
    if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)} min`;
    if (seconds < 86400) return `il y a ${Math.floor(seconds / 3600)} h`;
    return `il y a ${Math.floor(seconds / 86400)} j`;
}

// Setup theme toggle: checked = dark, unchecked = light
function setupThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    const themeLabel = document.getElementById('themeLabel');
    const themeIcon = document.getElementById('themeIcon');
    
    if (themeToggle) {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.body.setAttribute('data-theme', savedTheme);
        themeToggle.checked = (savedTheme === 'dark');
        if (themeLabel) themeLabel.textContent = savedTheme === 'dark' ? 'Mode clair' : 'Mode sombre';
        if (themeIcon) themeIcon.textContent = savedTheme === 'dark' ? '🌙' : '☀️';
        
        themeToggle.addEventListener('change', () => {
            const theme = themeToggle.checked ? 'dark' : 'light';
            document.body.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            if (themeLabel) themeLabel.textContent = theme === 'dark' ? 'Mode clair' : 'Mode sombre';
            if (themeIcon) themeIcon.textContent = theme === 'dark' ? '🌙' : '☀️';
        });
    }
}

// Profile panel: email + alerts activation
function setupProfilePanel() {
    const btn = document.getElementById('profileBtn');
    const panel = document.getElementById('profilePanel');
    const emailInput = document.getElementById('profileEmail');
    const alertsCheck = document.getElementById('alertsEnabled');
    const saveBtn = document.getElementById('profileSave');
    if (!panel) return;
    if (emailInput) emailInput.value = localStorage.getItem('alertEmail') || localStorage.getItem('userEmail') || '';
    if (alertsCheck) alertsCheck.checked = localStorage.getItem('alertsEnabled') !== 'false';
    if (btn) btn.addEventListener('click', (e) => { e.stopPropagation(); panel.classList.toggle('show'); });
    document.addEventListener('click', () => panel.classList.remove('show'));
    panel.addEventListener('click', (e) => e.stopPropagation());
    if (saveBtn) saveBtn.addEventListener('click', () => {
        if (emailInput) localStorage.setItem('alertEmail', emailInput.value);
        if (alertsCheck) localStorage.setItem('alertsEnabled', alertsCheck.checked ? 'true' : 'false');
        panel.classList.remove('show');
    });
}

// Notifications panel: toggle and fill from alerts API
function setupNotifications() {
    const notifBtn = document.getElementById('notifBtn');
    const panel = document.getElementById('notificationsPanel');
    if (!notifBtn || !panel) return;
    notifBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        panel.classList.toggle('show');
        if (panel.classList.contains('show')) updateNotificationsList();
    });
    document.addEventListener('click', () => panel.classList.remove('show'));
    panel.addEventListener('click', (e) => e.stopPropagation());
}

async function updateNotificationsList() {
    const list = document.getElementById('notificationsList');
    if (!list) return;
    try {
        const res = await fetch('/api/alerts');
        const data = await res.json();
        if (data.success && data.alerts && data.alerts.length > 0) {
            list.innerHTML = data.alerts.slice(0, 10).map(a => 
                '<div class="notif-item">' + (a.severity || '') + ' ' + (a.message || '') + '</div>'
            ).join('');
        } else {
            list.innerHTML = 'Aucune alerte active';
        }
    } catch (e) {
        list.innerHTML = 'Impossible de charger les notifications';
    }
}

// Update current date
function updateCurrentDate() {
    const dateElement = document.getElementById('currentDate');
    if (!dateElement) return;
    
    const now = new Date();
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateElement.textContent = now.toLocaleDateString('fr-FR', options);
}

// Show notification
function showNotification(alert) {
    // Check if browser supports notifications
    if (!("Notification" in window)) return;
    
    // Request permission if needed
    if (Notification.permission === "granted") {
        new Notification("Alerte qualité de l'air", {
            body: alert.message,
            icon: "/static/images/logo.png",
            badge: "/static/images/badge.png"
        });
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(permission => {
            if (permission === "granted") {
                new Notification("Alerte qualité de l'air", {
                    body: alert.message
                });
            }
        });
    }
}

// Update dashboard with real-time sensor data
function updateDashboardWithSensorData(data) {
    if (data.air_quality) {
        updateAQIDisplay(data.air_quality);
    }
    updateMetrics(data);
}

// Export functions for testing (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        fetchCurrentData,
        updateAQIDisplay,
        updateWeatherDisplay
    };
}

console.log('✓ Dashboard script loaded');
