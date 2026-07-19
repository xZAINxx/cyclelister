# Supabase setup

Project **cyclelister** (`jypizlyeptqpjkyjravp`, us-east-1, free tier) was provisioned on
2026-07-12. Already done:

- ✅ Full §5 schema applied (`initial_schema` migration; `alembic_version` stamped at `0001`)
- ✅ Public storage bucket `listing-images` (public URLs satisfy eBay's image-hosting requirement)
- ✅ `SUPABASE_URL` + anon key in `backend/.env` (anon key is safe to expose; it's the public client key)

## Two values only you can copy (Supabase dashboard, ~2 minutes)

1. **Database password** — dashboard → *Project Settings → Database → Reset database password*.
   Put it into `backend/.env` by uncommenting `DATABASE_URL` (session pooler host, IPv4-safe):

   ```
   DATABASE_URL=postgresql+asyncpg://postgres.jypizlyeptqpjkyjravp:<PASSWORD>@aws-1-us-east-1.pooler.supabase.com:5432/postgres
   ```

2. **service_role key** — dashboard → *Project Settings → API Keys → service_role* →
   paste into `SUPABASE_SERVICE_ROLE_KEY` and flip `STORAGE_BACKEND=supabase`.
   This key stays server-side only (never in the frontend).

## Then seed the hosted catalog (idempotent)

```bash
cd backend
.venv/bin/python scripts/import_listings.py ../data/seed/dscycleconnection-sample.csv
# expected: 454 new parts, 213 fitment rows; re-runs update instead of duplicating
```

## Auth (going live)

1. Frontend: put `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` in `frontend/.env`
   and rebuild — the sign-in gate activates (create the seller's account via its
   sign-up form, then disable public sign-ups in the Supabase dashboard).
2. Backend: set `AUTH_REQUIRED=true`. No JWT secret needed — tokens are verified
   against the project's public JWKS (`SUPABASE_URL` is already configured).
   Setting `SUPABASE_JWT_SECRET` instead selects legacy HS256 verification.
3. Local dev stays friction-free: `AUTH_REQUIRED` defaults to false (dev user).
