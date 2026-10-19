# API overview

Base path: `/api/v1`. FastAPI OpenAPI UI is available at `/docs`.

## Implemented in the first vertical slice

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | No | Process health |
| POST | `/api/v1/auth/register` | No | Create a customer and return a bearer access token |
| POST | `/api/v1/auth/login` | No | Authenticate and return a bearer access token |
| GET | `/api/v1/auth/me` | Customer | Return the current customer profile |
| PATCH | `/api/v1/auth/me` | Customer | Update name, phone number, and delivery address; email remains read-only |
| POST | `/api/v1/auth/me/photo` | Customer | Upload or replace a JPG, PNG, or WebP profile photo (maximum 5 MB) |
| DELETE | `/api/v1/auth/me/photo` | Customer | Remove the current profile photo |
| GET | `/api/v1/menu` | No | List active, available menu items |
| POST | `/api/v1/orders` | Customer | Price and create a pending-payment order |
| GET | `/api/v1/orders` | Customer | List the caller's latest orders |
| POST | `/api/v1/payments/{payment_id}/simulate-success` | Customer, development only | Simulate verified payment; returns 404 in production |
| GET | `/api/v1/loyalty/balance` | Customer | Return standard ledger-derived points balance and transactions |
| GET | `/api/v1/loyalty/dashboard` | Customer | Return customer profile, standard/VIP balances, rewards, claims, orders, and ledger activity |
| POST | `/api/v1/loyalty/rewards/{reward_id}/redeem` | Customer | Reserve points and issue a reward verification code |
| POST | `/api/v1/loyalty/redemptions/{redemption_id}/cancel` | Customer | Cancel a pending reservation |
| POST | `/api/v1/loyalty/vip/weekend/claim` | Customer | Issue the eligible weekly VIP benefit code |

All order totals are recalculated by the API from the current menu prices. Money fields are KES cents (`price_minor`); for example, `85000` is KSh 850.00. Points use eligible order-line selling prices from immutable order snapshots. By default, a paid order earns 5 standard points when eligible spend is strictly greater than KSh 200 and 10 VIP points when eligible spend is strictly greater than KSh 1,000; both tracks can earn on the same order. VIP qualification is permanent at 100 lifetime VIP points. Administrators can configure these rules and the one-per-week complimentary VIP benefit schedule.

Customer profile updates only affect the authenticated account. Phone numbers must remain unique across accounts. Email address changes are not supported because email verification is not currently available. Profile photos use the same configured upload storage as menu images.

## Administrator loyalty endpoints

All administrator endpoints require the separate admin bearer token.

| Method | Path | Purpose |
| --- | --- | --- |
| GET / PUT | `/api/v1/admin/loyalty/settings` | Read/update earning thresholds and VIP schedule |
| GET / POST | `/api/v1/admin/loyalty/rewards` | List/create customer rewards |
| PUT / DELETE | `/api/v1/admin/loyalty/rewards/{reward_id}` | Update or hide a reward |
| GET | `/api/v1/admin/loyalty/members?search=...` | List/search all customer accounts, contact/profile details, and point balances |
| GET | `/api/v1/admin/loyalty/members/{customer_id}/activity` | Review paid orders and ledger activity |
| POST | `/api/v1/admin/loyalty/members/{customer_id}/adjustments` | Record an audited, reasoned points adjustment |
| PATCH | `/api/v1/admin/loyalty/members/{customer_id}/suspension` | Suspend or reinstate the loyalty account |
| POST | `/api/v1/admin/loyalty/verify` | Verify a reward, VIP benefit, or VIP membership code |
| GET | `/api/v1/admin/loyalty/redemptions` | List reward and VIP benefit claims |
| GET | `/api/v1/admin/loyalty/analytics` | Read loyalty summary metrics |
| GET | `/api/v1/admin/loyalty/audit-logs` | Review administrator audit history |
| GET | `/api/v1/admin/loyalty/export` | Download CSV member report |

Tax, discounts, tips, modifiers, refunds, and refund point reversals are not implemented. Payment simulation is development-only and returns an error in production; Daraja STK push, callback verification, and reconciliation remain future work. Do not treat client-side or simulated payment results as live payment verification.
