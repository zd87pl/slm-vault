# Supabase Setup Guide

## Prerequisites

- Supabase account (free tier is fine for alpha)
- Access to Supabase dashboard

## Step 1: Create Project

1. Go to [supabase.com](https://supabase.com)
2. Click "New Project"
3. Choose organization
4. Project settings:
   - **Name**: `wdva-personal-vault` (or your preferred name)
   - **Database Password**: Generate strong password (save it!)
   - **Region**: Choose closest to your users
   - **Pricing Plan**: Free (for alpha)

5. Click "Create new project"
6. Wait 2-3 minutes for project to provision

## Step 2: Get API Keys

1. Go to Project Settings → API
2. Copy the following:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **anon/public key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
   - **service_role key**: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (keep secret!)

3. Save to `.env` file:
```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Step 3: Run Migrations

1. Go to SQL Editor in Supabase dashboard
2. Click "New query"
3. Copy contents of `migrations/001_initial_schema.sql`
4. Paste and click "Run"
5. Verify no errors

6. Repeat for `migrations/002_rls_policies.sql`

## Step 4: Configure Auth

### Enable Email/Password Auth

1. Go to Authentication → Providers
2. **Email** should be enabled by default
3. Configure settings:
   - ✅ Enable email confirmations
   - ✅ Secure email change
   - Confirmation URL: `http://localhost:3000/auth/callback` (update for production)

### Enable OAuth Providers

#### Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project (or use existing)
3. Enable Google+ API
4. Create OAuth 2.0 credentials:
   - Application type: Web application
   - Authorized redirect URIs:
     - `https://xxxxx.supabase.co/auth/v1/callback`
5. Copy **Client ID** and **Client Secret**

6. In Supabase:
   - Go to Authentication → Providers → Google
   - Toggle "Enable"
   - Paste Client ID and Client Secret
   - Click "Save"

#### GitHub OAuth

1. Go to GitHub → Settings → Developer settings → OAuth Apps
2. Click "New OAuth App"
3. Fill in:
   - Application name: "Personal Vault"
   - Homepage URL: `https://yourdomain.com` (or `http://localhost:3000` for dev)
   - Authorization callback URL: `https://xxxxx.supabase.co/auth/v1/callback`
4. Click "Register application"
5. Copy **Client ID**
6. Generate new **Client Secret** and copy it

7. In Supabase:
   - Go to Authentication → Providers → GitHub
   - Toggle "Enable"
   - Paste Client ID and Client Secret
   - Click "Save"

## Step 5: Verify Setup

### Test Database

1. Go to Table Editor
2. You should see tables:
   - profiles
   - user_keys
   - vault_entries
   - access_logs
   - devices
   - api_keys
   - sync_metadata

### Test RLS

1. Go to SQL Editor
2. Run this query:
```sql
SELECT * FROM vault_entries;
```

3. Should return 0 rows (no data yet, and RLS blocks anonymous access)

### Test Auth

1. Go to Authentication → Users
2. Click "Add user"
3. Enter email and password
4. User should be created
5. Check Table Editor → profiles
6. Should see auto-created profile for the user

## Step 6: Configure Production URLs

When deploying to production:

1. Update **Site URL** in Authentication → URL Configuration:
   - Site URL: `https://yourdomain.com`
   - Redirect URLs: `https://yourdomain.com/**`

2. Update OAuth redirect URIs in Google/GitHub:
   - `https://yourdomain.com/auth/callback`

## Environment Variables Summary

Create `.env` file in `advanced_vault/backend/`:

```env
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# App
JWT_SECRET=your-random-secret-min-32-chars
ENVIRONMENT=development

# Frontend (for CORS)
FRONTEND_URL=http://localhost:3000

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## Troubleshooting

### Migration Errors

**Error: "relation already exists"**
- Solution: Tables already created, skip that migration

**Error: "permission denied"**
- Solution: Make sure you're using service_role key in backend, not anon key

### Auth Not Working

**OAuth redirect not working**
- Check redirect URIs match exactly (including https/http)
- Verify OAuth app is approved/published

**Email confirmation not received**
- Check spam folder
- Verify email provider in Authentication → Settings

### RLS Blocking Queries

**Getting 0 rows when data exists**
- Make sure you're authenticated (JWT token in Authorization header)
- Check RLS policies are correct
- Use `auth.uid()` to get current user ID

## Next Steps

After Supabase is set up:

1. ✅ Database schema created
2. ✅ RLS policies enabled
3. ✅ Auth providers configured
4. ➡️  Build FastAPI backend
5. ➡️  Update CLI with auth
6. ➡️  Build web UI

## Useful Supabase Resources

- [Supabase Docs](https://supabase.com/docs)
- [Auth Docs](https://supabase.com/docs/guides/auth)
- [RLS Guide](https://supabase.com/docs/guides/auth/row-level-security)
- [Database Functions](https://supabase.com/docs/guides/database/functions)
