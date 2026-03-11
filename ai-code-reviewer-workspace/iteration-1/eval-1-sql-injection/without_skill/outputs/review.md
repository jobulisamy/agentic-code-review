# Code Review: New User Login Endpoint (`api/auth.py`)

## Summary

This PR adds `/login` and `/register` endpoints to the Flask API. While the basic structure is reasonable, the code has **critical security vulnerabilities** that must be fixed before merging. There are also secondary issues around error handling and code quality.

---

## Critical Issues

### 1. SQL Injection (Severity: Critical)

Both endpoints construct SQL queries using f-strings with unsanitized user input:

```python
# login()
query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{hashlib.md5(password.encode()).hexdigest()}'"
cursor.execute(query)

# register()
cursor.execute(f"INSERT INTO users (username, password, email) VALUES ('{username}', '{hashed}', '{email}')")
```

An attacker can inject arbitrary SQL by providing a username like `' OR '1'='1' --`, which would bypass authentication entirely or corrupt/destroy the database.

**Fix:** Use parameterized queries (also called prepared statements):

```python
# login
cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed_password))

# register
cursor.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", (username, hashed, email))
```

---

### 2. Weak Password Hashing — MD5 (Severity: Critical)

```python
hashlib.md5(password.encode()).hexdigest()
```

MD5 is cryptographically broken for password storage. It is extremely fast, has no salt, and massive precomputed rainbow tables exist for it. An attacker who obtains the database can crack most passwords trivially.

**Fix:** Use `bcrypt`, `argon2`, or at minimum `hashlib.scrypt` / `hashlib.pbkdf2_hmac` with a per-user salt:

```python
import bcrypt

# Hashing
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# Verification
bcrypt.checkpw(password.encode(), stored_hash)
```

---

## High-Severity Issues

### 3. No Input Validation (Severity: High)

Neither endpoint validates that `username`, `password`, or `email` are present, non-empty, or meet any format requirements. If any field is `None` (e.g., the client sends a malformed JSON body or omits a field), the code will raise an unhandled `AttributeError` (`None.encode()`) or produce broken SQL even after parameterization is applied.

**Fix:** Validate all required fields before processing:

```python
if not username or not password:
    return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
```

---

### 4. No Authentication Token Returned on Login (Severity: High)

The `/login` endpoint returns only `user_id` on success:

```python
return jsonify({'status': 'ok', 'user_id': user[0]})
```

There is no session, cookie, or token issued. This means the client has no secure way to prove identity on subsequent requests. The `user_id` alone in a response body provides no authentication mechanism.

**Fix:** Issue a signed token (e.g., JWT via `flask-jwt-extended`) or use Flask's server-side session management.

---

### 5. No Error Handling for Database Operations (Severity: High)

Database connections and queries are not wrapped in try/except blocks. Any database error (connection failure, constraint violation on duplicate username, etc.) will result in an unhandled exception and a 500 response that may leak stack trace details to the client.

**Fix:** Wrap database operations in try/except and return appropriate error responses:

```python
try:
    conn = sqlite3.connect(DB_PATH)
    # ... operations ...
except sqlite3.IntegrityError:
    return jsonify({'status': 'error', 'message': 'Username already exists'}), 409
except sqlite3.Error as e:
    return jsonify({'status': 'error', 'message': 'Database error'}), 500
finally:
    conn.close()
```

---

## Medium-Severity Issues

### 6. Database Connection Not Closed on Exception (Severity: Medium)

The `conn.close()` call at the end of each function will not execute if an exception is raised beforehand, potentially leaking database connections.

**Fix:** Use a context manager or `try/finally` to ensure the connection is always closed.

---

### 7. Hardcoded Database Path (Severity: Medium)

```python
DB_PATH = '/app/users.db'
```

This hardcoded absolute path makes the code inflexible across environments (development, staging, production) and requires code changes to reconfigure.

**Fix:** Read the path from an environment variable or application configuration:

```python
import os
DB_PATH = os.environ.get('DB_PATH', '/app/users.db')
```

---

### 8. `register` Returns 200 on Success Instead of 201 (Severity: Low)

Successful resource creation should return HTTP 201 Created, not the default 200 OK.

```python
return jsonify({'status': 'registered'}), 201
```

---

## Additional Observations

- **No PR description:** The lack of a description makes it hard to understand intent, testing done, or scope of the change. Please add one.
- **No rate limiting:** Authentication endpoints are prime targets for brute-force attacks. Consider adding rate limiting (e.g., via `flask-limiter`).
- **Timing side-channel:** The login response time may differ slightly between "user not found" and "wrong password" cases. Using a constant-time comparison (built into `bcrypt.checkpw`) mitigates this.
- **No logging:** Failed login attempts should be logged for security monitoring purposes.

---

## Verdict

**Do not merge in current state.** The SQL injection and MD5 password hashing issues alone are sufficient grounds for rejection — both are well-known, easily exploitable vulnerabilities. These must be resolved and the PR re-reviewed before merging.
