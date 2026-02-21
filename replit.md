# AI Manus - AI Agent System

## Overview
AI Manus adalah sistem AI Agent general-purpose yang mendukung menjalankan berbagai tools dan operasi. Proyek ini di-clone dari GitHub (simpleyyt/ai-manus) dan diadaptasi untuk berjalan sepenuhnya di Replit tanpa Docker.

Fitur utama:
- Terminal, Browser, File, Web Search, dan messaging tools
- Sandbox environment per task (Docker-based, perlu dikonfigurasi terpisah)
- Session history via PostgreSQL/Redis
- Upload/download file
- Multibahasa (Chinese & English)
- Autentikasi pengguna (local/password/none)
- Integrasi MCP (Model Context Protocol)

## Architecture
- **Frontend**: Vue.js 3 + Vite + TypeScript + Tailwind CSS (port 5000)
- **Backend**: Python FastAPI + Uvicorn (port 8000)
- **Database**: PostgreSQL (Replit built-in, via DATABASE_URL)
- **Cache/Queue**: Redis (local, port 6379)
- **LLM**: OpenAI-compatible API (configurable)
- **Sandbox**: LocalSandbox (runs commands locally, replaces Docker)

## Project Structure
```
frontend/           - Vue.js frontend application
  src/
    api/            - API client (auth, agent, file)
    components/     - Vue components (ChatBox, VNCViewer, FilePanel, etc.)
    views/          - Pages (Login, Chat, etc.)
    stores/         - State management
    i18n/           - Internationalization (CN/EN)
  vite.config.ts    - Vite config (port 5000, proxy to backend)

backend/            - Python FastAPI backend
  app/
    core/           - Config settings
    domain/         - Domain models & services (Agent, Session, Auth)
    infrastructure/ - Storage (PostgreSQL, Redis), LLM, Search, Sandbox
    interfaces/     - API routes, schemas, dependencies
    application/    - Business services (Auth, Agent, File, Token)

sandbox/            - Sandbox API (Docker-based, not used on Replit)
mockserver/         - Mock LLM server for testing
docs/               - Documentation

start.sh            - Startup script (Redis + Backend + Frontend)
install.sh          - Auto-install all dependencies
```

## How to Run
1. Run `bash install.sh` to install all dependencies
2. Click "Run" or use `bash start.sh` to start:
   - Redis server (daemonized)
   - Backend API on port 8000
   - Frontend dev server on port 5000 (with proxy to backend)

## Login
- Auth mode: `local` (no registration needed)
- Email: admin@example.com
- Password: admin123

## Environment Variables (Configured)
- `API_BASE` - LLM API base URL (https://api-dzeck--az405scqqg.replit.app/v1)
- `API_KEY` - LLM API key (secret)
- `MODEL_NAME` - LLM model name (claude40opus)
- `LLM_PROVIDER` - LLM provider name sent in extra_body (Perplexity)
- `AUTH_PROVIDER` - Authentication mode (local)
- `LOCAL_AUTH_EMAIL` / `LOCAL_AUTH_PASSWORD` - Local admin credentials
- `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` - Redis config
- `JWT_SECRET_KEY` - JWT secret (secret)
- `DATABASE_URL` - PostgreSQL connection (auto-configured by Replit)
- `SEARCH_PROVIDER` - Search engine (bing)
- `GOOGLE_SEARCH_API_KEY` / `GOOGLE_SEARCH_ENGINE_ID` - Google search (secrets)

## Key Technical Decisions
- PostgreSQL replaces MongoDB (original used MongoDB + GridFS)
- Local file storage replaces GridFS for file uploads
- Redis runs locally via Nix (not Docker container)
- Frontend proxies `/api` requests to backend via Vite proxy
- LocalSandbox replaces DockerSandbox for shell/file operations
- PlaywrightBrowser runs headless Chromium locally (no CDP required)

## Recent Changes
- 2026-02-21: Switched LLM provider to api-dzeck (Perplexity/claude40opus)
  - Updated API_BASE to https://api-dzeck--az405scqqg.replit.app/v1
  - Updated MODEL_NAME to claude40opus
  - Added LLM_PROVIDER config (sent via extra_body in OpenAI SDK)
  - Increased MAX_TOKENS to 4096
  - API tested and confirmed working
- 2026-02-21: LocalSandbox integration completed
  - Created LocalSandbox class (local_sandbox.py) replacing DockerSandbox
  - Shell commands run locally via asyncio subprocess
  - File operations use local filesystem (sandbox_workspace directory)
  - PlaywrightBrowser updated to support headless local launch
  - Playwright Chromium installed for browser automation
  - All tools (shell, file, browser, search, message) now fully functional
- 2026-02-21: Full Replit adaptation completed
  - Installed all Python/Node.js dependencies
  - Fixed GridFS import error (replaced with LocalFileStorage)
  - Created auto-install script (install.sh)
  - PostgreSQL database created and connected
  - Redis, Backend, Frontend all running successfully
  - Login page functional with local auth

## User Preferences
- Language: Indonesian (Bahasa Indonesia)
- Goal: Make this project work fully on Replit, comparable to manus.im
