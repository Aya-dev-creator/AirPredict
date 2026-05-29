#!/bin/bash
# Setup script for Air Quality Monitoring System (SQLite3 version)

set -e

echo "================================================"
echo "Air Quality Monitoring System - Setup"
echo "SQLite3 Version"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model)
    echo -e "${GREEN}✓${NC} Detected: $PI_MODEL"
else
    echo -e "${YELLOW}⚠${NC}  Not running on Raspberry Pi (OpenWeather API works on any platform)"
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python version: $PYTHON_VERSION"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}✗${NC} pip3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
fi

echo ""
echo "Step 1: Creating directory structure..."
mkdir -p data models logs backups
echo -e "${GREEN}✓${NC} Directories created"

echo ""
echo "Step 2: Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${YELLOW}⚠${NC}  Virtual environment already exists"
fi

echo ""
echo "Step 3: Activating virtual environment..."
source venv/bin/activate

echo ""
echo "Step 4: Upgrading pip..."
pip install --upgrade pip

echo ""
echo "Step 5: Installing Python dependencies..."
pip install -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

echo ""
echo "Step 6: Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓${NC} .env file created from template"
    echo -e "${YELLOW}⚠${NC}  Please edit .env file with your configuration"
else
    echo -e "${YELLOW}⚠${NC}  .env file already exists"
fi

echo ""
echo "Step 7: Initializing database..."
python3 -c "
from database import AirQualityDatabase
from config import config
db = AirQualityDatabase(config.DB_CONFIG['db_path'])
if db.connect():
    db.create_tables()
    print('✓ Database initialized successfully')
    db.close()
else:
    print('✗ Database initialization failed')
"

echo ""
echo "Step 8: Testing ML model..."
python3 -c "
from ml_model import AirQualityPredictor, generate_synthetic_training_data
import os
if not os.path.exists('./models/air_quality_model.pkl'):
    print('Training initial ML model with synthetic data...')
    predictor = AirQualityPredictor()
    training_data = generate_synthetic_training_data(num_samples=1000)
    predictor.train_model(training_data)
    print('✓ ML model trained and saved')
else:
    print('✓ ML model already exists')
"

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration:"
echo "   nano .env"
echo ""
echo "2. Start the system:"
echo "   python3 main.py"
echo ""
echo "3. Or run in background:"
echo "   nohup python3 main.py > output.log 2>&1 &"
echo ""
echo "4. View logs:"
echo "   tail -f air_quality_system.log"
echo ""
echo "5. Access database:"
echo "   sqlite3 ./data/air_quality.db"
echo ""
echo "For more information, see README.md"
echo ""