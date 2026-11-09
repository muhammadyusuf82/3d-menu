# Sizzle — LAN React Restaurant Platform: Design Spec

Date: 2026-11-01 · Status: approved in conversation, pending written-spec review

## 1. Goal
Convert the single-file `index.html` prototype (client menu with 3D meals, waiter console, admin dashboard, EN/UZ) into a React project that runs on a restaurant's **local network**: client tablets, waiter devices and the admin PC share live data through one server PC. Then add HD 3D mode, waiter table/order control, an admin events system, and a new category set.

Non-goals (for now): payments, kitchen ticket printing, internet-facing security, Russian language.

## 2. Architecture
- Monorepo: `server/` (Node 20+, Express, `ws`, `better-sqlite3`) and `web/` (React 18 + Vite + TypeScript), plus `shared/` (types and the pricing/events engine used by both).
- Server is the single source of truth. Clients send commands over REST; the server validates, persists, then broadcasts change events over WebSocket. A (re)connecting client receives a full snapshot.
- Fully offline: three.js and fonts are bundled locally; no CDN requests at runtime.
- `npm run build && npm start` serves the built web app and API on port 3000 and prints the LAN URL (`http://<pc-ip>:3000`).
- Auth: PINs are stored hashed on the server; login returns a session token with a role (`waiter` | `admin`). Clients (customers) need no login. Permissions are enforced server-side.

## 3. Data model (SQLite)
- `categories(id, parent_id, name_en, name_uz, icon, sort)` — drinks have sub-categories Hot / Cold / Coffee.
- `meals(id, category_id, price_uzs, prep_min, kcal, name_en, name_uz, tag_en, tag_uz, desc_en, desc_uz, ingredients_json, model_key, photo_path, available)`
- `tables(number, status)` — `free | occupied | needs_bill`; 12 seeded, count configurable by admin.
- `orders(id, number, table_no, source, staff_id, status, subtotal, discount, total, note, created_at, updated_at)`; status `new → preparing → ready → served`, plus `cancelled` (with reason).
- `order_items(order_id, meal_id, name_snapshot, qty, unit_price, discount, event_id)`
- `events(id, title_en, title_uz, type, params_json, target_meals_json, target_categories_json, schedule_json, banner_path, active, created_at)`
- `staff(id, name, role, pin_hash)`

Prices move from USD to **UZS** with thousands separator (e.g. 9.5 → 95 000). Money is stored as integer so'm.

## 4. Events and pricing engine (`shared/pricing`)
Pure functions, computed authoritatively on the server at order time; clients use the same module for live preview.
- Types: `percent` (percentage off), `bogo` / `buy_x_get_y` (buy X, get Y free; the cheapest eligible items in each group are free), optional `fixed_off`.
- Targets: specific meals and/or whole categories.
- Schedule: active flag, date range, weekdays, time window (local server time).
- Conflict rule: per line item the single best discount wins; discounts never stack.
- Seeded events: **Happy Hour** (time window, percent), **Happy Friday** (Fridays), **Buy One Get One**.
- **"Aksiyadagi ovqatlar"** is a virtual category: every meal currently covered by an active event, shown with badge and struck-through old price.
- Admin can create/edit/toggle/delete events, with EN/UZ title and optional banner image upload (stored on server disk, size and type validated).

## 5. Categories and seed menu
Promo meals (virtual) · Fast Food (existing Burgers, Hot Dogs, Wraps) · Sushi · Traditional · Kids · Steak · Dessert · Drinks → Hot, Cold, Coffee. Event banners/filters: Buy One Get One, Happy Hour, Happy Friday. Each new category is seeded with 2–3 meals with realistic ingredients and portions. Admin can add/edit/delete categories and meals.

## 6. 3D viewer and HD mode
- Standard mode: existing models, unchanged behavior.
- HD mode: per-device toggle (persisted locally) — higher-segment geometry, PBR materials, environment lighting, soft shadows, ambient occlusion, MSAA/higher pixel ratio. Auto-fallback to Standard if measured FPS stays below a threshold.
- New categories get procedural models in both Standard and HD versions (code-built, not scanned). Loading supplied `.glb` files is a possible later extension.
- Existing behaviors kept: explode/assemble, auto-spin, ingredient highlight/focus, mini thumbnails, reduced-motion respect, 2D fallback when WebGL is unavailable.

## 7. Waiter panel
- Live tables board (free / occupied / needs bill).
- Take order: choose table, add meals with event discounts previewed, add note, send. Can append to a table's open order.
- Change status of any order (`preparing`, `ready`, `served`), cancel with reason. Admin has the same rights plus management features.
- Live alerts (toast + sound) when orders arrive or become Ready.

## 8. Admin dashboard
Keeps current stats, live orders, pricing/availability, and adds: events manager, menu and category CRUD with photo upload, staff and PIN management, sales stats.

## 9. Frontend structure
React components: `App`, `RoleSwitcher`, `Menu`, `CategoryChips`, `MealCard`, `MealViewer` (three.js wrapper + `HDToggle`), `Cart`, `Checkout`, `WaiterConsole` (`TablesBoard`, `OrderBuilder`, `OrderList`), `AdminDashboard` (`EventsManager`, `MenuManager`, `StaffManager`, `Stats`), `PinGate`, `Toasts`. State via a store fed by the WebSocket (snapshot + events). i18n module (EN, UZ). Visual style carried over from the prototype.

## 10. Error handling
- WebSocket auto-reconnect with backoff; offline banner; actions disabled while disconnected.
- Server validates every command (availability, quantities ≤ 20, table exists, role permission, price recomputed server-side); returns typed errors shown as toasts.
- Order numbers are allocated atomically by the server.

## 11. Testing
- Vitest: pricing/events engine (percent, BOGO, schedule edges, conflict rule, rounding).
- Server integration tests: order lifecycle, permission matrix (client cannot change status; waiter cannot manage events/menu), snapshot/broadcast.
- Component tests for key UI flows; manual verification of the 3D viewer in both modes on a real browser.

## 11a. Implementation notes (where the build differs from the design above)
- Single `package.json` with `server/`, `web/`, `shared/` folders instead of three separate packages.
- Storage uses Node's built-in `node:sqlite` (Node 22.13+) instead of `better-sqlite3`, to avoid native compilation on Windows. Categories, meals and events are stored as JSON documents; order line items are stored as JSON inside the order row (no separate `order_items` table).
- HD mode (revised 2026-11-03): instead of higher-detail procedural models, HD shows photoreal CC0 scans from Poly Haven where one exists (two cakes, croissant, fruit platter composed of separate fruit scans), with environment lighting and soft shadows. Free photoreal scans of burgers, sushi, steak etc. with separable ingredients were not found; free separable models (Kenney) were evaluated and rejected as lower quality than the standard models. Dishes without a scan show the standard model in HD.
- Thumbnails share one WebGL context (rendered to 2D canvases) because browsers cap the number of simultaneous WebGL contexts and the menu has 35 meals.
- Sessions are stored in SQLite and last 12 hours; anonymous orders are rate limited per IP.

## 12. Assumptions
Currency UZS; TypeScript; Node 20+ on the server PC; EN/UZ only; 3D model is the main visual with optional photo; LAN-grade security only.
