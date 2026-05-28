#!/bin/bash
# Quick start script for Python FastAPI backend

echo "🚀 Starting Python FastAPI Backend..."

# Change to backend directory
cd backend || exit 1

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if [ ! -f "venv/lib/python*/site-packages/fastapi/__init__.py" ]; then
    echo "📥 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "⚙️  Please edit backend/.env and add your GEMINI_API_KEY"
    exit 1
fi

# Start the backend server on port 8001 (main-dev uses 8001, main uses 8000)
export PORT=8000
echo "✅ Starting FastAPI server on http://localhost:8000"
echo "📚 API Docs available at http://localhost:8000/docs"
echo ""
python main.py
