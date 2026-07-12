# PROJECT_SPEC.md — AI-Powered eBay Listing Platform ("CycleLister")

**Purpose of this document:** This is the complete build specification for a custom AI-powered eBay listing platform for a single client, D's Cycle Connection. Feed this file to Claude Code as the source of truth for the project. Every section is written for an engineering agent, not an end user. When in doubt, prefer clarity and explicit contracts over cleverness.

## 1. One-paragraph summary

CycleLister is a web and mobile application that lets a motorcycle-parts eBay seller photograph a physical part and receive a complete, competitively-priced eBay listing draft in under a minute. The system uses AI vision to identify the part and read its part number, looks up which motorcycle models it fits, generates an SEO-optimized title and description, prices the item 5–10% below the lowest current competitor (with a hard floor the seller sets, and prices always ending in `.95`), and publishes to eBay on the seller's approval. It also keeps a permanent archive of every part ever sold so the seller can re-list a recurring part in one click, reusing the original photos. It is, in effect, a modern replacement for the seller's current desktop tool (MotoLister), tailored to a New Old Stock (NOS) parts business.

## 2. The client and the domain (context the agent must understand)

* Client: D's Cycle Connection, a long-running eBay motorcycle-parts store (24+ years, 250K+ lifetime sales, Top Rated Seller). Sells primarily NOS (New Old Stock) parts — original-manufacturer parts, often decades old, for Yamaha, Honda, Suzuki, Kawasaki, and Harley-Davidson.
* Volume: ~42,000 active listings today, with a large unlisted physical backlog. Target throughput after launch: 500–1,000 new listings per week.
* Current tool being replaced: MotoLister (desktop-only). Its useful behaviors to match or beat: part-number → auto-generated listing with compatibility chart, saved per-category templates (shipping/returns/payment), quick photo upload, comparable-price lookup. Its weaknesses to fix: desktop-only, dated UI, keyword-stuffed titles, weak multi-model fitment, no AI identification from a photo, no sold-history/relist workflow.
* Pricing conventions that are non-negotiable business rules:
  * Undercut the lowest legitimate competitor by 5–10% (configurable within that band).
  * Never price below a per-item or per-category floor the seller sets (protect margin).
  * All prices end in `.95` (e.g., a computed $13.72 becomes $13.95 — round to nearest sensible `.95`, see §7.3).
  * Respect existing bulk/quantity discount tiers.

## 3. Core user (persona) and primary job-to-be-done

User: The seller (and, later, 1–2 assistants). Non-technical. Works partly at a desk and partly on the shop floor with a phone or tablet. Wants speed and trust: he will review every listing before it goes live, at least until he trusts the system.

Primary job: "Turn a physical part in my hand into a live, competitively-priced eBay listing as fast as possible, without re-typing things I've typed a thousand times."

Secondary jobs:

* "When a part I've sold before comes through again, re-list it instantly using the photos I already have."
* "Tell me what's sitting unsold too long so I can act on it."
* "Show me, simply, how the business is doing this week."

## 4. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                          │
│  React + Vite PWA (installable on phone/tablet/desktop)      │
│  - Capture screen (camera)      - Review/edit listing        │
│  - Inventory browser            - Sold history / relist      │
│  - Dashboard                    - Settings (rules/templates) │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS / JSON (REST)
┌───────────────────────────┴─────────────────────────────────┐
│                       BACKEND LAYER                          │
│  FastAPI (Python)                                            │
│  - Auth & sessions              - Listing orchestration      │
│  - AI service (Claude)          - Pricing engine             │
│  - Fitment lookup               - eBay integration           │
│  - Inventory service            - Job queue (async)          │
└──────┬───────────────┬───────────────┬──────────────┬───────┘
       │               │               │              │
┌──────┴─────┐  ┌───────┴──────┐  ┌─────┴──────┐  ┌────┴───────┐
│ PostgreSQL │  │ Object store │  │ Claude API │  │  eBay APIs │
│ (Supabase) │  │ (images)     │  │ (vision +  │  │ (Sell,     │
│            │  │              │  │  text)     │  │  Browse)   │
└────────────┘  └──────────────┘  └────────────┘  └────────────┘
```

Why this stack:

* React + Vite as a PWA gives one codebase across phone, tablet, and desktop, installable to the home screen, with camera access — no separate iOS/Android app needed for v1. (Native wrapper via Capacitor is a later option if push notifications or app-store presence are wanted.)
* FastAPI for the backend: async-friendly (important because each listing fans out to several slow external calls), clean typing with Pydantic, easy to expose a REST contract the frontend consumes.
* PostgreSQL via Supabase for relational data (parts, listings, sales history, rules) plus Supabase Storage (or S3-compatible) for images. Supabase also gives auth out of the box.
* Claude API for vision (part identification, OCR of part numbers, condition assessment) and text (title/description generation, fitment reasoning).

## 5. Data model (initial schema)

Tables (Postgres). Types are indicative; refine during implementation. All tables get `id uuid pk default gen_random_uuid()`, `created_at timestamptz default now()`, `updated_at timestamptz`.

### `users`

Seller and assistants. `email`, `display_name`, `role` (`owner` | `assistant`), auth handled by Supabase Auth.

### `parts`

The canonical record for a physical/known part. This is the seller's growing proprietary catalog — his moat.

* `part_number text` (OEM part number, normalized — uppercase, stripped of spaces/dashes for matching; keep a `part_number_display` for the pretty version)
* `brand text` (Yamaha, Honda, etc.)
* `part_type text` (carburetor, brake lever, CDI, fairing, …)
* `title_template text` (last good title, reusable)
* `description_template text`
* `default_category_id text` (eBay category)
* `item_specifics jsonb` (MPN, Brand, Type, etc.)
* `notes text`
* `source text` (`ai_generated` | `imported` | `manual`)

### `fitment`

Which bikes a part fits. Many rows per part.

* `part_id fk → parts`
* `make text`, `model text`, `year_start int`, `year_end int`
* `confidence numeric` (0–1; AI-suggested fitment starts lower until confirmed)
* `confirmed boolean default false`

### `listings`

A specific eBay listing (draft or live).

* `part_id fk → parts` (nullable until identified)
* `status text` (`draft` | `pending_review` | `listed` | `ended` | `sold` | `error`)
* `ebay_listing_id text` (once published)
* `title text`, `description text`
* `price numeric`, `price_floor numeric`, `computed_competitor_price numeric`, `undercut_pct numeric`
* `quantity int`
* `category_id text`
* `item_specifics jsonb`
* `shipping_policy_id text`, `return_policy_id text`, `payment_policy_id text`
* `condition text`, `condition_notes text`
* `ai_confidence numeric` (overall identification confidence)
* `needs_human_review boolean`

### `listing_images`

* `listing_id fk`, `part_id fk` (denormalized for relist reuse)
* `storage_path text`, `is_primary boolean`, `order_index int`
* `processed_path text` (e.g., background-removed variant, if any)

### `sales_history`

Immutable archive of every sale. This powers relisting.

* `part_id fk`, `original_listing_id fk`
* `part_number text` (denormalized so history survives part edits)
* `title text`, `description text`, `sold_price numeric`, `sold_date date`
* `image_paths text[]` (references retained images so relist can reuse them)
* `buyer_ref text` (optional/minimal)
* `fitment_snapshot jsonb`

### `pricing_rules`

* `scope text` (`global` | `category` | `part`)
* `scope_ref text` (category id or part id when scoped)
* `undercut_pct_min numeric default 5`, `undercut_pct_max numeric default 10`
* `price_ending text default '.95'`
* `floor_absolute numeric` (nullable)
* `floor_margin_pct numeric` (nullable — floor as % over cost if cost known)
* `free_shipping_threshold numeric` (nullable)

### `templates`

Saved per-category listing templates (mirrors MotoLister's part templates).

* `name text`, `part_type text`
* `shipping_policy_id`, `return_policy_id`, `payment_policy_id`
* `description_boilerplate text`, `item_specifics_defaults jsonb`

### `jobs`

Async work tracking (identification, pricing, publishing, bulk imports).

* `type text`, `status text`, `payload jsonb`, `result jsonb`, `error text`

## 6. The listing pipeline (the heart of the app)

This is the core flow. Implement it as an orchestrated, mostly-async pipeline so the UI can show progressive results.

Input: 1–8 photos of a single part (+ optional seller-typed hint like a part number).

Steps:

1. **Ingest & store images.** Upload to object storage, create a `listings` row with `status = draft`, attach `listing_images`.
2. **AI part identification (Claude vision).** Send the photos to Claude with a structured prompt (see §8.1). Extract:
   * visible part number(s) (OCR from the part or its packaging/label)
   * part type, brand markings
   * condition cues (NOS/new, used, wear, corrosion, packaging present)
   * a confidence score

   Return strict JSON. Low confidence → flag `needs_human_review = true` and surface to the user, don't block.
3. **Catalog match.** Normalize the extracted part number and look it up in `parts`.
   * Hit: reuse the stored `title_template`, `description_template`, `item_specifics`, `default_category_id`, and known `fitment`. This is the fast path and gets better the longer the system runs.
   * Miss: proceed to generate from scratch, and create a new `parts` row as a side effect (so the catalog grows).
4. **Fitment resolution.** Determine which makes/models/years the part fits (see §9). Attach `fitment` rows. Multi-model fitment is common and important for NOS — handle 1→many cleanly.
5. **Pricing (see §7).** Compute the competitor reference price, apply undercut band + floor + `.95` ending, respect bulk tiers.
6. **Listing generation (Claude text).** Produce:
   * Title ≤ 80 chars, natural and search-relevant (NOT keyword-stuffed), front-loading the most important terms (brand, part type, part number, key fitment).
   * Description from the template + AI personalization, incorporating condition notes and fitment.
   * Category (auto-selected; confirm against eBay category tree).
   * Item specifics (MPN, Brand, Type, Manufacturer Part Number, Condition, etc.).
7. **Assemble draft.** Populate the `listings` row fully, set `status = pending_review`.
8. **Human review (UI).** Seller sees the full draft with every field editable, images, price with a visible explanation ("$13.95 — 8% below lowest competitor $15.20"), and fitment as a confirmable list. Edits are saved back and, where appropriate, learned into `parts`/`templates`.
9. **Publish to eBay on approval (see §10).** On success, set `status = listed`, store `ebay_listing_id`.
10. **On sale (webhook/poll).** Move data into `sales_history` with retained images; set listing `status = sold`. This is what makes relisting possible later.

Design rules for the pipeline:

* Every external call (Claude, eBay) is retried with backoff and logged in `jobs`.
* The pipeline is resumable — if step 5 fails, the draft still exists with steps 1–4 done.
* Nothing is auto-published. Human approval is always required in v1.
* Cost-control: cache the static parts of prompts (style guide, rules, examples) via Claude prompt caching; use a cheaper model (Haiku-class) for narrow classification/extraction steps and a stronger model (Sonnet-class) for vision and description writing.

## 7. Pricing engine (precise spec — this is a business-critical module)

### 7.1 Competitor reference price — the hard constraint

Important reality the agent must not get wrong: eBay's old Finding API (`findCompletedItems`) and Shopping API were decommissioned (Feb 2025). True sold-price data now lives behind eBay's Marketplace Insights API, which is access-restricted and requires eBay business approval. Do not build against `findCompletedItems` — it's dead.

Implement pricing with a provider-abstraction layer so the data source can change without touching the rest of the engine:

```
PriceSource (interface)
  get_active_comps(part_number, keywords, category) -> list[Comp]
  get_sold_comps(part_number, keywords, category)   -> list[Comp]   # may be unavailable
```

Concrete providers, in priority order:

1. **eBay Browse API** — available now, returns active listings (current competition). This is the reliable, allowed source for "what are others charging right now," which is exactly what the undercut rule needs. Use this as the primary source.
2. **eBay Marketplace Insights API** — if and when the client's account is granted access, use it for true sold-price history (better signal). Gate behind a feature flag; degrade gracefully if not approved.
3. **Internal history** — the client's own `sales_history` gives real sold prices for parts he's sold before. Use this as a strong signal, especially for recurring NOS parts.

The engine should combine available signals: prefer sold data when present (Insights API or internal history), fall back to active-listing data (Browse API) otherwise. Always record which source was used on the `listings` row for transparency.

Because the seller's rule is literally "go 5–10% below competitors," active-listing data from the Browse API is sufficient and appropriate for the core feature. Sold data is an enhancement, not a blocker.

### 7.2 Undercut logic

```
reference = choose_reference_price(comps)          # e.g., lowest legitimate active competitor,
                                                   # filtering outliers and non-comparable items
undercut  = clamp(config.undercut_pct, 5, 10)      # default 8
target    = reference * (1 - undercut/100)
target    = max(target, floor)                     # never below floor (absolute or margin-based)
price     = round_to_95(target)                    # see 7.3
```

* Outlier filtering: drop comps that are obviously non-comparable (wrong part, bundles/lots when pricing a single, damaged when pricing NOS). Use part-number match + title similarity to keep comps honest.
* Thin/no competition: if fewer than N comparable comps exist, do not undercut blindly. Fall back to internal history or flag `needs_human_review` with a suggested price and a note ("only 1 competitor found; review price"). NOS parts frequently have thin markets — this case is common, not rare.
* Floor: if `target < floor`, set `price = round_to_95(floor)` and flag that the undercut couldn't be honored without losing margin.

### 7.3 `.95` rounding rule

Prices must end in `.95`. Round the computed target to the nearest sensible `.95` value, biased so the result stays at or below the undercut target where possible (never round up past the competitor).

Examples:

* 13.72 → 13.95 is above target; prefer 12.95 (nearest `.95` at/below target). Define: `round_to_95(x)` = largest value of form `k.95` that is ≤ `x`, unless `x < 0.95`, then `0.95`.
* 249.10 → 248.95
* 4.40 → 3.95

Make the rule a single, unit-tested pure function. Confirm the exact bias with the seller during Phase 2 (some sellers prefer nearest, some prefer never-round-up); default to never-round-up.

### 7.4 Bulk / quantity discounts

Respect existing tiered discounts (e.g., "save up to 20% when you buy 2+"). Store tiers per listing/part; apply eBay's Volume Pricing on publish. The undercut logic applies to the base (qty 1) price.

### 7.5 Free-shipping logic

If `free_shipping_threshold` is set and price ≥ threshold, mark free shipping; else attach the appropriate shipping policy. Keep this configurable per category/template.

## 8. AI service (Claude) — prompt contracts

Keep all prompts in a versioned `prompts/` directory. Every AI call returns strict JSON validated by a Pydantic model; on parse failure, retry once with a "return only valid JSON" reminder, then flag for review.

### 8.1 Part identification (vision)

* Input: images (base64), optional seller hint.
* System prompt includes (cache this): the seller's brands, the NOS context, the part-type taxonomy, and a strict output schema.
* Output JSON: `{ part_numbers: [...], part_type, brand, condition: {grade, notes}, visible_text, confidence }`.
* Rule: the model must not invent a part number. If none is legible, return `part_numbers: []` and lower confidence.

### 8.2 Title + description generation (text)

* Input: part record (matched or new), fitment, condition, seller's voice/boilerplate.
* Output JSON: `{ title (<=80 chars), description (html-safe), item_specifics: {...}, suggested_category }`.
* Style rules (cache these): natural modern eBay search style, front-load key terms, NO keyword stuffing, include fitment succinctly, use the seller's stock phrases (e.g., "New Old Stock", "Sold as-is") when applicable, never fabricate compatibility.

### 8.3 Fitment reasoning (text, optional assist)

* Given a part number/type, propose likely make/model/year ranges with confidence, explicitly marking uncertainty. This is an assist, not an authority — see §9. Never present low-confidence fitment as fact in a published listing.

### 8.4 Model routing & cost

* Vision + description → Sonnet-class. Narrow extraction/classification/category-mapping → Haiku-class.
* Enable prompt caching on the large static system content.
* Batch bulk-import identification through the Batch API where latency doesn't matter (overnight backlog processing).
* Target: keep per-listing AI cost in the low single-digit cents; log token usage per `job` for cost reporting.

## 9. Fitment database (the hardest sub-problem — read carefully)

One part often fits many bikes across many years. Getting fitment right is a major ranking and trust lever, and it's where the old tool was weak. There is no free, clean, official OEM fitment API. Approaches, best-first:

1. **Seed from the client's own history.** He has enriched a quarter-million parts with fitment over 24 years. Import his active listings and any MotoLister export to seed `parts` + `fitment`. This is the single most valuable data source and should be Phase-1 groundwork.
2. **eBay catalog / compatibility data.** Where eBay provides a compatible-vehicle list for a catalog product, use it to prefill the fitment multi-select.
3. **AI-assisted suggestion (§8.3)** with explicit confidence, always seller-confirmed before it's treated as authoritative.
4. **Manual override UI** — fast add/edit of make/model/year ranges, because the seller's own knowledge is often the ground truth for NOS.

Do not hard-depend on scraping third-party OEM fiche sites (PartZilla, Babbitts, etc.): it's legally gray and technically fragile. If ever added, isolate it behind the same provider interface and treat it as low-trust suggestion only.

The fitment model must support: a part with 0 fitments (unknown, flagged), 1 fitment, and many fitments; confirmed vs suggested; and year ranges (e.g., fits 1978–1984), not just single years.

## 10. eBay integration

Use the modern RESTful eBay APIs (the Sell APIs), not the deprecated traditional ones.

* **Auth:** OAuth 2.0 (user token via authorization-code grant). The seller creates his own eBay developer keyset and authorizes the app; the app stores and refreshes tokens securely. The app must never handle the seller's eBay password — only OAuth tokens the seller grants.
* **Publishing:** use the Sell Inventory API (create inventory item → create offer → publish offer) and/or the Listing/Trading flow as appropriate for motorcycle-parts categories and item specifics. Attach business policies (fulfillment/payment/return) by policy id.
* **Reading competition:** Browse API for active comps (§7.1).
* **Sold data:** Marketplace Insights API only if access is granted (feature-flagged).
* **Order/sale detection:** poll the Fulfillment/Order API on a schedule (or use eBay notifications if enabled) to detect sales and drive the `sales_history` archival step.
* **Rate limits & resilience:** respect per-API call limits, implement token-bucket throttling, exponential backoff, and idempotent publish (never double-list on retry — key on a client-generated correlation id).
* **Sandbox first:** build and test against eBay's sandbox before touching the production seller account.

Guardrails: publishing is a real, irreversible, money-affecting action. Require explicit seller approval per listing in v1. Never auto-publish, never bulk-publish without a confirmation step showing counts and a sample.

## 11. Sold history & one-click relist (an explicit client ask)

* Every sale writes an immutable `sales_history` row with retained images.
* Relist screen: searchable/filterable by part number, fitment, part type, date, price.
* One-click relist: from a history row, generate a fresh draft that reuses the original images (no re-photographing), re-runs current pricing (market moves), pre-fills title/description/fitment from history, and drops the seller into the standard review screen.
* This is high-value specifically because NOS inventory recurs — the same part type cycles back through the shop repeatedly.
* Image retention: keep sold-listing images in object storage indefinitely (they're the whole point of fast relist). Track storage growth; it's an expected cost.

## 12. Inventory management

* Track physical/unlisted backlog vs. listed vs. sold.
* Bulk intake: photograph/upload a batch (e.g., a container's worth), run identification in the background (Batch API), produce a review queue of drafts. Surface high-value items first.
* Stale-listing detection: flag listings sitting past a threshold (e.g., 90 days) with watchers-but-no-sale signals → suggest price refresh or relist.
* Low/zero stock: auto-end or flag listings when quantity hits zero.

## 13. Dashboard & reporting

Simple, non-technical, at-a-glance:

* Listings created this week/month; sales count and revenue.
* Top categories by volume and by margin.
* Stale-inventory action list.
* Pricing performance (are we winning on price where it matters?).
* A weekly summary emailed automatically. Keep it genuinely simple — the user is non-technical. Charts over tables where possible.

## 14. Non-goals / explicitly out of scope for v1

* Selling on platforms other than eBay (Amazon, Shopify, Facebook Marketplace). Architect so it's possible later, but don't build it.
* Accounting/QuickBooks integration (provide CSV export instead).
* Automated buyer-message answering and returns/dispute drafting (nice-to-have, later phase).
* Native app-store apps (PWA is the v1 target; Capacitor wrapper is a later option).
* Fully automatic (no-human) publishing. Human review stays mandatory in v1.

## 15. Cross-cutting requirements

* **Security:** OAuth tokens and API keys encrypted at rest; never logged. No secrets in the frontend. Least-privilege on storage buckets.
* **Privacy:** store the minimum buyer data needed; don't build features that compile buyer personal data beyond what eBay order fulfillment requires.
* **Cost observability:** log Claude token usage and eBay call counts per job; expose a monthly cost view (this directly informs the retainer).
* **Resilience:** every external dependency (Claude, eBay, storage) can fail; the app degrades gracefully and never loses a draft. Queue + retry, not fire-and-forget.
* **Testing:** unit-test the pure logic hard — `round_to_95`, undercut/floor math, part-number normalization, fitment range handling. Integration-test the eBay publish flow against sandbox. Add a golden-set of ~20–30 known parts with correct expected outputs to measure identification/pricing accuracy over time.
* **Config over code:** pricing bands, `.95` rule, floors, thresholds, and templates live in data/config, editable by the seller in Settings — not hardcoded.
* **Observability:** structured logging, error tracking (e.g., Sentry), uptime monitoring.

## 16. Suggested build order (maps to the client SOW phases)

1. **Phase 1 — Snap & List.** Image capture (PWA camera) → AI identification → catalog match → title/description generation → review screen → publish to eBay (sandbox then production). Groundwork: import the seller's existing listings to seed `parts`/`fitment`. Deliverable: seller can photograph a part and produce a real listing.
2. **Phase 2 — Smart Pricing.** Browse-API comps → undercut/floor/`.95` engine → bulk discounts → price explanation in the review UI. Wire internal-history and (if approved) Insights API as additional price sources. Deliverable: listings are auto-priced per the rules.
3. **Phase 3 — Sold History & Relist.** Sale detection → `sales_history` archival with image retention → searchable history → one-click relist reusing images. Deliverable: recurring parts re-list in one click.
4. **Phase 4 — Inventory & Dashboard.** Backlog/stale tracking, bulk intake via Batch API, dashboard, weekly email. Deliverable: the seller can see and manage the whole operation.

Each phase ends in a working, demoable increment. Nothing in a later phase should break an earlier one.

## 17. Open questions to resolve with the client before/while building

* Exact `.95` rounding preference (never-round-up vs nearest) — default: never-round-up.
* Floor definition: absolute per-part, per-category, or margin-based (needs cost data)?
* Is a MotoLister export available to seed the catalog and fitment? What format?
* Will eBay grant Marketplace Insights access to his account? (Determines sold-data availability.)
* Photo setup: backgrounds/lighting — does the pipeline need background removal, or are shots clean enough?
* Who besides the owner will use it (assistant accounts, permissions)?

---

*End of specification. Treat §6 (pipeline), §7 (pricing), §9 (fitment), and §10 (eBay) as the load-bearing sections; get those contracts right and the rest follows.*
