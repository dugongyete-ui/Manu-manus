#!/bin/bash
set -e

echo "============================================"
echo "  AI Manus - Auto Install Dependencies"
echo "============================================"

echo ""
echo "[1/3] Installing Python backend dependencies..."
cd /home/runner/workspace/backend
pip install -r requirements.txt --quiet 2>&1 | tail -3
echo "[OK] Backend dependencies installed"

echo ""
echo "[2/3] Installing Node.js frontend dependencies..."
cd /home/runner/workspace/frontend
npm install --silent 2>&1 | tail -3
echo "[OK] Frontend dependencies installed"

echo ""
echo "[3/3] Installing Playwright browser..."
playwright install chromium 2>&1 | tail -3
echo "[OK] Playwright browser installed"

echo ""
echo "============================================"
echo "  All dependencies installed successfully!"
echo "============================================"
echo ""
echo "To start the application, run: bash start.sh"
echo "Or use the 'Start AI Manus' workflow in Replit"
