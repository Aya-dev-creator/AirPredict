#!/bin/bash
# Script d'installation automatique des corrections - AirWatch
# Ce script applique toutes les corrections identifiées

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================"
echo "🔧 INSTALLATION DES CORRECTIONS - AirWatch"
echo "================================================"
echo ""

# Fonction pour afficher les messages
function print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

function print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

function print_error() {
    echo -e "${RED}✗${NC} $1"
}

function print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Vérifier qu'on est dans le bon dossier
if [ ! -f "web_server.py" ]; then
    print_error "Erreur : web_server.py non trouvé"
    print_info "Veuillez exécuter ce script depuis le dossier racine du projet"
    exit 1
fi

print_success "Dossier du projet détecté"
echo ""

# ========== ÉTAPE 1 : SAUVEGARDE ==========
echo "Étape 1/6 : Sauvegarde des fichiers originaux"
echo "---------------------------------------------"

# Créer le dossier de sauvegarde
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR/templates"

# Sauvegarder les fichiers existants
if [ -d "templates" ]; then
    cp templates/*.html "$BACKUP_DIR/templates/" 2>/dev/null || true
    print_success "Fichiers HTML sauvegardés dans $BACKUP_DIR/"
else
    print_warning "Dossier templates/ non trouvé, création en cours..."
    mkdir -p templates
fi

echo ""

# ========== ÉTAPE 2 : VÉRIFICATION DES DÉPENDANCES ==========
echo "Étape 2/6 : Vérification des dépendances"
echo "----------------------------------------"

# Vérifier Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    print_success "Python installé : $PYTHON_VERSION"
else
    print_error "Python 3 non trouvé"
    exit 1
fi

# Vérifier pip
if command -v pip3 &> /dev/null; then
    print_success "pip3 installé"
else
    print_warning "pip3 non trouvé, tentative d'installation..."
    sudo apt-get update && sudo apt-get install -y python3-pip
fi

# Vérifier les modules Python nécessaires
echo ""
print_info "Vérification des modules Python..."

REQUIRED_MODULES=(
    "flask"
    "flask_socketio"
    "flask_cors"
    "numpy"
    "pandas"
    "scikit-learn"
    "requests"
)

MISSING_MODULES=()

for module in "${REQUIRED_MODULES[@]}"; do
    if python3 -c "import ${module//-/_}" 2>/dev/null; then
        print_success "Module $module installé"
    else
        MISSING_MODULES+=("$module")
        print_warning "Module $module manquant"
    fi
done

if [ ${#MISSING_MODULES[@]} -gt 0 ]; then
    echo ""
    print_info "Installation des modules manquants..."
    pip3 install "${MISSING_MODULES[@]}" --break-system-packages
    print_success "Modules installés"
fi

echo ""

# ========== ÉTAPE 3 : COPIE DES FICHIERS CORRIGÉS ==========
echo "Étape 3/6 : Application des corrections"
echo "---------------------------------------"

# Vérifier si les fichiers corrigés existent
CORRECTED_FILES="/home/claude/corrected_files"

if [ ! -d "$CORRECTED_FILES" ]; then
    print_error "Fichiers corrigés non trouvés dans $CORRECTED_FILES"
    print_info "Téléchargez d'abord les fichiers corrigés"
    exit 1
fi

# Copier les fichiers HTML corrigés
if [ -d "$CORRECTED_FILES/templates" ]; then
    cp -v "$CORRECTED_FILES/templates"/*.html templates/
    print_success "Fichiers HTML corrigés copiés"
else
    print_error "Templates corrigés non trouvés"
    exit 1
fi

echo ""

# ========== ÉTAPE 4 : CONFIGURATION ==========
echo "Étape 4/6 : Configuration"
echo "------------------------"

# Vérifier/créer le fichier .env
if [ ! -f ".env" ]; then
    print_warning "Fichier .env non trouvé, création..."
    
    cat > .env << 'EOF'
# Configuration de l'API OpenWeatherMap
# Obtenez votre clé gratuite sur : https://openweathermap.org/api
OPENWEATHER_API_KEY=your_api_key_here

# Configuration de la base de données
DB_PATH=./data/air_quality.db

# Configuration du serveur web
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false
FLASK_SECRET_KEY=change-this-in-production

# Configuration MQTT (optionnel)
MQTT_BROKER=broker.hivemq.com
MQTT_PORT=1883
MQTT_TOPIC=air_quality/sensor_data

# Seuils de qualité de l'air (PPM)
THRESHOLD_GOOD=50
THRESHOLD_MODERATE=100
THRESHOLD_UNHEALTHY=150
THRESHOLD_VERY_UNHEALTHY=200
THRESHOLD_HAZARDOUS=300

# Configuration des capteurs (GPIO)
DHT11_PIN=4
MQ135_PIN=17
GPS_ENABLED=true
SENSOR_READ_INTERVAL=60

# Configuration email (pour les alertes)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
ALERT_EMAIL=
EOF
    
    print_success "Fichier .env créé"
    print_warning "IMPORTANT : Configurez votre clé API dans le fichier .env"
else
    print_success "Fichier .env existant"
fi

# Vérifier si la clé API est configurée
if grep -q "your_api_key_here" .env 2>/dev/null; then
    print_warning "Clé API météo non configurée"
    print_info "Éditez le fichier .env et ajoutez votre clé OpenWeatherMap"
    echo ""
    print_info "Pour obtenir une clé gratuite :"
    echo "   1. Visitez https://openweathermap.org/api"
    echo "   2. Créez un compte gratuit"
    echo "   3. Obtenez votre clé API"
    echo "   4. Remplacez 'your_api_key_here' dans .env"
fi

echo ""

# ========== ÉTAPE 5 : INITIALISATION DE LA BASE DE DONNÉES ==========
echo "Étape 5/6 : Initialisation de la base de données"
echo "-----------------------------------------------"

# Créer les dossiers nécessaires
mkdir -p data models logs

print_info "Initialisation de la base de données SQLite..."

python3 << 'PYTHON_SCRIPT'
from database import AirQualityDatabase
from config import config

try:
    db_path = config.DB_CONFIG.get('db_path', './data/air_quality.db')
    db = AirQualityDatabase(db_path=db_path)
    
    if db.connect():
        db.create_tables()
        print('✓ Base de données initialisée avec succès')
        db.close()
    else:
        print('✗ Échec de l\'initialisation de la base de données')
        exit(1)
except Exception as e:
    print(f'✗ Erreur : {e}')
    exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    print_success "Base de données initialisée"
else
    print_error "Erreur lors de l'initialisation de la base de données"
    exit 1
fi

echo ""

# ========== ÉTAPE 6 : ENTRAÎNEMENT DU MODÈLE ML ==========
echo "Étape 6/6 : Entraînement du modèle ML"
echo "------------------------------------"

if [ ! -f "./models/air_quality_model.pkl" ]; then
    print_info "Modèle ML non trouvé, entraînement avec données synthétiques..."
    
    python3 << 'PYTHON_SCRIPT'
from ml_model import AirQualityPredictor, generate_synthetic_training_data

try:
    print('Génération de données d\'entraînement synthétiques...')
    predictor = AirQualityPredictor()
    training_data = generate_synthetic_training_data(num_samples=2000)
    
    print('Entraînement du modèle (cela peut prendre quelques secondes)...')
    predictor.train_model(training_data)
    
    print('✓ Modèle ML entraîné et sauvegardé')
except Exception as e:
    print(f'✗ Erreur lors de l\'entraînement : {e}')
    exit(1)
PYTHON_SCRIPT
    
    if [ $? -eq 0 ]; then
        print_success "Modèle ML entraîné"
    else
        print_error "Erreur lors de l'entraînement du modèle ML"
        print_warning "Le système fonctionnera sans prédictions ML"
    fi
else
    print_success "Modèle ML déjà existant"
fi

echo ""

# ========== RÉSUMÉ ==========
echo "================================================"
echo "✅ INSTALLATION TERMINÉE"
echo "================================================"
echo ""

print_success "Toutes les corrections ont été appliquées avec succès !"
echo ""

echo "📋 Résumé des corrections appliquées :"
echo "   ✓ Fichiers HTML traduits en français"
echo "   ✓ Icônes remplacées par Font Awesome"
echo "   ✓ Carte GPS centrée sur Casablanca avec géolocalisation"
echo "   ✓ Support des prédictions ML activé"
echo "   ✓ Affichage météo (température/humidité) corrigé"
echo ""

echo "📁 Fichiers sauvegardés dans : $BACKUP_DIR/"
echo ""

echo "🚀 Prochaines étapes :"
echo ""
echo "1. Configurer la clé API météo (si pas encore fait) :"
echo "   nano .env"
echo "   # Remplacer 'your_api_key_here' par votre clé"
echo ""
echo "2. Démarrer le serveur :"
echo "   python3 web_server.py"
echo "   # OU en mode complet avec capteurs :"
echo "   python3 main.py"
echo ""
echo "3. Ouvrir dans le navigateur :"
echo "   http://localhost:5000"
echo ""

echo "📖 Documentation complète disponible dans :"
echo "   - GUIDE_PROJET_COMPLET.md"
echo "   - GUIDE_CORRECTIONS_COMPLET.md"
echo ""

print_info "Si vous rencontrez des problèmes, consultez la section DÉPANNAGE du guide"
echo ""

echo "================================================"
echo "Bonne utilisation ! 🌍"
echo "================================================"