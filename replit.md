# AI Manus - Replit Setup

## Overview
AI Manus is a general-purpose AI Agent system that supports running tools and operations in a sandbox environment. This project was cloned from GitHub and adapted to run on Replit.

## Architecture
- **Frontend**: Vue.js 3 + Vite (port 5000)
- **Backend**: Python FastAPI (port 8000)
- **Database**: MongoDB (external - MongoDB Atlas)
- **Cache**: Redis (local via Nix)
- **Sandbox**: Docker-based sandbox (requires external sandbox or Docker host)

## Project Structure
```
frontend/     - Vue.js frontend application
backend/      - Python FastAPI backend
sandbox/      - Sandbox API (Docker-based, not used locally on Replit)
mockserver/   - Mock LLM server for testing
docs/         - Documentation
start.sh      - Startup script for Replit
```

## Required Secrets/Environment Variables
- `API_KEY` - LLM API key (OpenAI, DeepSeek, etc.)
- `MONGODB_URI` - MongoDB Atlas connection string
- `JWT_SECRET_KEY` - JWT secret for authentication

## Non-Secret Environment Variables (already configured)
- `API_BASE` - LLM API base URL (default: https://api.openai.com/v1)
- `MODEL_NAME` - LLM model name (default: gpt-4o)
- `AUTH_PROVIDER` - Authentication mode (set to "local")
- `LOCAL_AUTH_EMAIL` - Local admin email (admin@example.com)
- `LOCAL_AUTH_PASSWORD` - Local admin password (admin)
- `REDIS_HOST` - Redis host (localhost)
- `SEARCH_PROVIDER` - Search engine (bing)

## How to Run
The `start.sh` script runs:
1. Redis server (daemonized)
2. Backend API on port 8000
3. Frontend dev server on port 5000 (with proxy to backend)

## Login
- Auth mode: local (no registration needed)
- Email: admin@example.com
- Password: admin

## Recent Changes
- 2026-02-20: Initial Replit adaptation
  - Configured Vite to port 5000 with allowedHosts
  - Set up Redis locally via Nix
  - Created startup script
  - Set environment variables for local auth mode
