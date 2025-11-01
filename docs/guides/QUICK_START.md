# Quick Start Guide

## ✅ Step 1: Database Migration (COMPLETE!)
Migration applied successfully in Supabase.

## ⏭️ Step 2: Install Dependencies

```bash
# Backend dependencies
cd advanced_vault/backend
pip install -r requirements.txt

# GUI dependencies  
cd ../gui
pip install flet requests PyPDF2

# Or install globally
pip install fastapi uvicorn supabase flet requests PyPDF2
```

## ⏭️ Step 3: Configure Backend

Create `advanced_vault/backend/.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
JWT_SECRET=your-random-secret-min-32-chars
ENVIRONMENT=development
```

## ⏭️ Step 4: Start Backend

```bash
cd advanced_vault/backend
python3 main.py
```

Backend runs at: `http://localhost:8000`

## ⏭️ Step 5: Test API

```bash
# Get auth token (signup/login)
# Then test adapter registry:
python3 verify_backend.py YOUR_TOKEN
```

## ⏭️ Step 6: Launch GUI

```bash
cd advanced_vault/gui
python3 vault_app.py
```

## ⏭️ Step 7: Test Workflow

1. Login in GUI
2. Add secret → Verify sync to cloud
3. Upload PDF → Verify processing
4. Accept training prompt → Verify Q&A generation
5. Check training job submission

---

## Verification Checklist

- [ ] Backend dependencies installed
- [ ] Backend server starts
- [ ] API endpoints respond
- [ ] GUI launches
- [ ] Can login
- [ ] Can add secrets
- [ ] Can upload PDFs
- [ ] Training workflow works

---

## Files Created

- ✅ `verify_backend.py` - API verification script
- ✅ `BACKEND_API_TESTING.md` - Testing guide
- ✅ `NEXT_STEPS.md` - Detailed next steps

---

## Status

✅ Database migration: APPLIED
✅ Code structure: VERIFIED  
⏭️  Dependencies: NEED INSTALLATION
⏭️  Backend server: NEED TESTING
⏭️  GUI: NEED TESTING

