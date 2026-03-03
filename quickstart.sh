#!/bin/bash
# Quick Start Script - Complete Air Quality System with Web Interface

set -e

echo "================================================"
echo "🌍 Air Quality Monitoring System - Quick Start"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check Python version
echo -e "${BLUE}Checking Python...${NC}"
python3 --version
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Create directories
echo -e "${BLUE}Creating directories...${NC}"
mkdir -p data models logs backups templates static/css static/js static/images
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Check .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
    echo ""
    echo -e "${YELLOW}⚠ IMPORTANT: Edit .env file with your settings!${NC}"
    echo "   Especially: OPENWEATHER_API_KEY"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to exit and configure .env..."
fi

# Initialize database
echo -e "${BLUE}Initializing database...${NC}"
python3 -c "
from database import AirQualityDatabase
from config import config

try:
    db_path = config.DB_CONFIG.get('db_path', './data/air_quality.db')
    db = AirQualityDatabase(db_path=db_path)
    if db.connect():
        db.create_tables()
        print('✓ Database initialized')
        db.close()
    else:
        print('✗ Database initialization failed')
except Exception as e:
    print(f'Error: {e}')
"
echo ""

# Check if ML model exists
if [ ! -f "./models/air_quality_model.pkl" ]; then
    echo -e "${BLUE}Training ML model (first time)...${NC}"
    python3 -c "
from ml_model import AirQualityPredictor, generate_synthetic_training_data

try:
    predictor = AirQualityPredictor()
    print('Generating synthetic training data...')
    training_data = generate_synthetic_training_data(num_samples=1000)
    print('Training model...')
    predictor.train_model(training_data)
    print('✓ ML model trained and saved')
except Exception as e:
    print(f'Error: {e}')
"
    echo ""
fi

# Check OpenWeather API key
echo -e "${BLUE}Checking OpenWeather API configuration...${NC}"
if grep -q "your_api_key_here" .env 2>/dev/null || ! grep -q "OPENWEATHER_API_KEY" .env 2>/dev/null; then
    echo -e "${YELLOW}⚠ OpenWeather API key not configured${NC}"
    echo ""
    echo "To get a FREE API key:"
    echo "1. Visit: https://openweathermap.org/api"
    echo "2. Sign up for a free account"
    echo "3. Get your API key (Free tier: 1,000 calls/day)"
    echo "4. Add to .env: OPENWEATHER_API_KEY=your_key_here"
    echo ""
    echo "Weather features will be limited without API key."
    echo ""
else
    echo -e "${GREEN}✓ OpenWeather API key configured${NC}"
fi
echo ""

# Show startup options
echo "================================================"
echo "🚀 System Ready!"
echo "================================================"
echo ""
echo "Choose startup mode:"
echo ""
echo "1) Full System (Sensors + Database + ML + Web Interface)"
echo "   Command: python3 main.py"
echo ""
echo "2) Web Interface Only (Testing/Development)"
echo "   Command: python3 web_server.py"
echo ""
echo "3) Background Mode (Production)"
echo "   Command: nohup python3 main.py > output.log 2>&1 &"
echo ""

read -p "Enter choice (1-3) or press Ctrl+C to exit: " choice

case $choice in
    1)
        echo ""
        echo -e "${GREEN}Starting full system...${NC}"
        echo ""
        echo "📊 Dashboard will be available at: http://localhost:5000"
        echo "🔴 Press Ctrl+C to stop"
        echo ""
        sleep 2
        python3 main.py
        ;;
    2)
        echo ""
        echo -e "${GREEN}Starting web interface only...${NC}"
        echo ""
        echo "📊 Dashboard: http://localhost:5000"
        echo "📡 API: http://localhost:5000/api/health"
        echo "🔴 Press Ctrl+C to stop"
        echo ""
        sleep 2
        python3 web_server.py
        ;;
    3)
        echo ""
        echo -e "${GREEN}Starting in background mode...${NC}"
        nohup python3 main.py > output.log 2>&1 &
        PID=$!
        echo ""
        echo "✓ System started with PID: $PID"
        echo ""
        echo "To check status:"
        echo "  ps aux | grep main.py"
        echo ""
        echo "To view logs:"
        echo "  tail -f air_quality_system.log"
        echo ""
        echo "To stop:"
        echo "  pkill -f main.py"
        echo ""
        echo "Dashboard: http://localhost:5000"
        echo ""
        ;;
    *)
        echo ""
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac