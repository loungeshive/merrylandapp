# Local and production setup

## Local

1. Install Python dependencies from `backend/requirements.txt`.
2. Copy `.env.example` to `.env` at the repository root; backend settings load this file. Environment variables override file values.
3. Set `DATABASE_URL` to the Neon connection string using the `postgresql+psycopg://` scheme and `sslmode=require`. Keep it in the backend environment or secret store only.
4. From `backend`, apply the schema with `alembic upgrade head` before deploying backend changes that require new tables or columns.
5. Start the API in `backend` with `uvicorn app.main:app --reload`.
6. Start the web app in `apps/web` using `npm install` and `npm run dev`; set `NEXT_PUBLIC_API_URL` to the API base URL ending in `/api/v1`.
7. Start Expo in `apps/mobile`. On Android Emulator, `10.0.2.2` routes to the host machine. Set `EXPO_PUBLIC_API_URL` to the reachable API base URL.

The application requires PostgreSQL for normal runs; file-based SQLite is rejected at startup. Tests use an isolated in-memory SQLite database. Existing local SQLite records are not migrated automatically and must be explicitly exported/imported if needed.

## Remembered customer sessions

Customer access tokens expire after 30 minutes and are renewed using rotating refresh tokens stored in the backend database. Refresh tokens do not expire automatically; they are revoked when the customer signs out. Apply the session-table migration with `alembic upgrade head` from `backend` before deploying the updated API. Sessions created by older API versions may need to sign in once after this migration.

## Production blockers

- Replace the development token secret with a high-entropy managed secret; terminate TLS and restrict CORS to deployed origins.
- Keep `APP_ENV=production` and `DEMO_PAYMENT_ENABLED=false`. The simulated payment endpoint is intentionally unavailable then.
- Implement and test Daraja OAuth/STK Push, callback validation/reconciliation, amount/reference matching, replay/idempotency storage and refund reversal before accepting payments.
- Add rate limiting, staff RBAC and audited administration.
- Apply Alembic migrations, provision backups/restore tests, monitoring, structured logs and retention policy.
- Build/sign the Android app only after production API and secure storage behavior are configured.
