# Personal Vault Backend API

FastAPI backend for multi-tenant personal vault.

## Features

- ✅ User authentication (Supabase Auth)
- ✅ Encrypted vault storage (client-side encryption)
- ✅ Access logging/audit trail
- ✅ Device management
- ✅ API keys for programmatic access
- ✅ Row Level Security (RLS)
- ✅ Rate limiting
- ✅ CORS support

## Setup

### 1. Install Dependencies

```bash
cd advanced_vault/backend
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
cp .env.example .env
```

Fill in Supabase credentials (see `supabase/SETUP.md`).

### 3. Set Up Supabase

Follow instructions in `supabase/SETUP.md`:
1. Create Supabase project
2. Run migrations
3. Configure auth providers
4. Get API keys

### 4. Run Server

```bash
# Development (auto-reload)
python main.py

# Or with uvicorn
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

Server runs at: `http://localhost:8000`

API docs at: `http://localhost:8000/docs`

## API Endpoints

### Authentication

```
POST /api/auth/signup       - Create new user
POST /api/auth/login        - Login with email/password
POST /api/auth/logout       - Logout
POST /api/auth/refresh      - Refresh access token
GET  /api/auth/me           - Get current user profile
```

### Vault

```
POST   /api/vault/store        - Store encrypted entry
GET    /api/vault/entries      - List entries (metadata)
GET    /api/vault/entry/:id    - Get specific entry
DELETE /api/vault/entry/:id    - Delete entry
POST   /api/vault/sync         - Batch sync entries
GET    /api/vault/stats        - Get vault statistics
```

### Access Logs

```
GET /api/logs          - Get access logs (paginated)
GET /api/logs/stats    - Get access statistics
```

### Devices

```
GET    /api/devices           - List devices
POST   /api/devices/register  - Register new device
DELETE /api/devices/:id       - Revoke device
```

### API Keys

```
GET    /api/keys        - List API keys
POST   /api/keys/create - Create new API key
DELETE /api/keys/:id    - Revoke API key
```

## Authentication

All endpoints (except `/auth/signup` and `/auth/login`) require authentication.

### JWT Token

Include in Authorization header:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/vault/entries
```

### API Key

For programmatic access:

```bash
curl -H "Authorization: Bearer vlt_YOUR_API_KEY" \
  http://localhost:8000/api/vault/entries
```

## Client Headers

Recommended headers for proper logging:

```
Authorization: Bearer <token>
X-Client-Type: cli|macos_app|web|mcp
X-Client-Version: 0.1.0
```

## Security

### Zero-Knowledge Architecture

- All encryption/decryption happens **client-side**
- Server stores only encrypted blobs
- Master key never transmitted to server
- User password derives Key Encryption Key (KEK)
- KEK encrypts master key stored in database

### Row Level Security (RLS)

- Database-level isolation between users
- Users can only access their own data
- Enforced by Supabase policies

### Rate Limiting

- Default: 60 requests/minute per IP
- Configure in `config.py`

### CORS

- Configure allowed origins in `.env`
- Default: `http://localhost:3000` (web UI)

## Development

### Run Tests

```bash
pytest tests/
```

### Check Logs

```bash
# View Supabase logs
# Go to Supabase Dashboard → Logs

# View local logs
tail -f logs/api.log
```

### Database Migrations

```bash
# Run new migration in Supabase SQL Editor
cat supabase/migrations/003_new_migration.sql

# Or use Supabase CLI
supabase migration up
```

## Deployment

### Railway

```bash
railway init
railway up
```

Set environment variables in Railway dashboard.

### Render

```yaml
# render.yaml
services:
  - type: web
    name: vault-api
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_ANON_KEY
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
```

### Docker

```bash
docker build -t vault-api .
docker run -p 8000:8000 --env-file .env vault-api
```

## Troubleshooting

### JWT Verification Failed

- Check `JWT_SECRET` matches Supabase project secret
- Verify token hasn't expired
- Ensure `aud: "authenticated"` in JWT payload

### Database Connection Failed

- Verify `SUPABASE_URL` is correct
- Check `SUPABASE_ANON_KEY` or `SUPABASE_SERVICE_KEY`
- Ensure Supabase project is active

### RLS Blocking Queries

- Make sure JWT token is valid
- Check RLS policies in Supabase dashboard
- Use service role key for admin operations (bypasses RLS)

## Project Structure

```
backend/
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── api/                    # API endpoints
│   ├── auth.py            # Authentication routes
│   ├── vault.py           # Vault operations
│   ├── logs.py            # Access logs
│   ├── devices.py         # Device management
│   └── keys.py            # API key management
├── middleware/            # Middleware
│   └── auth.py           # JWT verification
├── models/               # Data models (Pydantic)
├── utils/                # Utilities
│   ├── supabase_client.py  # Supabase client
│   └── access_logger.py    # Access logging
└── supabase/             # Supabase setup
    ├── SETUP.md          # Setup instructions
    └── migrations/       # SQL migrations
        ├── 001_initial_schema.sql
        └── 002_rls_policies.sql
```

## Next Steps

1. ✅ Backend API created
2. ➡️  Update CLI with auth
3. ➡️  Build web UI
4. ➡️  Deploy to production
5. ➡️  Invite alpha testers
