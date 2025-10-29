#!/bin/bash

echo "Setting Railway environment variables..."
echo ""
echo "Make sure you're in the correct Railway project context."
echo ""

# Get credentials from user
read -p "Enter SUPABASE_ANON_KEY: " SUPABASE_ANON_KEY
read -p "Enter SUPABASE_SERVICE_KEY: " SUPABASE_SERVICE_KEY
read -p "Enter JWT_SECRET: " JWT_SECRET

# Set all variables
railway variables set SUPABASE_URL="https://ibiapabkyskoazpgcymo.supabase.co"
railway variables set SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY"
railway variables set SUPABASE_SERVICE_KEY="$SUPABASE_SERVICE_KEY"
railway variables set JWT_SECRET="$JWT_SECRET"
railway variables set FRONTEND_URL="https://getenclave.vercel.app"
railway variables set ALLOWED_ORIGINS='["https://getenclave.vercel.app","http://localhost:3000"]'
railway variables set ENVIRONMENT="production"
railway variables set JWT_ALGORITHM="HS256"
railway variables set API_HOST="0.0.0.0"
railway variables set RATE_LIMIT_PER_MINUTE="60"
railway variables set LOG_LEVEL="INFO"

echo ""
echo "✓ All environment variables set!"
echo "Railway will automatically redeploy your service."
