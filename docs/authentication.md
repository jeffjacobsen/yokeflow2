# Authentication

YokeFlow uses a simple single-user authentication system designed for personal or small team use. This document explains how it works and how to configure it.

---

## Overview

**Authentication Model:** Single shared password (not multi-user)

- **Development Mode** (default): No password required - automatic bypass
- **Production Mode** (optional): Single password protects all API access

**Key Features:**
- JWT-based authentication for stateless sessions
- Automatic development mode detection
- 24-hour token expiration (configurable)
- Password-protected API endpoints

---

## Quick Start

### Local Development (No Authentication)

**Default behavior** - just run the servers:

```bash
# Start API
python api/start_api.py

# Start Web UI
cd web-ui && npm run dev

# Visit http://localhost:3010
# ✓ Direct access - no login required
```

No configuration needed. Authentication is automatically disabled when `UI_PASSWORD` is not set.

### Production Deployment (Enable Authentication)

Set a password in your `.env` file:

```bash
# .env
UI_PASSWORD=your-secure-password-here
SECRET_KEY=your-random-jwt-secret-key
```

Restart the API server and authentication will be enabled.

---

## How It Works

### Single-User Authentication System

YokeFlow uses a **shared password** model, not individual user accounts:

1. **One password** protects the entire application
2. **Everyone** who knows the password has full access
3. **No user management** - no registration, users, or roles
4. **Session tokens** (JWT) keep you logged in for 24 hours

**This is designed for:**
- Personal projects (single developer)
- Small teams (2-5 people sharing a password)
- Internal tools (trusted environment)

**Not designed for:**
- Public-facing applications
- Multi-tenant systems
- Enterprise role-based access control

### Development Mode (Authentication Disabled)

When `UI_PASSWORD` is **not set** or **empty**:

**Backend Behavior:**
```python
# api/auth.py
if not UI_PASSWORD:
    # Accept any password
    # Skip JWT validation
    # Allow all API requests
```

**Frontend Behavior:**
1. On load, checks if `/api/info` is accessible without auth
2. If successful → Sets authenticated state
3. Bypasses login page completely
4. Shows console message: `🔓 Development mode detected`

**Result:** No login required, instant access to all features.

### Production Mode (Authentication Enabled)

When `UI_PASSWORD` is **set** to a non-empty value:

**Backend Behavior:**
```python
# api/auth.py
if password == UI_PASSWORD:
    # Generate JWT token
    # Return token to client
else:
    # Return 401 Unauthorized
```

**Frontend Behavior:**
1. Checks `/api/info` - receives 401 Unauthorized
2. Redirects to `/login` page
3. User enters password
4. If correct, receives JWT token
5. Token stored in localStorage and used for all API calls
6. Shows console message: `🔒 Production mode`

**Result:** Login required, password-protected access.

---

## Configuration

### Environment Variables

Set in `.env` file in the project root:

```bash
# Authentication
UI_PASSWORD=                              # Unset/empty = dev mode, set = production
SECRET_KEY=your-random-secret-key-here    # Used to sign JWT tokens

# Optional
ACCESS_TOKEN_EXPIRE_MINUTES=1440          # Token lifetime (default: 24 hours)
```

### Configuration Options

| Mode | UI_PASSWORD | Behavior |
|------|-------------|----------|
| **Development** | (not set) | Authentication disabled, instant access |
| **Development** | (empty string) | Authentication disabled, instant access |
| **Production** | `mypassword` | Login required, password = "mypassword" |

### Generating a Secure Secret Key

**For production**, generate a strong random secret key:

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"

# OpenSSL
openssl rand -base64 32
```

Example `.env` for production:
```bash
UI_PASSWORD=MySecurePass123!
SECRET_KEY=8nZXKj3mP9vLqR2wE5tY7uI0oP3aSdFgHjKl1QwErTy=
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

---

## Disabling Authentication

### Method 1: Remove UI_PASSWORD (Recommended)

Comment out or delete the `UI_PASSWORD` line in `.env`:

```bash
# .env (before)
UI_PASSWORD=mypassword
SECRET_KEY=...

# .env (after)
# UI_PASSWORD=mypassword
SECRET_KEY=...
```

**Restart the API server** - authentication is now disabled.

### Method 2: Set to Empty String

Set `UI_PASSWORD` to an empty value:

```bash
# .env
UI_PASSWORD=
SECRET_KEY=dev-secret-key
```

**Restart the API server** - authentication is now disabled.

### Method 3: Environment Variable Override

Unset the variable when running:

```bash
# Clear variable
unset UI_PASSWORD

# Run API
python api/start_api.py
```

---

## Enabling Authentication

### Step 1: Set Password

Edit `.env`:
```bash
UI_PASSWORD=YourPassword123
SECRET_KEY=your-random-secret-key-here
```

### Step 2: Restart API Server

```bash
# Stop current server (Ctrl+C)
# Start with new config
python api/start_api.py
```

### Step 3: Verify

Visit http://localhost:3010:
- Should redirect to `/login`
- Enter your password
- Should access dashboard on success

---

## Security Considerations

### Development Mode Security

⚠️ **Development mode disables ALL authentication:**
- No password required
- No JWT validation
- All API endpoints accessible
- **Never use in production or public networks**

✅ **Safe for:**
- Local development (localhost)
- Private networks (firewalled)
- Trusted environments

❌ **Unsafe for:**
- Public internet
- Shared hosting
- Cloud deployments

### Production Mode Security

**Password Protection:**
- Use strong passwords (12+ characters, mixed case, numbers, symbols)
- Don't share passwords in insecure channels (email, Slack, etc.)
- Rotate passwords periodically
- Use password manager for team sharing

**JWT Security:**
- SECRET_KEY must be random and unique
- Never commit SECRET_KEY to git
- Tokens expire after 24 hours (configurable)
- Tokens stored in browser localStorage (XSS risk if not careful)

**Limitations:**
- Single password = anyone with password has full access
- No user roles or permissions
- No audit trail of who did what
- No password reset mechanism (just change UI_PASSWORD)

---

## Authentication Flow Diagram

### Development Mode
```
Browser → GET /api/info (no auth) → API → 200 OK
         ↓
    Auto-login (no password)
         ↓
    Access all features
```

### Production Mode
```
Browser → GET /api/info (no auth) → API → 401 Unauthorized
         ↓
    Redirect to /login
         ↓
    User enters password
         ↓
    POST /api/auth/login → API validates → JWT token returned
         ↓
    Store token in localStorage
         ↓
    GET /api/projects (with token) → API validates JWT → 200 OK
```

---

## Troubleshooting

### Issue: Still seeing login in development mode

**Check 1:** Is `UI_PASSWORD` actually unset?
```bash
# View .env file
cat .env | grep UI_PASSWORD

# Should be commented or missing:
# UI_PASSWORD=
```

**Check 2:** Did you restart the API?
```bash
# Stop API (Ctrl+C)
# Start fresh
python api/start_api.py

# Look for startup message (should NOT mention password)
```

**Check 3:** Clear browser cache
```javascript
// Browser console
localStorage.clear();
location.reload();
```

### Issue: Can't login with correct password

**Check 1:** Verify password in .env
```bash
# .env
UI_PASSWORD=MyPassword123

# Must match exactly (case-sensitive, no extra spaces)
```

**Check 2:** Check API logs
```bash
# Should see login attempts in terminal
# Failed: "Invalid credentials"
# Success: "Login successful"
```

**Check 3:** Inspect JWT token
```javascript
// Browser console
console.log(localStorage.getItem('token'));
// Should show a long JWT string
```

### Issue: Token expired / 401 errors

**Solution:** Login again to get fresh token

Tokens expire after 24 hours (default). When expired:
1. API returns 401 Unauthorized
2. Frontend redirects to `/login`
3. Enter password again
4. New token issued for 24 hours

**To extend expiration:**
```bash
# .env
ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7 days
```

---

## API Endpoints

### Public Endpoints (No Auth Required)

```bash
POST /api/auth/login              # Login with password
GET  /api/auth/check              # Check if auth is required
```

### Protected Endpoints (Auth Required in Production)

All other endpoints require authentication when `UI_PASSWORD` is set:

```bash
GET    /api/projects              # List projects
POST   /api/projects              # Create project
GET    /api/projects/{id}         # Get project
POST   /api/sessions/start        # Start session
# ... all other API endpoints
```

**In development mode:** All endpoints are public

**In production mode:** All endpoints require valid JWT token in `Authorization` header:
```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Code References

### Backend
- [api/auth.py](../api/auth.py) - Authentication logic, JWT handling
- [api/main.py](../api/main.py) - Protected endpoints, auth dependency

### Frontend
- [web-ui/src/lib/auth-context.tsx](../web-ui/src/lib/auth-context.tsx) - Auth state management
- [web-ui/src/lib/api.ts](../web-ui/src/lib/api.ts) - JWT token injection
- [web-ui/src/app/login/page.tsx](../web-ui/src/app/login/page.tsx) - Login form

---

## Migration to Multi-User

If you need multi-user authentication:

**Option 1: Add user management**
- Add `users` table to database
- Store hashed passwords (bcrypt)
- Add user_id to sessions/projects
- Implement registration/login flows

**Option 2: Use external auth**
- OAuth (GitHub, Google, etc.)
- SAML for enterprise
- Auth0, Clerk, or similar services

**Option 3: Deploy behind auth proxy**
- Nginx with basic auth
- Cloudflare Access
- Tailscale for private access

These are beyond the scope of YokeFlow's built-in authentication, but can be added as needed.

---

## Best Practices

### Development
✅ Leave `UI_PASSWORD` unset for local work
✅ Use `.env.example` to document variables
✅ Add `.env` to `.gitignore`
✅ Test both modes before deploying

### Production
✅ Always set strong `UI_PASSWORD`
✅ Generate random `SECRET_KEY`
✅ Never commit secrets to git
✅ Use deployment platform secret management
✅ Enable HTTPS (required for secure cookies)
✅ Consider adding Tailscale/VPN for private access

### Team Usage
✅ Share password via secure channel (1Password, etc.)
✅ Rotate password when team members leave
✅ Document who has access
✅ Consider VPN for additional security

---

## Related Documentation

- [docs/deployment-guide.md](deployment-guide.md) - Production deployment
- [api/README.md](../api/README.md) - API documentation
- [README.md](../README.md) - Quick start guide
