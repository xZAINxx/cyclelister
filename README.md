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

1. **Snap & List** — capture → AI identification → catalog match → generation → review → publish
2. **Smart Pricing** — Browse-API comps → undercut/floor/`.95` engine
3. **Sold History & Relist** — sale archival + one-click relist reusing images
4. **Inventory & Dashboard** — backlog/stale tracking, bulk intake, weekly summary
