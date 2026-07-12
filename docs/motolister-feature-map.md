# MotoLister feature map

Research pass over https://www.motolister.com (crawled 2026-07-12: homepage, pages-sitemap.xml, /pricing-and-features, /listing-fees, /oem-fitment-catalog, /smart-titles, /search-by-mpn, /photo-editor, /introducing-motolister-pro, /what-s-new-with-motolister-5-0, /get-started, /tutorials, /oem-fitment-editor, /how-to-customize-your-template, /add-a-video-to-your-listings, /featured-sellers, /about-us). MotoLister is the desktop eBay-listing tool CycleLister replaces; the client (D's/DS Cycle Connection) even appears in MotoLister's testimonials. Current shipping version: MotoLister 5.4 (Windows desktop download; mobile "COMING SOON"). Site last touched ~2024; many tutorial pages are video-only (content not extractable — noted below, not fabricated).

Legend: **VERIFIED** = seen on the site. **CLAIMED-IN-SPEC** = only from PROJECT_SPEC.md §2. Pages in parentheses.

## What MotoLister does

### Listing creation
- **VERIFIED — Sub-30-second listing flow.** "List your part on eBay in less than 30 seconds"; pick-your-vehicle then pick-your-part flow. (homepage)
- **VERIFIED — Pre-loaded parts catalog.** "Thousands of parts already loaded into the software making it so easy to simply find your part and list it." (/pricing-and-features)
- **VERIFIED — Search by MPN + barcode scanning (Pro).** Enter or scan an OEM part number; tool matches a part type and generates a listing with full compatibility charts and a Smart Title. Works with "most standard USB barcode scanners." (/search-by-mpn, /introducing-motolister-pro)
- **VERIFIED — Smart Titles (Pro).** Auto-generated titles from MPN fitment data; format adapts to model count (1 model: years+brand+model+part+MPN; 2 models: both; 6+ models: brand+part type+MPN only). Optional "As Written" setting keeps the title untouched. (/smart-titles, /what-s-new-with-motolister-5-0)
- **VERIFIED — Pop-up listing confirmation** before submit, disableable. (tutorial index "Disable the automatic pop-up listing confirmation", /tutorials)
- **VERIFIED — Part variations** exist as a feature ("What are part variations" tutorial); details video-only, not extractable. (/part-variations, /tutorials)
- **VERIFIED — Assembly listing / Assembly Compatibility (Pro).** Named 5.0 Pro feature plus a "List an assembly" tutorial; details video-only. (/assemblies, /what-s-new-with-motolister-5-0, /tutorials)

### Fitment / compatibility
- **VERIFIED — OEM Fitment Catalog (Pro, $50/mo).** Part-number → auto compatibility chart in the eBay listing; example: one KTM part number matching "103 different vehicles"; part numbers updated with each release. (/oem-fitment-catalog)
- **VERIFIED — Catalog coverage across powersports.** Motorcycles (Honda 1977-2016, Kawasaki 1985-2016, KTM 1994-2016, Suzuki 1973-2016, Yamaha 1962-2016, Harley-Davidson 1979-2016, Ducati, MV Agusta, Aprilia), plus ATVs, UTVs, scooters, PWC, snowmobiles (Polaris, Arctic Cat, Can-Am, Sea-Doo, Ski-Doo…). (/oem-fitment-editor)
- **VERIFIED — Non-Pro fallback: compatibility from vehicle selection.** "If you choose not to subscribe to MotoLister Pro, then the part's compatibility will be based off of your vehicle selection." (homepage)
- **VERIFIED — User-extendable fitment data.** Tutorials for "Add your own vehicle" and "Add manufacturer part numbers" (video-only). (/how-to-add-your-own-vehicle, /add-manufacturer-part-numbers)

### Photos
- **VERIFIED — Live photo upload.** Tethered-camera instant photo capture into the listing ("pictures uploading instantly" per testimonials); recommended hardware Canon T6, camera-suspension rig, free DIY photo-booth plans. (homepage, /pricing-and-features, /get-started)
- **VERIFIED — Photo editor (Pro, added in 5.0).** Brightness/contrast, manual crop, auto-crop to square "to utilize all of eBay's available photo space," and a "magic wand" that attempts a "crisp, clean, white background" (works best on already-white backgrounds). (/photo-editor)
- **VERIFIED — Video embed in listings** via manual HTML template edit + self-hosted (S3) video URL — a workaround doc, not a product feature. (/add-a-video-to-your-listings)

### Pricing
- **VERIFIED — Live price comparison.** "Compare product pricing live from existing and sold listings" / "Search existing comparable listings within the software and price your part according to the going rate." Manual: shows comps, seller picks the price — no auto-pricing rules shown anywhere. (homepage, /pricing-and-features)

### Inventory
- **VERIFIED — Auto-generated, auto-printed inventory labels.** "Automatically generates and prints a customized inventory label"; recommended Dymo 450 printer + Dymo 30256 labels. (homepage, /pricing-and-features, /get-started)
- **VERIFIED — Inventory tool with stock location.** "Inventory tool to check listings on eBay and update stock location." (/pricing-and-features)

### Templates / settings
- **VERIFIED — HTML description template, user-editable.** File → Settings → HTML; edit MotoLister's template or paste your own eBay template HTML. (/how-to-customize-your-template)
- **VERIFIED — Shipping settings** exist (tutorial "Update the shipping settings", video-only). (/tutorials)
- **VERIFIED — Payments setting.** "Accept Credit Cards in Settings Page" (5.0). (/what-s-new-with-motolister-5-0)
- **CLAIMED-IN-SPEC — Saved per-category templates (shipping/returns/payment).** Spec §2 says templates are per-category; the site only shows a single global HTML template + shipping settings.

### Business model / platform
- **VERIFIED — Windows desktop only; mobile "COMING SOON."** (homepage, /download-page)
- **VERIFIED — Pricing:** free to 25 listings/mo, then $10/mo base + tiered per-listing fees capped at $200/mo; Pro is +$50/mo (fitment catalog, MPN search, Smart Titles, photo editor, assembly compatibility). 30-day free trial; hardware sold with 90-day guarantee. (/pricing-and-features, /listing-fees, /get-started)
- **VERIFIED — Scale proof points:** users report 300-500 listings/day per lister; >1M listings created via the tool. (/featured-sellers, /about-us)

### Spec §2 claims not verifiable on the site
- "Keyword-stuffed titles," "weak multi-model fitment" — weakness characterizations, plausible from Smart Title examples (which cram years/models/MPN) but not stated by the vendor.
- No sold-history/relist workflow, no AI photo identification — consistent with the site (neither is mentioned anywhere), verified by absence only.

## Feature map: MotoLister → CycleLister

| MotoLister capability | CycleLister status | Notes |
|---|---|---|
| Part-number → generated listing | ✅ Phase 1 built | Pipeline: photo → AI ident (incl. part-number OCR) → catalog match → generate → review (`backend/app/services/pipeline.py`) |
| Pre-loaded parts catalog | ✅ Phase 1 built | `parts` table seeded from seller's own export (`backend/scripts/import_listings.py`) — seller-specific, richer than generic |
| Compatibility chart in listing | ✅ Phase 1 built (partial) | `fitment` table + AI suggestions + confirm UI (`FitmentSection.jsx`); chart rendering in the published description should be checked against MotoLister's buyer-facing chart |
| OEM fitment catalog (licensed, all powersports) | ❌ not planned | CycleLister builds fitment from seller history + AI, no licensed OEM database; spec §9.1 calls the seller's own data the moat. Risk: cold-start coverage for never-sold parts |
| User-editable fitment (add vehicle/MPN) | ✅ Phase 1 built | `PUT /parts/{id}/fitment` (`backend/app/routes/misc.py`) |
| Smart Titles (fitment-driven, format by model count) | ✅ Phase 1 built | AI title generation; spec explicitly targets non-keyword-stuffed titles. Adaptive many-model truncation worth borrowing as a prompt rule |
| Search/scan by MPN (USB barcode scanner) | 💡 new gap | Catalog part search exists (`GET /parts/search`) but no scan-to-listing entry point |
| Live photo upload (tethered camera) | ✅ Phase 1 built (different form) | PWA camera capture (`CaptureScreen.jsx`) replaces desktop camera-tether hardware |
| Photo editor (auto-crop square, brightness/contrast, white-background wand) | 💡 new gap | Schema reserves `processed_path` for background-removed variants; no editing implemented; spec §17 leaves background removal as an open question |
| Video in listings | ❌ not planned | Manual HTML workaround in MotoLister too; low value |
| Live price comparison (manual, comps shown) | 🔜 planned Phase 2 | CycleLister goes further: auto undercut 5-10%, floor, `.95` endings, bulk tiers, price explanation |
| Inventory labels (auto-generate + print, Dymo) | 💡 new gap | Not in spec at all; client's current workflow presumably depends on these labels to find parts on shelves |
| Inventory tool: stock location per item | 💡 new gap | Spec §12 has backlog/stale/zero-stock but no physical location field |
| Check listings on eBay / stock sync | 🔜 planned Phase 4 | Spec §12 low/zero-stock auto-end |
| Part variations | 💡 new gap (unclear) | Feature exists in MotoLister (details video-only); spec has `quantity` but no eBay variation listings |
| Assembly listing / assembly compatibility | 💡 new gap (unclear) | Probably low priority for NOS single parts; confirm with client whether he ever lists assemblies |
| HTML description templates (editable) | ✅ Phase 1 built (partial) | `templates` table per spec §5; per-category template editing UI is later-phase Settings work |
| Shipping/returns/payment policies | ✅ Phase 1 built (partial) | Policy IDs on `listings`; policy management UI is later-phase |
| Pop-up publish confirmation | ✅ Phase 1 built | Explicit per-listing approval is a spec guardrail (§10) — stronger than MotoLister's disableable pop-up |
| Desktop app | ✅ exceeded | PWA runs desktop + phone + tablet |
| AI identification from photo | ✅ Phase 1 built | MotoLister has nothing comparable |
| Sold history + one-click relist | 🔜 planned Phase 3 | MotoLister has nothing comparable |
| Dashboard / reporting | 🔜 planned Phase 4 | MotoLister has nothing comparable |

## Gaps worth adopting

1. **Inventory label printing + stock location (Phase 4, promote to explicit requirement).** MotoLister auto-generates and prints a shelf label per listing (Dymo 450 / 30256) and tracks stock location. Nothing in PROJECT_SPEC covers this; the client's physical retrieval workflow likely depends on it. Add `stock_location` (and printable label with part number/SKU/location, e.g. QR code) to the inventory service. Losing this at cutover is a regression he will notice immediately.
2. **Barcode-scanner fast path (Phase 1.x — cheap).** MotoLister accepts a USB scanner "enter or scan an OEM part number" to start a listing. NOS parts usually have barcoded OEM labels on the box — a scan is faster and 100%-accurate vs. photo OCR. A keyboard-wedge scanner works in any text input: add a part-number entry box on the capture screen that hits the existing catalog-match path.
3. **Photo auto-crop + cleanup (Phase 2).** MotoLister Pro auto-crops to eBay's square and offers a white-background "magic wand." Spec §17 leaves background removal open; resolve it: at minimum auto-crop/normalize, optionally background cleanup, writing to the already-reserved `listing_images.processed_path`.
4. **Adaptive title format by fitment breadth (Phase 1 prompt tweak).** MotoLister's one good title idea: 1-2 compatible models → put years/models in the title; 6+ models → drop models, keep brand + part type + MPN. Encode this as a rule in the title-generation prompt to avoid both keyword stuffing and misleadingly narrow titles.
5. **Part variations + assemblies (Phase 3/4 — confirm with client first).** Both exist in MotoLister; site details are video-only. Ask the client whether he uses either (multi-color/multi-size variation listings; multi-part assemblies with combined compatibility) before scoping.
6. **Fitment cold-start awareness (Phase 1/2 risk note, not a feature).** MotoLister ships a licensed OEM fitment catalog spanning nine motorcycle brands plus ATV/UTV/PWC/snowmobile. CycleLister's seller-history+AI fitment will be thinner for parts he has never sold; watch `fitment.confidence` rates after import and consider a licensed dataset only if AI fitment underperforms.

## Where CycleLister already exceeds it

- **AI identification from a photo** (part type, part number OCR, condition) — MotoLister requires manual part/vehicle selection or an MPN.
- **Automated pricing rules** (undercut band, floor, `.95`, bulk tiers, explanation) vs. MotoLister's look-at-comps-and-decide.
- **Sold history + one-click relist with retained images** — absent from MotoLister.
- **Cross-platform PWA** (phone/tablet/desktop, camera built in) vs. Windows-only desktop + ~$500 of tethered hardware.
- **Modern titles/descriptions** via AI generation instead of fitment-string concatenation.
- **Dashboard/reporting and stale-listing detection** (Phase 4) — no equivalent.
- **No per-listing fees**: MotoLister costs $10/mo + per-listing fees (cap $200/mo) + $50/mo Pro; at the client's 500-1,000 listings/week he'd be at the cap, ~$250/mo.
