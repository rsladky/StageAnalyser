#!/usr/bin/env python3
"""Test de connexion Supabase"""

import os
from pathlib import Path
from supabase import create_client

# Charger .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"🔍 Testing Supabase connection...")
print(f"   URL: {SUPABASE_URL}")
print(f"   Key type: {SUPABASE_KEY[:20]}...")

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Test 1: Tester lecture (fonctionne toujours)
    print("\n✓ Connected to Supabase")

    # Test 2: Tester insertion sur User (attend RLS)
    print("Testing permissions...")
    result = supabase.table("User").select("count").execute()
    print(f"✓ Can read User table: {result.data}")

    # Test 3: Tester insert
    print("\nTesting insert permission...")
    result = supabase.table("User").insert({"Name": "TestUser"}).execute()
    if result.data:
        print(f"✓ Can insert to User table!")
        # Nettoyer
        supabase.table("User").delete().eq("Name", "TestUser").execute()
    else:
        print(f"✗ Insert failed: {result}")

except Exception as e:
    print(f"✗ Connection failed: {e}")
