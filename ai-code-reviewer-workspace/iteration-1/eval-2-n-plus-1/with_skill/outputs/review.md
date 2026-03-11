# PR Code Review: User Orders Endpoint

**PR Description:** Adds endpoint to get user orders with total spend for the account dashboard.

**File Reviewed:** `src/routes/orders.js`

---

## Inline Findings

---

**File: src/routes/orders.js  Line: 10**
**[SECURITY][error] No authentication or authorization check — any user can fetch any user's orders**

The endpoint accepts `userId` from the URL path and queries the database with it directly, with no check that the requesting user is actually allowed to see that user's data. An authenticated user (or an unauthenticated caller if auth middleware is not enforced globally) can simply change the `userId` in the URL to retrieve every order belonging to any other account. This is a classic Insecure Direct Object Reference (IDOR) vulnerability.

Fix: Before executing the query, verify that the authenticated session/token corresponds to the requested `userId` (or that the caller has an admin role). Example:

```js
if (req.user.id !== userId && !req.user.isAdmin) {
  return res.status(403).json({ error: 'Forbidden' });
}
```

---

**File: src/routes/orders.js  Lines: 9–28**
**[BUGS][error] No try/catch — any database error crashes the request with an unhandled promise rejection**

Every `await db.query(...)` call can throw (connection failure, query error, etc.). There is no `try/catch` wrapping the handler, so a DB error will result in an unhandled promise rejection and the request will hang or crash rather than returning an appropriate error response.

Fix: Wrap the entire handler body in a try/catch:

```js
router.get('/users/:userId/orders', async (req, res) => {
  try {
    // ... existing logic ...
  } catch (err) {
    console.error('Failed to fetch orders for user', userId, err);
    res.status(500).json({ error: 'Internal server error' });
  }
});
```

---

**File: src/routes/orders.js  Lines: 13–17**
**[PERFORMANCE][error] N+1 query pattern — one DB query is issued per order**

The code fetches all orders in a single query, then executes a separate `SELECT * FROM order_items WHERE order_id = $1` query inside a `for` loop for every order. If a user has 100 orders, this makes 101 round-trips to the database. At scale this will cause serious latency and connection pool exhaustion.

Fix: Replace the loop with a single JOIN query that retrieves orders and their items together, or use an `IN` clause to batch the item lookups:

```sql
-- Option A: single JOIN
SELECT o.*, oi.id AS item_id, oi.price, oi.quantity, oi.product_id
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.id
WHERE o.user_id = $1;

-- Option B: two queries — one for orders, one batch fetch for all items
SELECT * FROM order_items WHERE order_id = ANY($1::int[]);
```

Either approach reduces the round-trips to 1–2 regardless of how many orders exist.

---

**File: src/routes/orders.js  Lines: 10**
**[SECURITY][warning] `userId` from URL params is not validated before being used in a query**

Although a parameterized query (`$1`) is used (which prevents SQL injection), `userId` is not validated to be a non-empty string, a valid integer, or within an expected range. Passing a malformed value (e.g., an empty string, a very large number, or a specially crafted value) could trigger unexpected database behavior or expose internal error messages.

Fix: Validate the parameter early:

```js
const userId = parseInt(req.params.userId, 10);
if (!Number.isInteger(userId) || userId <= 0) {
  return res.status(400).json({ error: 'Invalid userId' });
}
```

---

**File: src/routes/orders.js  Lines: 20–25**
**[BUGS][warning] Floating-point arithmetic used for currency — total spend will have rounding errors**

`item.price * item.quantity` uses JavaScript's native floating-point numbers. For monetary values this is unreliable: `0.1 + 0.2 === 0.30000000000000004`. Displaying or storing a `totalSpend` computed this way will produce incorrect values (e.g., $99.999999 instead of $100.00).

Fix: Either store prices as integers (cents) and divide only at the presentation layer, or use a library like `decimal.js` / `big.js` for all monetary arithmetic:

```js
const Decimal = require('decimal.js');
let total = new Decimal(0);
for (const order of ordersWithItems) {
  for (const item of order.items) {
    total = total.plus(new Decimal(item.price).times(item.quantity));
  }
}
res.json({ orders: ordersWithItems, totalSpend: total.toFixed(2) });
```

---

**File: src/routes/orders.js  Lines: 9–28**
**[PERFORMANCE][warning] No pagination — endpoint returns all orders for a user in a single response**

The query `SELECT * FROM orders WHERE user_id = $1` has no `LIMIT`/`OFFSET` or cursor-based pagination. A user with thousands of orders will cause a very large result set to be loaded entirely into memory, serialized, and sent over the wire in a single response. This will cause memory pressure and slow response times.

Fix: Add pagination parameters:

```js
const page = parseInt(req.query.page, 10) || 1;
const pageSize = Math.min(parseInt(req.query.pageSize, 10) || 20, 100);
const offset = (page - 1) * pageSize;

const orders = await db.query(
  'SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3',
  [userId, pageSize, offset]
);
```

---

**File: src/routes/orders.js  Lines: 9–28**
**[TEST COVERAGE][warning] No tests provided for the new endpoint**

The PR adds a meaningful new endpoint with multiple logic paths (empty orders, orders with no items, monetary calculation, DB error) and no tests are included. Edge cases that should be covered include:

- User with no orders → `{ orders: [], totalSpend: 0 }`
- Order with zero-quantity items
- DB failure → 500 response (once error handling is added)
- Unauthorized access attempt (once auth is added)
- Correct total spend calculation with decimal prices

---

**File: src/routes/orders.js  Lines: 9–10**
**[CODE QUALITY][info] `SELECT *` used in both queries — prefer explicit column lists**

Using `SELECT *` couples the API response schema directly to the database table schema. If a column is added to `orders` or `order_items` (e.g., an internal flag or sensitive field), it will automatically be exposed in the API response. Explicitly listing needed columns makes the contract clear and prevents accidental data leakage.

Fix:

```sql
SELECT id, user_id, status, created_at FROM orders WHERE user_id = $1
SELECT id, order_id, product_id, price, quantity FROM order_items WHERE order_id = $1
```

---

## Code Review Summary

**Overall: REQUEST CHANGES**

| Category        | Errors | Warnings | Info |
|-----------------|--------|----------|------|
| Bugs            | 1      | 1        | 0    |
| Security        | 1      | 1        | 0    |
| Performance     | 1      | 1        | 0    |
| Code Quality    | 0      | 0        | 1    |
| Test Coverage   | 0      | 1        | 0    |
| **Total**       | **3**  | **4**    | **1**|

---

### Critical Issues (must fix before merge)

1. **[SECURITY] Missing authorization check** (`src/routes/orders.js` line 10) — any caller can read any user's complete order history. This is an IDOR vulnerability that directly violates user data privacy.
2. **[BUGS] No error handling** (`src/routes/orders.js` lines 9–28) — unhandled promise rejections on any DB failure; the server will crash or hang instead of returning a 500.
3. **[PERFORMANCE] N+1 query pattern** (`src/routes/orders.js` lines 13–17) — one DB query per order row will not scale and will cause latency and connection pool exhaustion under real load.

---

### Recommended Fixes (should address)

- **[SECURITY]** Validate and sanitize `userId` before use (line 10), even though parameterized queries prevent SQL injection.
- **[BUGS]** Switch to integer cents or a decimal library for monetary arithmetic (lines 20–25) to avoid floating-point rounding errors in `totalSpend`.
- **[PERFORMANCE]** Add pagination to the orders query (line 10) to prevent unbounded response sizes.
- **[TEST COVERAGE]** Add unit/integration tests covering happy path, empty results, DB errors, and the authorization check.

---

### Suggestions (optional improvements)

- **[CODE QUALITY]** Replace `SELECT *` with explicit column lists in both queries to make the API contract explicit and prevent accidental exposure of future columns.

---

### What's Good

- **Parameterized queries are used correctly.** Both `db.query` calls pass user input as a bound parameter (`$1`), which correctly prevents SQL injection. This is the right pattern.
- **The response shape is sensible.** Returning `{ orders, totalSpend }` in a single response is a reasonable design for a dashboard use-case and avoids requiring a second round-trip from the client.
