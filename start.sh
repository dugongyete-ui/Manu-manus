#!/bin/bash

redis-server --daemonize yes --port 6379

cd /home/runner/workspace/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

cd /home/runner/workspace/frontend
BACKEND_URL=http://localhost:8000 npm run dev &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
