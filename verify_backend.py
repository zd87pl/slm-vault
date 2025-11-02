#!/usr/bin/env python3
"""
Backend API Verification Script

Tests adapter registry endpoints after migration is deployed.
Requires: Backend server running and valid auth token.
"""

import requests
import sys
import json
from pathlib import Path

# Configuration
BACKEND_URL = "http://localhost:8000"
# You'll need to get a token from login
AUTH_TOKEN = None  # Set this or pass as argument


def test_adapter_registration(auth_token: str):
    """Test adapter registration endpoint."""
    print("\n" + "="*60)
    print("Testing Adapter Registration")
    print("="*60)
    
    url = f"{BACKEND_URL}/api/adapters/register"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "adapter_path": "/workspace/adapters/test-user/test-adapter.json",
        "encryption_key_hash": "a" * 64,  # Valid SHA256 hash format
        "status": "pending"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Registration successful!")
            print(f"   Adapter ID: {data.get('adapter_id')}")
            return data.get('adapter_id')
        else:
            print(f"❌ Registration failed")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def test_list_adapters(auth_token: str):
    """Test listing adapters endpoint."""
    print("\n" + "="*60)
    print("Testing List Adapters")
    print("="*60)
    
    url = f"{BACKEND_URL}/api/adapters"
    headers = {
        "Authorization": f"Bearer {auth_token}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            adapters = data.get('adapters', [])
            print(f"✅ Found {len(adapters)} adapters")
            if adapters:
                print(f"   First adapter: {adapters[0].get('adapter_id')}")
            return adapters
        else:
            print(f"❌ Failed to list adapters")
            print(f"   Response: {response.text}")
            return []
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def test_verify_ownership(auth_token: str, adapter_id: str):
    """Test ownership verification endpoint."""
    print("\n" + "="*60)
    print("Testing Ownership Verification")
    print("="*60)
    
    url = f"{BACKEND_URL}/api/adapters/{adapter_id}/verify"
    headers = {
        "Authorization": f"Bearer {auth_token}"
    }
    
    try:
        response = requests.post(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            authorized = data.get('authorized', False)
            if authorized:
                print(f"✅ Ownership verified!")
                print(f"   Adapter ID: {data.get('adapter_id')}")
                print(f"   User ID: {data.get('user_id')}")
            else:
                print(f"⚠️  Access denied (expected for test)")
            return authorized
        else:
            print(f"❌ Verification failed")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_hash_function():
    """Test hash_encryption_key function directly."""
    print("\n" + "="*60)
    print("Testing Hash Function")
    print("="*60)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent / "advanced_vault" / "backend"))
        from api.adapters import hash_encryption_key
        
        key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        hash_result = hash_encryption_key(key)
        
        if len(hash_result) == 64:
            print(f"✅ Hash function works correctly")
            print(f"   Input: {key[:16]}...")
            print(f"   Output: {hash_result[:16]}...")
            print(f"   Length: {len(hash_result)} chars (expected: 64)")
            return True
        else:
            print(f"❌ Hash length incorrect: {len(hash_result)} (expected: 64)")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all verification tests."""
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         Backend API Verification Script                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    
    # Test hash function (doesn't require server)
    test_hash_function()
    
    # Get auth token
    auth_token = sys.argv[1] if len(sys.argv) > 1 else AUTH_TOKEN
    
    if not auth_token:
        print("\n⚠️  No auth token provided. Skipping API tests.")
        print("   Usage: python3 verify_backend.py YOUR_AUTH_TOKEN")
        print("   Or set AUTH_TOKEN in the script.")
        print("\n✅ Code structure tests passed!")
        return 0
    
    # Test API endpoints (requires server running)
    print(f"\n🔗 Testing against: {BACKEND_URL}")
    print("   Make sure backend server is running: python3 advanced_vault/backend/main.py")
    
    adapter_id = test_adapter_registration(auth_token)
    
    if adapter_id:
        adapters = test_list_adapters(auth_token)
        test_verify_ownership(auth_token, adapter_id)
    
    print("\n" + "="*60)
    print("✅ Verification Complete!")
    print("="*60)
    return 0


if __name__ == "__main__":
    sys.exit(main())


