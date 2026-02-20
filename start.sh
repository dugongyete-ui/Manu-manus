#!/bin/bash

echo "=== Starting AI Manus ==="

redis-server --daemonize yes --port 6379
echo "[OK] Redis started"

cd /home/runner/workspace/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "[OK] Backend starting on port 8000..."

cd /home/runner/workspace/frontend
BACKEND_URL=http://localhost:8000 npm run dev &
FRONTEND_PID=$!
echo "[OK] Frontend starting on port 5000..."

wait $BACKEND_PID $FRONTEND_PID
