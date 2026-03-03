"""
Système d'alertes en temps réel
Surveille la qualité de l'air et envoie des alertes via MQTT, email et notifications push
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import config
# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class AlertSystem:
    """
    Système de gestion des alertes multi-canaux
    Supporte: MQTT (temps réel), Email, Logs, Notifications push
    """
    def __init__(self, db_manager=None, iot_manager=None):
        """
        Initialise le système d'alertes
        Args:
            db_manager: Instance de AirQualityDatabase
            iot_manager: Instance de IoTCloudManager
        """
        self.db = db_manager
        self.iot = iot_manager
        self.email_config = config.EMAIL_CONFIG
        self.thresholds = config.AIR_QUALITY_THRESHOLDS
        # État des alertes actives (pour éviter les répétitions)
        self.active_alerts = {}
        logger.info("✓ Système d'alertes initialisé")
    def check_air_quality(self, air_quality_value, location=None):
        """
        Vérifie la qualité de l'air et déclenche des alertes si nécessaire
        Args:
            air_quality_value (float): Valeur de qualité de l'air (PPM)
            location (dict): Localisation (latitude, longitude)
        Returns:
            list: Liste des alertes déclenchées
        """
        alerts_triggered = []
        # Déterminer le niveau de qualité
        quality_info = config.get_air_quality_level(air_quality_value)
        level = quality_info['level']
        logger.info(f"🔍 Vérification qualité: {air_quality_value:.2f} PPM - Niveau: {level}")
        # Alertes basées sur les seuils (moderate = LOW so alerts can activate earlier)
        alert_configs = [
            {
                'threshold': self.thresholds['moderate'],
                'type': 'MODERATE_AIR',
                'severity': 'LOW',
                'message': f"Qualité de l'air modérée: {air_quality_value:.1f} PPM"
            },
            {
                'threshold': self.thresholds['unhealthy'],
                'type': 'UNHEALTHY_AIR',
                'severity': 'MEDIUM',
                'message': f"⚠️ Qualité de l'air dégradée: {air_quality_value:.1f} PPM"
            },
            {
                'threshold': self.thresholds['very_unhealthy'],
                'type': 'VERY_UNHEALTHY_AIR',
                'severity': 'HIGH',
                'message': f"🚨 Qualité de l'air mauvaise: {air_quality_value:.1f} PPM"
            },
            {
                'threshold': self.thresholds['hazardous'],
                'type': 'HAZARDOUS_AIR',
                'severity': 'CRITICAL',
                'message': f"🔴 ALERTE CRITIQUE: Qualité de l'air dangereuse: {air_quality_value:.1f} PPM"
            }
        ]
        for alert_config in alert_configs:
            if air_quality_value >= alert_config['threshold']:
                # Vérifier si cette alerte n'est pas déjà active
                alert_key = f"{alert_config['type']}_{int(air_quality_value/10)}"
                if alert_key not in self.active_alerts:
                    alert = self._create_alert(
                        alert_type=alert_config['type'],
                        severity=alert_config['severity'],
                        message=alert_config['message'],
                        air_quality_value=air_quality_value,
                        location=location
                    )
                    alerts_triggered.append(alert)
                    self.active_alerts[alert_key] = datetime.now()
        return alerts_triggered
    def check_predictions(self, predictions):
        """
        Analyse les prédictions pour détecter les pics futurs
        Args:
            predictions (list): Liste des prédictions
        Returns:
            list: Alertes pour les pics prévus
        """
        alerts = []
        for pred in predictions:
            predicted_aqi = pred['predicted_aqi']
            if predicted_aqi > self.thresholds['very_unhealthy']:
                timestamp = pred['timestamp']
                alert = self._create_alert(
                    alert_type='PREDICTED_PEAK',
                    severity='HIGH' if predicted_aqi > 200 else 'MEDIUM',
                    message=f"📊 Pic de pollution prévu: {predicted_aqi:.0f} PPM à {timestamp}",
                    air_quality_value=predicted_aqi
                )
                alerts.append(alert)
        return alerts
    def _create_alert(self, alert_type, severity, message, air_quality_value=None, location=None):
        """
        Crée et distribue une alerte via tous les canaux
        Args:
            alert_type (str): Type d'alerte
            severity (str): Sévérité (LOW, MEDIUM, HIGH, CRITICAL)
            message (str): Message de l'alerte
            air_quality_value (float): Valeur qui a déclenché l'alerte
            location (dict): Localisation
        Returns:
            dict: Données de l'alerte créée
        """
        alert_data = {
            'type': alert_type,
            'severity': severity,
            'message': message,
            'air_quality_value': air_quality_value,
            'latitude': location.get('latitude') if location else None,
            'longitude': location.get('longitude') if location else None,
            'timestamp': datetime.now().isoformat()
        }
        # Log de l'alerte
        severity_emoji = {
            'LOW': 'ℹ️',
            'MEDIUM': '⚠️',
            'HIGH': '🚨',
            'CRITICAL': '🔴'
        }
        emoji = severity_emoji.get(severity, '⚠️')
        logger.warning(f"{emoji} ALERTE {severity}: {message}")
        # Enregistrer dans la base de données
        if self.db:
            self.db.insert_alert(
                alert_type=alert_type,
                severity=severity,
                message=message,
                air_quality_value=air_quality_value,
                lat=location.get('latitude') if location else None,
                lon=location.get('longitude') if location else None
            )
        # Publier via IoT Cloud (MQTT)
        if self.iot and self.iot.is_connected():
            self.iot.publish_alert(alert_data)
        # Envoyer email pour alertes critiques
        if severity in ['HIGH', 'CRITICAL'] and self.email_config['enabled']:
            self._send_email_alert(alert_data)
        return alert_data
    def _send_email_alert(self, alert_data):
        """
        Envoie une alerte par email
        Args:
            alert_data (dict): Données de l'alerte
        """
        try:
            # Créer le message email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"⚠️ Alerte Qualité de l'Air - {alert_data['severity']}"
            msg['From'] = self.email_config['username']
            msg['To'] = self.email_config['alert_email']
            # Corps du message HTML
            html_body = f"""
            <html>
              <head></head>
              <body style="font-family: Arial, sans-serif;">
                <div style="background-color: #f44336; color: white; padding: 20px; border-radius: 5px;">
                  <h2>🚨 Alerte Qualité de l'Air</h2>
                </div>
                <div style="padding: 20px; background-color: #f9f9f9; margin-top: 10px;">
                  <p><strong>Type:</strong> {alert_data['type']}</p>
                  <p><strong>Sévérité:</strong> {alert_data['severity']}</p>
                  <p><strong>Message:</strong> {alert_data['message']}</p>
                  {f"<p><strong>Valeur AQI:</strong> {alert_data['air_quality_value']:.1f} PPM</p>"
                   if alert_data['air_quality_value'] else ""}
                  {f"<p><strong>Localisation:</strong> {alert_data['latitude']:.4f}, {alert_data['longitude']:.4f}</p>"
                   if alert_data.get('latitude') else ""}
                  <p><strong>Heure:</strong> {alert_data['timestamp']}</p>
                </div>
                <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 4px solid #ffc107;">
                  <h3>Recommandations:</h3>
                  <ul>
                    <li>Restez à l'intérieur si possible</li>
                    <li>Évitez les activités physiques intenses</li>
                    <li>Fermez les fenêtres</li>
                    <li>Utilisez un purificateur d'air</li>
                    <li>Les personnes sensibles doivent consulter un médecin en cas de symptômes</li>
                  </ul>
                </div>
                <div style="margin-top: 20px; color: #666; font-size: 12px;">
                  <p>Cet email a été envoyé automatiquement par le système de surveillance de qualité de l'air.</p>
                </div>
              </body>
            </html>
            """
            # Attacher le corps HTML
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
            # Envoyer l'email
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['username'], self.email_config['password'])
                server.send_message(msg)
            logger.info(f"✓ Email d'alerte envoyé à {self.email_config['alert_email']}")
        except Exception as e:
            logger.error(f"✗ Erreur envoi email: {e}")
    def send_daily_summary(self, statistics):
        """
        Envoie un résumé quotidien par email
        Args:
            statistics (dict): Statistiques de la journée
        """
        if not self.email_config['enabled']:
            return
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📊 Résumé Qualité de l'Air - {datetime.now().strftime('%d/%m/%Y')}"
            msg['From'] = self.email_config['username']
            msg['To'] = self.email_config['alert_email']
            # Déterminer la qualité moyenne
            avg_aqi = statistics.get('avg_aqi', 0)
            quality_info = config.get_air_quality_level(avg_aqi)
            html_body = f"""
            <html>
              <body style="font-family: Arial, sans-serif;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px;">
                  <h2>📊 Résumé Quotidien - Qualité de l'Air</h2>
                  <p>{datetime.now().strftime('%d %B %Y')}</p>
                </div>
                <div style="padding: 20px; background-color: #f9f9f9; margin-top: 10px;">
                  <h3>Statistiques des dernières 24 heures:</h3>
                  <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background-color: {quality_info['color']}; color: white;">
                      <td style="padding: 10px; border: 1px solid #ddd;">Qualité Moyenne</td>
                      <td style="padding: 10px; border: 1px solid #ddd;"><strong>{avg_aqi:.1f} PPM</strong></td>
                    </tr>
                    <tr>
                      <td style="padding: 10px; border: 1px solid #ddd;">Niveau</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{quality_info['level']}</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                      <td style="padding: 10px; border: 1px solid #ddd;">Minimum</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{statistics.get('min_aqi', 0):.1f} PPM</td>
                    </tr>
                    <tr>
                      <td style="padding: 10px; border: 1px solid #ddd;">Maximum</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{statistics.get('max_aqi', 0):.1f} PPM</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                      <td style="padding: 10px; border: 1px solid #ddd;">Température Moyenne</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{statistics.get('avg_temp', 0):.1f}°C</td>
                    </tr>
                    <tr>
                      <td style="padding: 10px; border: 1px solid #ddd;">Humidité Moyenne</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{statistics.get('avg_humidity', 0):.1f}%</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                      <td style="padding: 10px; border: 1px solid #ddd;">Nombre de Mesures</td>
                      <td style="padding: 10px; border: 1px solid #ddd;">{statistics.get('total_readings', 0)}</td>
                    </tr>
                  </table>
                </div>
                <div style="margin-top: 20px; padding: 15px; background-color: #e8f5e9; border-left: 4px solid #4caf50;">
                  <p><em>{quality_info['description']}</em></p>
                </div>
              </body>
            </html>
            """
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['username'], self.email_config['password'])
                server.send_message(msg)
            logger.info("✓ Résumé quotidien envoyé par email")
        except Exception as e:
            logger.error(f"✗ Erreur envoi résumé: {e}")
    def clear_old_alerts(self, hours=24):
        """
        Nettoie les alertes actives anciennes
        Args:
            hours (int): Nombre d'heures après lesquelles une alerte est considérée ancienne
        """
        current_time = datetime.now()
        to_remove = []
        for alert_key, alert_time in self.active_alerts.items():
            if (current_time - alert_time).total_seconds() > hours * 3600:
                to_remove.append(alert_key)
        for key in to_remove:
            del self.active_alerts[key]
        if to_remove:
            logger.info(f"🧹 {len(to_remove)} alertes anciennes nettoyées")
# Test du module si exécuté directement
if __name__ == "__main__":
    print("=== Test du système d'alertes ===\n")
    # Créer le système d'alertes
    alert_system = AlertSystem()
    # Tester différents niveaux de qualité
    test_values = [75, 120, 180, 250]
    for value in test_values:
        print(f"\nTest avec valeur: {value} PPM")
        alerts = alert_system.check_air_quality(
            air_quality_value=value,
            location={'latitude': 36.8065, 'longitude': 10.1815}
        )
        if alerts:
            print(f"  → {len(alerts)} alerte(s) déclenchée(s)")
    print("\n✓ Test terminé")