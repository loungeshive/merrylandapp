# Database schema (initial slice)

All primary keys are UUID strings. Timestamps are UTC. Monetary values are integer KES minor units, not floating point.

| Table | Important fields and relationships |
| --- | --- |
| `users` | Customer identity, unique normalized email and phone, optional profile photo and delivery address, password hash |
| `categories` | Menu grouping and display order |
| `menu_items` | Category FK, selling and optional marked price, image URL, availability and points eligibility |
| `menu_ratings` | One customer rating per menu item, with timestamps; homepage averages are derived from these records |
| `orders` | Customer FK, unique public order number, order state and KES totals |
| `order_items` | Order FK, product FK, immutable product-name, unit-price and points-eligibility snapshot, quantity |
| `payments` | One payment per order, provider, unique provider reference, amount and verification state |
| `loyalty_transactions` | Append-oriented signed standard/VIP points entries; optional order FK, unique idempotency key, and adjustment audit metadata |
| `loyalty_profiles` | Customer VIP membership number, permanent qualification timestamp, and suspension state |
| `loyalty_configuration` | Standard/VIP earning thresholds, redemption threshold, qualification threshold, and weekly benefit schedule |
| `rewards` | Customer reward definition, points cost, linked menu item, conditions, and availability |
| `reward_redemptions` | Customer reward reservation and verification status/code |
| `weekend_benefit_claims` | VIP benefit claim, one per customer and calendar week, with verification status/code |
| `admin_audit_logs` | Administrator actor, action, affected entity, reason, and structured details |

`orders.customer_id`, `menu_items.category_id`, `order_items.order_id`, `order_items.menu_item_id`, `payments.order_id`, and `loyalty_transactions.customer_id/order_id` are foreign keys. Customer/order/status/menu lookup fields are indexed. The balance endpoint sums ledger entries rather than maintaining a separately mutable balance. `menu_items.price_minor` is the selling price; `marked_price_minor` is nullable and, when present, must be at least the selling price. Menu deletion is a soft hide so that historical order references remain valid.

Alembic migration `0003_managed_menu` adds offer pricing, customer ratings, and the Food/Drinks/Bites categories. Migration `0004_loyalty_system` adds configurable loyalty/VIP rules, profiles, audit records, reservations, and weekly claims. Migration `0005_customer_profiles` adds optional customer delivery address and profile photo URL fields. “Under KSh 500” is calculated from the selling price rather than stored as a category.

Admin access uses a separate username/password configured only in the backend environment. Product images are stored in the backend's local `uploads/` directory by default; production deployments must use a persistent volume or replace this with durable object storage. Real payment callback-event and refund/reversal records remain future schema work.
