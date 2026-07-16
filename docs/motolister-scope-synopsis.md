# MotoLister — full-scope synopsis, aligned to CycleLister

Sources: site crawl (docs/motolister-feature-map.md, 17 pages), PROJECT_SPEC §2,
and product screenshots of MotoLister 5.x (desktop UI). This is the complete
conceptual model of the tool CycleLister reinterprets — not a feature checklist
to clone, but the workflow logic to modernize.

## 1. MotoLister's complete conceptual model

MotoLister is a **Windows desktop cockpit** organized around one loop:

```
PICK VEHICLE ──> PICK PART TYPE ──> TEMPLATE + FITMENT ──> PHOTOS ──> PRICE ──> PUBLISH
   (or PICK BY MPN / barcode scan — the Pro fast path)
```

### The six pillars (with what the UI actually looks like)

| # | Pillar | How MotoLister does it | Evidence |
|---|--------|------------------------|----------|
| 1 | **Part taxonomy picker** | A dense A–Z grid of ~150 part-type icon tiles (air cleaner → wiring), with vehicle-category tabs along the bottom: ALL, Aircraft, Apparel, ATV, Boat, Cart/Buggy, Cruiser, Dirtbike, PWC, Scooter, Snowmobile, Sportbike, Trike, UTV. Sub-30-second listing rests on this grid being muscle-memory fast. | screenshot; homepage |
| 2 | **MPN fast path (Pro)** | Type or USB-barcode-scan an OEM part number → tool resolves part type + compatibility + Smart Title in one step, skipping the grid entirely. | /search-by-mpn |
| 3 | **Fitment authority (Pro, $50/mo)** | Licensed OEM fitment catalog across 9 moto brands + ATV/UTV/scooter/PWC/snowmobile; one MPN → up to 100+ vehicle compatibility chart injected into the listing. Non-Pro falls back to fitment-from-vehicle-selection; users can extend vehicles/MPNs by hand. | /oem-fitment-catalog |
| 4 | **Smart Titles (Pro)** | Title format adapts to fitment breadth: 1–2 models → years+models in title; 6+ → brand + part type + MPN only. "As Written" opt-out. | /smart-titles |
| 5 | **Photo bench** | Tethered-camera live upload (Canon T6 + suspension rig + DIY booth plans); Pro editor: auto-crop-to-square, brightness/contrast, white-background magic wand. | /photo-editor, /get-started |
| 6 | **Ops loop** | Live price comps (existing + sold) with MANUAL price pick; auto-printed Dymo inventory labels; stock-location updater; per-category templates (shipping/returns/payment); listing counter ("Listings created: 517") as the motivating scoreboard. | /pricing-and-features; screenshot header |

Cost model: free ≤25/mo, then $10/mo + per-listing fees capped ~$200/mo, +$50/mo Pro.
Platform: Windows desktop only; mobile "coming soon" for years.

### What makes it work (the lessons worth keeping)
- **Speed through recognition, not typing** — the icon grid and barcode scan exist so the seller almost never types a description from scratch.
- **The catalog IS the product** — thousands of pre-loaded parts + licensed fitment means a listing starts 80% done.
- **A visible scoreboard** — the created-listings counter front and center.

### Where it's stuck (the gaps CycleLister exploits)
- Desktop-only, dated chrome, manual pick flows — no camera-first capture, no AI.
- Pricing shows comps but decides nothing — no rules engine, no .95 discipline.
- No sold-history relist loop, no analytics beyond the counter, per-listing fees.

## 2. Alignment map — MotoLister concept → CycleLister modern take

| MotoLister concept | CycleLister reinterpretation | Status |
|---|---|---|
| Pick-vehicle → pick-part icon grid | **AI vision identification from photos** is the primary path (the grid's job — "don't make me type" — done by camera). The grid's browse value survives as the **Catalog screen**: searchable, brand-tabbed browser of the seller's own growing parts catalog, one click from any part to a prefilled draft. | AI path ✅ P1 · Catalog screen ✅ this pass |
| MPN search + barcode scan | Part-number hint field today; scanner types into it (USB scanners are keyboards). Dedicated scan affordance + camera barcode read | 🔜 P1.x |
| Licensed OEM fitment catalog | Seller's own 24-year fitment history (seeded: 454 parts / 213 fitments) + AI suggestions (confidence-scored, confirm-to-trust) + manual override. No licensing fee; grows with every listing | ✅ P1, compounding |
| Smart Titles by fitment breadth | Adaptive-title rule in the generation prompt (1–2 models → years+models; 6+ → brand+type+MPN) | ✅ shipped |
| Compatibility chart in listing | Fitment rows render into the description at generation; full eBay compatibility payload | ✅ basic · 🔜 P2 |
| Photo bench + Pro editor | Phone camera IS the tethered rig (capture → upload in one gesture); auto-crop/white-bg cleanup planned via `processed_path` | ✅ capture · 🔜 P2 cleanup |
| Live price comps, manual pick | **Phase 2 pricing engine decides**: Browse-API comps → 5–10% undercut → floor → .95 ending, with the explanation shown ("$13.95 — 8% below lowest competitor $15.20") | 🔜 P2 |
| Per-category templates | `templates` table (policies + boilerplate + specifics defaults), learned automatically from edited listings | ✅ schema · 🔜 UI P2 |
| Dymo labels + stock location | `stock_location` field + printable QR shelf labels | 🔜 P4 (adopted from gap analysis) |
| Listings-created scoreboard | **Pit Wall dashboard** — operations, revenue, AI cost, inventory health; the counter grown into an instrument panel | ✅ shipped |
| Sold-history relist | One-click relist reusing retained images — MotoLister has nothing here | 🔜 P3 (our moat) |
| $10–250/mo + per-listing fees | Self-hosted: Supabase free tier + low-single-digit-cents AI per listing | ✅ |

## 3. Scope guardrails
MotoLister's Aircraft/Boat/Apparel breadth is NOT in scope — CycleLister stays a
motorcycle-NOS specialist (spec §2). Its licensed-fitment dependency is explicitly
rejected (spec §9): our authority is the seller's own history, AI-assisted, seller-confirmed.
