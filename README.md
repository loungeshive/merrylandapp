# Merryland Digital Dining & Rewards

An incremental monorepo for Merryland Restaurant & Bar. This first implementation establishes a shared API foundation and a connected customer workflow; it is not yet a production-ready payment or administration system.

## Architecture

```text
Expo Android app ─┐
                  ├── HTTPS REST API (FastAPI) ── SQLAlchemy ── Neon PostgreSQL
Next.js web app ──┘
                                                       └──────── Daraja integration (planned)
```

The API owns pricing, order state, payment state, and all loyalty calculations. Clients never report that a payment succeeded. The initial local payment adapter is explicitly development-only; production payment confirmation must be implemented through Daraja callbacks and reconciliation before accepting live payments.

### Data relationships

```text
users 1──1 loyalty_accounts 1──* loyalty_transactions
  │
  ├──* orders 1──* order_items *──1 menu_items *──1 categories
  │      └──1 payments
  └──* redemptions *──1 rewards
```

Order items preserve the product name and price at checkout. Payment provider references and loyalty idempotency keys are unique. KES amounts are stored as integer minor units; points are integer ledger entries, and a balance is derived from the ledger. PostgreSQL transactions and row locking are required for production redemption and reconciliation paths.

### Repository structure

```text
merrlandfolder/
  apps/
    mobile/                    Expo + React Native customer app
    web/
      app/                     Next.js routes, root layout, manifest and global styles
      src/
        components/            Shared authentication and PWA UI
        features/
          admin/                Admin dashboard
          customer/             Customer menu, ordering and account experience
  backend/
    app/
      api/                     FastAPI routes and request/response schemas
      core/                    Settings, security and Google authentication
      db/                      SQLAlchemy session and ORM models
      main.py                  Stable ASGI entry point (app.main:app)
    alembic/                   Database migrations
    tests/
  docs/
  .env.example                 Environment variable template (no secrets)
```

Legacy backend imports such as `app.models` and `app.database` remain as small compatibility modules; new backend code should import from `app.db`, `app.core`, or `app.api` directly.

### Development plan

1. Foundation: monorepo, API configuration, database schema/migration, health endpoint, and responsive design direction.
2. Customer workflow: authentication, live menu, cart/checkout, order history, and mobile client.
3. Payments: Daraja STK Push/callback validation, reconciliation, and refund handling.
4. Operations: expanded staff RBAC, audited order management, and production monitoring.
5. Release: automated integration tests, production configuration, deployment, Android builds, monitoring, backups, and operational runbooks.

## Run the API locally

From `merrlandfolder/backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item ..\.env.example .env
# Edit the root .env and set DATABASE_URL to your Neon PostgreSQL connection string.
uvicorn app.main:app --reload
```

Use the Neon connection string with the `postgresql+psycopg://` scheme and `sslmode=require`. Keep it only in the root `.env` file or deployment secret store; never put it in either frontend environment or commit it. Run `alembic upgrade head` from `backend` to apply the schema to Neon. Open `http://127.0.0.1:8000/docs`; the API creates the menu category choices, while products are managed in the admin dashboard. For the web app, set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1` in `apps/web/.env.local`; for Expo set `EXPO_PUBLIC_API_URL` in the app environment. Android Emulator reaches the host API at `http://10.0.2.2:8000`.

## Menu administration

Set `ADMIN_USERNAME` and a unique `ADMIN_PASSWORD` in the root `.env`; these credentials are separate from customer accounts and are never exposed to the web client. The admin dashboard is available directly at `/admin` and is not linked from the customer homepage. Use it to post, update, hide, or restore products in the Food, Drinks, and Bites categories. A marked price is optional and must be greater than or equal to the selling price. The customer menu's “Under KSh 500” filter uses the selling price. Admin image uploads accept JPG, PNG, or WebP files up to 5 MB and are stored in `backend/uploads/`; configure persistent storage before using local uploads in production. Customers must sign in to rate a product, and each customer's latest rating is included in the displayed average.

The menu no longer inserts demo products automatically. Apply the Alembic migrations before starting against an existing database; the managed-menu migration hides the original seeded demo dishes while preserving their order history.

The application requires Neon PostgreSQL at runtime (`DATABASE_URL=postgresql+psycopg://...`). SQLite is used only by the isolated automated tests; it is rejected for development and production app runs.

The existing `backend/merryland.db` SQLite file is not copied to Neon automatically. Export/import any local data that needs to be retained before switching deployments.

## Install the web app

The web app includes a PWA manifest, app icon, and service worker. Deploy it over HTTPS for supported browsers to offer installation. When the browser reports that installation is available, Merryland displays an install banner; the customer taps **Install** to open the browser's native confirmation. iPhone and iPad users see instructions to use Safari's Share menu and choose **Add to Home Screen**, because iOS does not expose the same automatic install prompt. Browsers control native prompt eligibility and do not allow websites to force it to appear.

## Loyalty and VIP

The customer account includes an editable profile (name, phone, profile photo, and delivery address), a rewards dashboard, QR-based reward reservations, a VIP membership card, weekly VIP benefit claims, and a points/order history. Email is read-only until email verification is implemented. The `/admin` dashboard has a separate authenticated Loyalty & VIP area for managing earning rules and rewards, searching members, viewing order/ledger activity, suspending or reinstating loyalty accounts, recording reasoned point adjustments, verifying codes, exporting member data, and reviewing the audit log.

The default rules award 5 standard points when eligible menu items in one successfully paid order total **more than KSh 200**, and 10 VIP points when they total **more than KSh 1,000**. Both awards may apply to one order. VIP membership is permanent after 100 lifetime VIP points have been earned. Eligible items are determined from their order-time snapshot; marked prices, delivery fees, and other charges are not included. A VIP member may claim one complimentary nyama-choma portion per configured calendar week during administrator-configured days and hours in the configured time zone. Reward reservations hold points until staff verify the code; unredeemed reservations can be cancelled by the customer.

Apply Alembic migration `0004_loyalty_system` after configuring the intended Neon database. Payment simulation is development-only and cannot support live loyalty awards; real Daraja payment verification, refunds/reversals, and staff order-completion workflows are not implemented yet. Do not treat a client-side or simulated payment result as production payment verification.

## Google sign-in setup

Google sign-in requires OAuth client IDs from a Google Cloud project. Configure the OAuth consent screen, then create:

- A **Web application** client with the web app's deployed origin in Authorized JavaScript origins.
- An **Android** client for package `com.merryland.dining`, using the SHA-1 certificate fingerprint for the development or release signing key.
- An **iOS** client if building for iOS.

Copy `apps/web/.env.example` to `apps/web/.env.local` and set `NEXT_PUBLIC_GOOGLE_CLIENT_ID` to the Web client ID. The API's `GOOGLE_CLIENT_IDS` setting in the root `.env` must contain the Web client ID. Client IDs are not secrets; do not add OAuth client secrets to frontend configuration.

Run `alembic upgrade head` from `backend` after configuring the database to add the Google subject field and allow Google-only accounts. The API validates Google ID tokens and only links an existing account when Google reports a verified matching email.

Mobile currently uses email/password authentication so it can run in Expo Go without a custom native build. Google sign-in remains available on the web; the native Google Sign-In module is intentionally not included in the Expo app.

## Run the mobile app

From `merrlandfolder/apps/mobile`:

```powershell
npm install
npx expo start
```

Scan the displayed QR code with Expo Go. The default API URL targets the Android Emulator (`http://10.0.2.2:8000/api/v1`). For a physical device, set `EXPO_PUBLIC_API_URL` to the computer's reachable LAN address and start the API bound to `0.0.0.0`.

## Current implementation boundary

The connected workflow supports customer registration/login, menu retrieval and administration, order creation, development-only simulated payment confirmation, loyalty earning/redemption, VIP benefits, and loyalty administration. The demo payment endpoint returns an error when `APP_ENV=production`; it is not a substitute for Safaricom Daraja. Real payment callbacks, refund reversals, production-grade refresh-token rotation, and expanded staff roles remain future work.