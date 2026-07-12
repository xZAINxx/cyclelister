# CycleLister

AI-powered eBay listing platform for D's Cycle Connection — photograph a motorcycle part, get a complete, competitively-priced eBay listing draft in under a minute.

**Source of truth:** [PROJECT_SPEC.md](PROJECT_SPEC.md). Sections §6 (listing pipeline), §7 (pricing engine), §9 (fitment), and §10 (eBay integration) are load-bearing.

## Stack (per spec §4)

- **Frontend:** React + Vite PWA (camera capture, installable on phone/tablet/desktop)
- **Backend:** FastAPI (Python)
- **Data:** PostgreSQL + Storage + Auth via Supabase
- **AI:** Claude API (vision identification + listing generation)
- **Marketplace:** eBay Sell/Browse APIs (OAuth 2.0, sandbox first)

## Build phases (spec §16)

1. **Snap & List** ✅ *(this repo, in review)* — capture → AI identification → catalog match → generation → review → publish (sandbox)
2. **Smart Pricing** — Browse-API comps → undercut/floor/`.95` engine
3. **Sold History & Relist** — sale archival + one-click relist reusing images
4. **Inventory & Dashboard** — backlog/stale tracking, bulk intake, weekly summary

## Running locally (Phase 1)

```bash
# Backend (Python 3.12+)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # fill in ANTHROPIC_API_KEY at minimum
.venv/bin/uvicorn app.main:app --port 8000 --reload

# Frontend (Node 20+)
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api -> :8000
```

Local dev needs no Supabase/eBay credentials: auth is bypassed with a dev user,
images go to local disk, tables auto-create on a local database
(`docker compose -f docker-compose.dev.yml up -d` for Postgres, or point
`DATABASE_URL` at SQLite). Publishing returns 503 until eBay sandbox
credentials are configured in `backend/.env` and the seller completes OAuth
via `GET /api/ebay/oauth/url`.

```bash
# Tests
cd backend && .venv/bin/python -m pytest tests

# Seed the catalog from an existing-listings CSV export (spec §9.1)
.venv/bin/python scripts/import_listings.py export.csv

# Production schema
alembic upgrade head
```
