# OAuth Setup Guide for Enclave GUI

This guide walks you through setting up OAuth providers (Google, GitHub) for the Enclave GUI.

## Prerequisites

- Supabase project created
- Backend deployed to Railway

## Configure Redirect URLs in Supabase

1. Go to **Supabase Dashboard** → Your Project → **Authentication** → **URL Configuration**

2. Add these to **Redirect URLs**:
   ```
   http://localhost:54321/auth/callback
   http://localhost:54321/*
   ```

3. Set **Site URL** to your frontend URL:
   ```
   https://getenclave.vercel.app
   ```

## Setup Google OAuth

### 1. Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure OAuth consent screen if prompted:
   - User Type: **External**
   - App name: **Enclave**
   - User support email: your email
   - Developer contact: your email
6. Create OAuth Client ID:
   - Application type: **Web application**
   - Name: **Enclave**
   - Authorized redirect URIs:
     ```
     https://ibiapabkyskoazpgcymo.supabase.co/auth/v1/callback
     ```
7. Copy **Client ID** and **Client Secret**

### 2. Configure in Supabase

1. Go to **Supabase Dashboard** → **Authentication** → **Providers**
2. Find **Google** and enable it
3. Paste your **Client ID** and **Client Secret**
4. Click **Save**

## Setup GitHub OAuth

### 1. Create GitHub OAuth App

1. Go to [GitHub Settings](https://github.com/settings/developers)
2. Click **OAuth Apps** → **New OAuth App**
3. Fill in details:
   - Application name: **Enclave**
   - Homepage URL: `https://getenclave.vercel.app`
   - Authorization callback URL:
     ```
     https://ibiapabkyskoazpgcymo.supabase.co/auth/v1/callback
     ```
4. Click **Register application**
5. Copy **Client ID**
6. Click **Generate a new client secret** and copy it

### 2. Configure in Supabase

1. Go to **Supabase Dashboard** → **Authentication** → **Providers**
2. Find **GitHub** and enable it
3. Paste your **Client ID** and **Client Secret**
4. Click **Save**

## Environment Variables

Set these environment variables before running the GUI:

```bash
export SUPABASE_URL="https://ibiapabkyskoazpgcymo.supabase.co"
export SUPABASE_ANON_KEY="your_supabase_anon_key"
export ENCLAVE_BACKEND_URL="https://keen-curiosity-production-1288.up.railway.app"
```

## Test OAuth

1. Run the GUI:
   ```bash
   python3 vault_app.py
   ```

2. You should see the authentication screen with:
   - **Continue with Google** button
   - **Continue with GitHub** button
   - Email/password sign in form

3. Click an OAuth button:
   - Browser opens to provider's OAuth consent screen
   - After authorization, you're redirected back
   - GUI automatically logs you in

## Troubleshooting

### OAuth buttons don't work

- Check redirect URLs are exactly correct in both provider and Supabase
- Make sure providers are enabled in Supabase dashboard
- Check browser console for errors

### "Invalid redirect URL" error

- Verify `http://localhost:54321/auth/callback` is in Supabase Redirect URLs
- Make sure the port (54321) isn't already in use

### Email/password sign in works but OAuth doesn't

- Double-check Client ID and Client Secret in Supabase
- Verify callback URLs match exactly
- Try disabling and re-enabling the provider in Supabase

## Testing Email/Password Auth

If you want to skip OAuth setup for now, you can use email/password authentication:

1. Click "Don't have an account? Sign up"
2. Enter email, password, and optional full name
3. Click "Sign Up"
4. Check your email for verification link (if Supabase email confirmation is enabled)
5. Sign in with your credentials

Note: For development, you can disable email confirmation in:
**Supabase Dashboard** → **Authentication** → **Settings** → **Email Auth** → Uncheck "Enable email confirmations"
