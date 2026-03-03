"""
Module de Machine Learning pour la prédiction de la qualité de l'air
Utilise Random Forest et LSTM pour prédire les pics de pollution
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
import joblib
import os
# Machine Learning
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class AirQualityPredictor:
    """
    Classe pour créer et utiliser des modèles de prédiction de qualité de l'air
    """
    def __init__(self, model_path='./models/air_quality_model.pkl'):
        """
        Initialise le prédicteur
         Args:
            model_path (str): Chemin pour sauvegarder/charger le modèle
        """
        self.model_path = model_path
        self.scaler_path = model_path.replace('.pkl', '_scaler.pkl')
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = [
            'hour', 'day_of_week', 'month',
            'temperature', 'humidity',
            'air_quality_lag_1', 'air_quality_lag_2', 'air_quality_lag_3',
            'air_quality_rolling_mean_3', 'air_quality_rolling_mean_6',
            'air_quality_rolling_std_3'
        ]
        # Créer le dossier models s'il n'existe pas
        os.makedirs('./models', exist_ok=True)
        os.makedirs('./data', exist_ok=True)
        logger.info("✓ Prédicteur de qualité de l'air initialisé")
    def create_features(self, df):
        """
        Crée les features pour le modèle ML à partir des données brutes
        Args:
            df (DataFrame): DataFrame avec colonnes timestamp, air_quality_ppm, temperature, humidity
        Returns:
            DataFrame: DataFrame avec features engineered
        """
        logger.info("🔧 Création des features...")
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        # Features temporelles
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['month'] = df['timestamp'].dt.month
        # Features de lag (valeurs précédentes)
        df['air_quality_lag_1'] = df['air_quality_ppm'].shift(1)
        df['air_quality_lag_2'] = df['air_quality_ppm'].shift(2)
        df['air_quality_lag_3'] = df['air_quality_ppm'].shift(3)
        # Features de rolling statistics
        df['air_quality_rolling_mean_3'] = df['air_quality_ppm'].rolling(window=3).mean()
        df['air_quality_rolling_mean_6'] = df['air_quality_ppm'].rolling(window=6).mean()
        df['air_quality_rolling_std_3'] = df['air_quality_ppm'].rolling(window=3).std()
        # Supprimer les lignes avec des NaN créées par les opérations de lag/rolling
        df = df.dropna()
        logger.info(f"✓ {len(df)} échantillons avec features créés")
        return df
    def train_model(self, data, test_size=0.2):
        """
        Entraîne le modèle de prédiction
        Args:
            data (DataFrame): Données d'entraînement avec colonnes requises
            test_size (float): Proportion des données pour le test
        Returns:
            dict: Métriques de performance du modèle
        """
        logger.info("🎓 Début de l'entraînement du modèle...")
        # Créer les features
        df = self.create_features(data)
        # Préparer X et y
        X = df[self.feature_names]
        y = df['air_quality_ppm']
        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, shuffle=False
        )
        logger.info(f"📊 Données d'entraînement: {len(X_train)} échantillons")
        logger.info(f"📊 Données de test: {len(X_test)} échantillons")
        # Normaliser les features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        # Entraîner le modèle Random Forest
        logger.info("🌳 Entraînement Random Forest...")
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X_train_scaled, y_train)
        # Prédictions
        y_pred_train = self.model.predict(X_train_scaled)
        y_pred_test = self.model.predict(X_test_scaled)
        # Calculer les métriques
        metrics = {
            'train': {
                'rmse': np.sqrt(mean_squared_error(y_train, y_pred_train)),
                'mae': mean_absolute_error(y_train, y_pred_train),
                'r2': r2_score(y_train, y_pred_train)
            },
            'test': {
                'rmse': np.sqrt(mean_squared_error(y_test, y_pred_test)),
                'mae': mean_absolute_error(y_test, y_pred_test),
                'r2': r2_score(y_test, y_pred_test)
            }
        }
        # Afficher les résultats
        logger.info("\n" + "="*50)
        logger.info("📈 RÉSULTATS DE L'ENTRAÎNEMENT")
        logger.info("="*50)
        logger.info(f"Train RMSE: {metrics['train']['rmse']:.2f}")
        logger.info(f"Train MAE:  {metrics['train']['mae']:.2f}")
        logger.info(f"Train R²:   {metrics['train']['r2']:.3f}")
        logger.info("-"*50)
        logger.info(f"Test RMSE:  {metrics['test']['rmse']:.2f}")
        logger.info(f"Test MAE:   {metrics['test']['mae']:.2f}")
        logger.info(f"Test R²:    {metrics['test']['r2']:.3f}")
        logger.info("="*50 + "\n")
        # Importance des features
        feature_importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        logger.info("🔍 Importance des features:")
        for idx, row in feature_importance.head(5).iterrows():
            logger.info(f"  {row['feature']}: {row['importance']:.3f}")
        # Sauvegarder le modèle
        self.save_model()
        return metrics
    def predict(self, current_data, hours_ahead=24):
        """
        Fait des prédictions pour les prochaines heures
        Args:
            current_data (dict): Données actuelles des capteurs
            hours_ahead (int): Nombre d'heures à prédire
        Returns:
            list: Liste de prédictions avec timestamps
        """
        if self.model is None:
            logger.error("✗ Modèle non chargé. Chargez ou entraînez d'abord le modèle.")
            return []
        logger.info(f"🔮 Prédiction pour les {hours_ahead} prochaines heures...")
        predictions = []
        current_time = datetime.now()
        # Préparer les features de base
        for hour in range(hours_ahead):
            pred_time = current_time + timedelta(hours=hour)
            # Créer les features pour cette heure
            features = {
                'hour': pred_time.hour,
                'day_of_week': pred_time.weekday(),
                'month': pred_time.month,
                'temperature': current_data.get('temperature', 25),
                'humidity': current_data.get('humidity', 50),
                'air_quality_lag_1': current_data.get('air_quality_ppm', 100),
                'air_quality_lag_2': current_data.get('air_quality_ppm', 100),
                'air_quality_lag_3': current_data.get('air_quality_ppm', 100),
                'air_quality_rolling_mean_3': current_data.get('air_quality_ppm', 100),
                'air_quality_rolling_mean_6': current_data.get('air_quality_ppm', 100),
                'air_quality_rolling_std_3': 10
            }
            # Préparer l'input pour le modèle
            X = np.array([[features[f] for f in self.feature_names]])
            X_scaled = self.scaler.transform(X)
            # Faire la prédiction
            predicted_aqi = self.model.predict(X_scaled)[0]
            predictions.append({
                'timestamp': pred_time.isoformat(),
                'predicted_aqi': max(0, round(predicted_aqi, 2)),
                'hour': pred_time.hour,
                'confidence': 0.85  # Score de confiance simulé
            })
        logger.info(f"✓ {len(predictions)} prédictions générées")
        return predictions
    def detect_pollution_peak(self, predictions, threshold=150):
        """
        Détecte les pics de pollution prévus
        Args:
            predictions (list): Liste des prédictions
            threshold (float): Seuil de pollution critique (PPM)
        Returns:
            list: Liste des alertes de pics de pollution
        """
        alerts = []
        for pred in predictions:
            if pred['predicted_aqi'] > threshold:
                alerts.append({
                    'timestamp': pred['timestamp'],
                    'predicted_aqi': pred['predicted_aqi'],
                    'severity': 'HIGH' if pred['predicted_aqi'] > 200 else 'MEDIUM',
                    'message': f"Pic de pollution prévu: {pred['predicted_aqi']:.0f} PPM"
                })
        if alerts:
            logger.warning(f"⚠️ {len(alerts)} pic(s) de pollution détecté(s)")
        else:
            logger.info("✓ Aucun pic de pollution prévu")
        return alerts
    def generate_recommendations(self, current_aqi, predicted_peaks):
        """
        Génère des recommandations personnalisées basées sur les prédictions
        Args:
            current_aqi (float): Qualité de l'air actuelle
            predicted_peaks (list): Liste des pics prévus
        Returns:
            dict: Recommandations personnalisées
        """
        recommendations = {
            'current_status': '',
            'actions': [],
            'health_advice': [],
            'time_periods_to_avoid': []
        }
        # Statut actuel
        if current_aqi <= 50:
            recommendations['current_status'] = "Qualité de l'air excellente"
            recommendations['actions'].append("Profitez des activités en plein air")
        elif current_aqi <= 100:
            recommendations['current_status'] = "Qualité de l'air acceptable"
            recommendations['actions'].append("Les activités en plein air sont généralement sûres")
        elif current_aqi <= 150:
            recommendations['current_status'] = "Qualité de l'air modérée"
            recommendations['actions'].append("Limitez les activités extérieures prolongées")
            recommendations['health_advice'].append("Les personnes sensibles doivent être prudentes")
        else:
            recommendations['current_status'] = "Qualité de l'air mauvaise"
            recommendations['actions'].append("Évitez les activités extérieures intenses")
            recommendations['health_advice'].append("Restez à l'intérieur si possible")
        # Analyser les pics prévus
        if predicted_peaks:
            for peak in predicted_peaks:
                timestamp = datetime.fromisoformat(peak['timestamp'])
                time_str = timestamp.strftime('%H:%M')
                recommendations['time_periods_to_avoid'].append(
                    f"{time_str} - Pic prévu: {peak['predicted_aqi']:.0f} PPM"
                )
            recommendations['actions'].append(
                f"⚠️ {len(predicted_peaks)} pic(s) de pollution prévu(s) dans les prochaines heures"
            )
        return recommendations
    def save_model(self):
        """Sauvegarde le modèle et le scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            logger.info(f"✓ Modèle sauvegardé: {self.model_path}")
        except Exception as e:
            logger.error(f"✗ Erreur sauvegarde modèle: {e}")
    def load_model(self):
        """Charge le modèle et le scaler depuis le disque"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                logger.info(f"✓ Modèle chargé: {self.model_path}")
                return True
            else:
                logger.warning("⚠ Fichiers de modèle non trouvés")
                return False
        except Exception as e:
            logger.error(f"✗ Erreur chargement modèle: {e}")
            return False
def generate_synthetic_training_data(num_samples=1000):
    """
    Génère des données synthétiques pour l'entraînement initial
    Utilisé pour démarrer le système avant d'avoir des données réelles
    Args:
        num_samples (int): Nombre d'échantillons à générer
    Returns:
        DataFrame: Données synthétiques
    """
    logger.info(f"🔧 Génération de {num_samples} échantillons synthétiques...")
    np.random.seed(42)
    # Générer des timestamps (derniers 30 jours)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=30)
    timestamps = pd.date_range(start=start_time, end=end_time, periods=num_samples)
    # Créer des patterns réalistes
    data = {
        'timestamp': timestamps,
        'air_quality_ppm': [],
        'temperature': [],
        'humidity': []
    }
    for i, ts in enumerate(timestamps):
        # Qualité de l'air avec patterns horaires et bruit
        hour = ts.hour
        base_aqi = 80  # Base
        hour_effect = 30 * np.sin((hour - 6) * np.pi / 12)  # Pic à 18h
        weekend_effect = -10 if ts.weekday() >= 5 else 0
        noise = np.random.normal(0, 15)
        aqi = max(10, base_aqi + hour_effect + weekend_effect + noise)
        # Température avec variation diurne
        temp_base = 25
        temp_hour = 8 * np.sin((hour - 6) * np.pi / 12)
        temp = temp_base + temp_hour + np.random.normal(0, 2)
        # Humidité inversement corrélée à température
        humidity = max(20, min(90, 70 - temp_hour * 2 + np.random.normal(0, 5)))
        data['air_quality_ppm'].append(round(aqi, 2))
        data['temperature'].append(round(temp, 1))
        data['humidity'].append(round(humidity, 1))
    df = pd.DataFrame(data)
    logger.info(f"✓ {len(df)} échantillons synthétiques générés")
    return df
# Test du module si exécuté directement
if __name__ == "__main__":
    print("=== Test du système de Machine Learning ===\n")
    # Créer le prédicteur
    predictor = AirQualityPredictor()
    # Générer des données synthétiques
    print("Génération de données d'entraînement...")
    training_data = generate_synthetic_training_data(num_samples=2000)
    # Entraîner le modèle
    print("\nEntraînement du modèle...")
    metrics = predictor.train_model(training_data)
    # Faire des prédictions
    print("\nPrédictions pour les prochaines 24 heures...")
    current_data = {
        'temperature': 25,
        'humidity': 60,
        'air_quality_ppm': 95
    }
    predictions = predictor.predict(current_data, hours_ahead=24)
    # Détecter les pics
    peaks = predictor.detect_pollution_peak(predictions, threshold=120)
    # Générer des recommandations
    recommendations = predictor.generate_recommendations(
        current_aqi=95,
        predicted_peaks=peaks
    )
    print("\n📋 RECOMMANDATIONS:")
    print(f"Statut: {recommendations['current_status']}")
    print("\nActions:")
    for action in recommendations['actions']:
        print(f"  • {action}")
    if recommendations['time_periods_to_avoid']:
        print("\nPériodes à éviter:")
        for period in recommendations['time_periods_to_avoid']:
            print(f"  • {period}")
    print("\n✓ Test terminé")