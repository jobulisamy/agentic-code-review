# Code Review: User Orders Endpoint

**PR:** Adds endpoint to get user orders with total spend for the account dashboard.
**File:** `src/routes/orders.js`

---

## Summary

The PR adds a `GET /users/:userId/orders` endpoint that fetches all orders for a user, retrieves their line items, and calculates a total spend. The implementation is functional but has several significant issues that should be addressed before merging.

---

## Issues

### Critical

#### 1. N+1 Query Problem

**Lines 14–18** — The most significant performance issue in this PR. For every order returned by the first query, a separate database query is fired to fetch its line items. If a user has 100 orders, this results in 101 database round-trips.

```js
for (const order of orders.rows) {
  const items = await db.query('SELECT * FROM order_items WHERE order_id = $1', [order.id]);
  ordersWithItems.push({ ...order, items: items.rows });
}
```

**Fix:** Use a single JOIN query (or a single `WHERE order_id = ANY(...)` query) to fetch all line items in one round-trip, then group them in application code.

```js
// Fetch orders and items in two queries instead of N+1
const orders = await db.query('SELECT * FROM orders WHERE user_id = $1', [userId]);
const orderIds = orders.rows.map(o => o.id);

const items = await db.query(
  'SELECT * FROM order_items WHERE order_id = ANY($1::int[])',
  [orderIds]
);

// Group items by order_id
const itemsByOrderId = {};
for (const item of items.rows) {
  if (!itemsByOrderId[item.order_id]) itemsByOrderId[item.order_id] = [];
  itemsByOrderId[item.order_id].push(item);
}

const ordersWithItems = orders.rows.map(order => ({
  ...order,
  items: itemsByOrderId[order.id] || [],
}));
```

Alternatively, a single JOIN query can do both in one round-trip.

---

#### 2. No Error Handling

There is no `try/catch` block around any of the `await db.query(...)` calls. If the database is unreachable or a query fails, the promise rejection will be unhandled, and the server will likely crash or hang the request without ever sending a response.

```js
// Current — no error handling
const orders = await db.query('SELECT * FROM orders WHERE user_id = $1', [userId]);
```

**Fix:** Wrap the entire handler body in a `try/catch` and return an appropriate error response.

```js
router.get('/users/:userId/orders', async (req, res) => {
  try {
    // ... logic ...
    res.json({ orders: ordersWithItems, totalSpend: total });
  } catch (err) {
    console.error('Failed to fetch orders for user', userId, err);
    res.status(500).json({ error: 'Internal server error' });
  }
});
```

---

#### 3. Missing Input Validation / Authorization

`userId` is taken directly from `req.params` and interpolated into a query parameter without any validation or authorization check. Two problems:

- **Type/format validation:** No check that `userId` is a valid integer (or UUID, depending on your schema). A malformed value could cause a database error that leaks internal details.
- **Authorization:** There is no check that the authenticated user is allowed to view the requested `userId`'s orders. Any authenticated (or even unauthenticated, if the route has no auth middleware) caller can enumerate any user's order history and total spend by changing the `userId` in the URL.

**Fix:**
1. Validate that `userId` matches the expected format before querying.
2. Confirm the requesting user's identity (e.g., from `req.user`) matches `userId`, or that the requester has an admin role.

---

### Moderate

#### 4. Floating-Point Arithmetic for Currency

```js
total += item.price * item.quantity;
```

If `price` is stored as a JavaScript `Number` (floating-point), this will accumulate rounding errors. For example, `0.1 + 0.2 !== 0.3` in IEEE 754 arithmetic.

**Fix:** Store and transmit monetary values in integer cents, or use a decimal library (e.g., `decimal.js`) for arithmetic. Return the value to the client in a consistent format (e.g., cents as an integer, or a string representation of the decimal).

---

#### 5. `SELECT *` in Both Queries

Both queries use `SELECT *`, which:
- Fetches columns that may not be needed (wasted bandwidth and memory).
- Makes the API contract implicit — adding or removing a column in the database silently changes the API response shape.

**Fix:** Explicitly list the columns needed by the endpoint.

---

### Minor

#### 6. No Handling for Non-Existent User

If `userId` does not exist in the database, the endpoint returns `{ orders: [], totalSpend: 0 }` with a `200 OK`. Depending on your API conventions, this may be acceptable, but it's worth considering whether a `404` should be returned when the user is not found.

#### 7. No Pagination

Fetching all orders for a user with no limit or offset will not scale. A user with thousands of orders will cause large payloads and slow queries. Consider adding `LIMIT`/`OFFSET` or cursor-based pagination, especially since this is described as powering an account dashboard.

---

## Positive Notes

- The route is correctly mounted under a meaningful, RESTful path (`/users/:userId/orders`).
- The use of parameterized queries (`$1`) for `userId` prevents SQL injection.
- The logic for accumulating total spend is straightforward and easy to follow.

---

## Verdict

**Request changes.** The N+1 query problem and missing error handling are blockers. The authorization gap is a security concern that must be addressed before this ships to production. The floating-point currency issue should also be fixed to avoid subtle financial calculation bugs.
