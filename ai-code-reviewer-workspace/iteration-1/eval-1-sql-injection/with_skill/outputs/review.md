# PR Review: New User Login Endpoint (`api/auth.py`)

> Note: No PR description was provided. This makes it harder to understand the intended scope, rollout plan, or any known trade-offs. Please add a description before merging — this is an authentication flow and context matters.

---

## Inline Comments

---

**File: api/auth.py  Line: 17**
**[SECURITY][error] SQL injection via unsanitized `username` and `password` in login query**

The `username` value is interpolated directly into a raw SQL string:

```python
query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{hashlib.md5(password.encode()).hexdigest()}'"
cursor.execute(query)
```

An attacker can pass `' OR '1'='1' --` as the username to bypass authentication entirely and log in as any user. This is a textbook SQL injection vulnerability in an auth endpoint — this is as serious as it gets.

Fix: Use parameterized queries:
```python
query = "SELECT * FROM users WHERE username = ? AND password = ?"
cursor.execute(query, (username, hashlib.md5(password.encode()).hexdigest()))
```
(Also see the MD5 issue below — you'll want to fix both together.)

---

**File: api/auth.py  Line: 37**
**[SECURITY][error] SQL injection via unsanitized `username`, `password`, and `email` in register query**

Same problem in the registration route:

```python
cursor.execute(f"INSERT INTO users (username, password, email) VALUES ('{username}', '{hashed}', '{email}')")
```

An attacker can inject arbitrary SQL through any of the three fields. For example, passing `', '', ''); DROP TABLE users; --` as the email would drop the users table.

Fix: Use parameterized queries:
```python
cursor.execute(
    "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
    (username, hashed, email)
)
```

---

**File: api/auth.py  Lines: 17, 35**
**[SECURITY][error] MD5 used for password hashing — cryptographically broken**

MD5 is not a password hashing algorithm. It is:
- Extremely fast, making brute-force and rainbow table attacks trivial
- Not salted here, meaning identical passwords produce identical hashes (enabling precomputed attacks)
- Considered broken for cryptographic use since the early 2000s

A database breach exposes every user's real password in seconds with GPU-based cracking tools.

Fix: Use `bcrypt`, `argon2-cffi`, or at minimum `hashlib.scrypt` / `hashlib.pbkdf2_hmac` with a random salt:
```python
import bcrypt

# Hashing (registration)
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# Verification (login)
if bcrypt.checkpw(password.encode(), stored_hash):
    ...
```

---

**File: api/auth.py  Lines: 12-13**
**[BUG][error] No input validation — `request.json` can be `None`, crashing the server**

If the request body is not valid JSON (or the `Content-Type` header is wrong), `request.json` returns `None`, and `.get('username')` will throw `AttributeError: 'NoneType' object has no attribute 'get'`. The same issue exists in `register()`.

Additionally, if `username` or `password` are missing from the JSON body, they will be `None`, and `password.encode()` will throw `AttributeError: 'NoneType' object has no attribute 'encode'` — a crash that produces a 500 error and leaks a stack trace.

Fix: Validate inputs explicitly before use:
```python
data = request.get_json(silent=True)
if not data:
    return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

username = data.get('username')
password = data.get('password')

if not username or not password:
    return jsonify({'status': 'error', 'message': 'Username and password are required'}), 400
```

---

**File: api/auth.py  Line: 23**
**[SECURITY][warning] Login response leaks `user_id` — potential IDOR surface**

Returning `user[0]` (the raw database primary key) in the login response exposes internal IDs. If any downstream endpoint uses this ID without proper authorization checks, it enables Insecure Direct Object Reference (IDOR) attacks.

Fix: Return a signed session token or JWT instead of a raw database ID. If you must return an identifier, use an opaque token that cannot be guessed or enumerated.

---

**File: api/auth.py  Lines: 14-15, 32-33**
**[BUG][warning] Database connections not closed on error paths**

If an exception is thrown between `conn = sqlite3.connect(...)` and `conn.close()`, the connection leaks. Under SQLite this is less immediately harmful than in connection-pool databases, but it is still incorrect resource management.

Fix: Use a context manager:
```python
with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    user = cursor.fetchone()
# connection is closed automatically
```

---

**File: api/auth.py  Lines: 26-27**
**[SECURITY][warning] Authentication timing is not constant — timing oracle on username existence**

The `SELECT` query short-circuits: if the username does not exist, the DB returns no rows instantly. If it does exist but the password is wrong, the query may take slightly longer. This timing difference can allow an attacker to enumerate valid usernames.

Fix: Once you switch to bcrypt (see above), always run `bcrypt.checkpw` regardless of whether the user was found, to keep the response time constant. Also, keep the error message generic (which you already do — good).

---

**File: api/auth.py  Lines: 38-40**
**[BUG][warning] `register()` does not handle duplicate usernames**

If a username already exists and the column has a `UNIQUE` constraint, `cursor.execute(...)` will raise `sqlite3.IntegrityError`, which is unhandled and will return a 500. If there is no constraint, duplicate accounts are silently created.

Fix: Catch `sqlite3.IntegrityError` and return a 409 Conflict response:
```python
try:
    cursor.execute(...)
    conn.commit()
except sqlite3.IntegrityError:
    return jsonify({'status': 'error', 'message': 'Username already exists'}), 409
```

---

**File: api/auth.py  Lines: 7**
**[SECURITY][warning] Hardcoded database path**

`DB_PATH = '/app/users.db'` is a hardcoded absolute path. This is not a secret, but hard-coding infrastructure paths makes the app environment-specific and fragile.

Fix: Read from an environment variable with a sensible default:
```python
import os
DB_PATH = os.environ.get('DB_PATH', '/app/users.db')
```

---

**File: api/auth.py  Lines: 41-42**
**[TEST COVERAGE][info] No tests present for any of the new code paths**

There are no tests for the `/login` or `/register` endpoints. Given this is an authentication flow — the security boundary for the entire application — tests are especially important. At minimum, cover:
- Successful login
- Login with wrong password
- Login with non-existent username
- Registration with a new user
- Registration with a duplicate username
- Missing/malformed request body for both endpoints

---

## Code Review Summary

**Overall: REQUEST CHANGES**

| Category       | Errors | Warnings | Info |
|----------------|--------|----------|------|
| Bugs           | 1      | 2        | 0    |
| Security       | 3      | 3        | 0    |
| Performance    | 0      | 0        | 0    |
| Code Quality   | 0      | 1        | 0    |
| Test Coverage  | 0      | 0        | 1    |
| **Total**      | **4**  | **6**    | **1**|

---

### Critical Issues (must fix before merge)

1. **SQL injection in `/login`** — `api/auth.py:17` — raw f-string interpolation into SQL; trivially exploitable to bypass authentication
2. **SQL injection in `/register`** — `api/auth.py:37` — same pattern; can destroy data or exfiltrate records
3. **MD5 password hashing** — `api/auth.py:17,35` — passwords are effectively stored in plaintext equivalent; any DB breach exposes all user credentials
4. **No input validation / None crash** — `api/auth.py:12-13` — malformed requests crash the server with a 500 and a stack trace

### Recommended Fixes (should address)

5. **Timing oracle on username enumeration** — `api/auth.py:26-27` — use constant-time comparison after switching to bcrypt
6. **Unhandled duplicate username on register** — `api/auth.py:38-40` — `sqlite3.IntegrityError` produces a 500 instead of a 409
7. **Unclosed DB connections on exceptions** — `api/auth.py:14-15,32-33` — use `with` context manager
8. **`user_id` leaked in login response** — `api/auth.py:23` — raw DB primary key in response is an IDOR risk
9. **Hardcoded `DB_PATH`** — `api/auth.py:7` — should come from environment config

### Suggestions (optional improvements)

10. **Add tests** — no test coverage for either endpoint; critical for an auth flow

---

### What's Good

- The error message on failed login (`"Invalid credentials"`) is correctly generic — it does not reveal whether the username or password was wrong. This is the right call for preventing username enumeration via the response body.
- The endpoint structure (separate `/login` and `/register`) is clean and correctly uses `POST` for both.
- `conn.close()` is called on the happy path, showing awareness of connection management — just needs to be made robust against exceptions too.

---

**Bottom line:** Do not merge this. There are four `error`-severity issues, two of which (SQL injection and MD5 passwords) are critical security vulnerabilities that would be exploitable immediately in production. Switch to parameterized queries and a proper password hashing library (bcrypt or argon2) as the minimum bar before this ships.
