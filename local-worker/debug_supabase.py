#!/usr/bin/env python3
"""
Debug script for Supabase authentication issues
"""

import os
import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from dotenv import load_dotenv
from supabase import create_client

def debug_environment():
    """Check environment variables"""
    print("=== Environment Variables ===")
    
    load_dotenv()
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SERVICE_ROLE_KEY")
    
    print(f"SUPABASE_URL: {url}")
    print(f"SERVICE_ROLE_KEY: {'*' * 20 + key[-10:] if key and len(key) > 20 else 'MISSING'}")
    
    if not url:
        print("❌ SUPABASE_URL is missing!")
        return False
    
    if not key:
        print("❌ SERVICE_ROLE_KEY is missing!")
        return False
    
    # Validate URL format
    if not url.startswith("https://") or not ".supabase.co" in url:
        print("❌ SUPABASE_URL format looks incorrect")
        return False
    
    # Validate key format (should be a JWT starting with eyJ)
    if not key.startswith("eyJ"):
        print("❌ SERVICE_ROLE_KEY format looks incorrect (should start with 'eyJ')")
        return False
    
    print("✅ Environment variables look correct")
    return True

def debug_client_creation():
    """Test Supabase client creation"""
    print("\n=== Client Creation ===")
    
    try:
        load_dotenv()
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SERVICE_ROLE_KEY")
        
        client = create_client(url, key)
        print("✅ Supabase client created successfully")
        return client
    except Exception as e:
        print(f"❌ Failed to create Supabase client: {e}")
        return None

def debug_simple_query(client):
    """Test a simple query"""
    print("\n=== Simple Query Test ===")
    
    try:
        # Try to query the sources table (should exist)
        response = client.table('sources').select('*').limit(1).execute()
        print(f"✅ Query successful! Returned {len(response.data)} records")
        if response.data:
            print(f"Sample record keys: {list(response.data[0].keys())}")
        return True
    except Exception as e:
        print(f"❌ Query failed: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Check if it's specifically an auth error
        if "401" in str(e) or "Unauthorized" in str(e):
            print("🔍 This is an authentication error. Possible causes:")
            print("   1. Wrong SERVICE_ROLE_KEY")
            print("   2. Key is for a different Supabase project")
            print("   3. Key has expired or been regenerated")
            print("   4. Project has been paused/suspended")
        
        return False

def debug_table_existence(client):
    """Check if expected tables exist"""
    print("\n=== Table Existence Check ===")
    
    expected_tables = ['sources', 'events', 'features', 'inferences']
    
    for table_name in expected_tables:
        try:
            response = client.table(table_name).select('*').limit(0).execute()
            print(f"✅ Table '{table_name}' exists")
        except Exception as e:
            if "relation" in str(e).lower() and "does not exist" in str(e).lower():
                print(f"❌ Table '{table_name}' does not exist")
            else:
                print(f"❓ Table '{table_name}' check failed: {e}")

def debug_permissions(client):
    """Test different permission levels"""
    print("\n=== Permission Level Check ===")
    
    try:
        # Try to access auth admin (service role only)
        auth_response = client.auth.admin.list_users()
        print("✅ Service role confirmed - can access auth admin")
        return True
    except Exception as e:
        print(f"❌ Cannot access auth admin: {e}")
        print("🔍 This suggests the key might not be a service role key")
        return False

def main():
    """Run all debug checks"""
    print("🔍 Debugging Supabase Authentication\n")
    
    # Step 1: Check environment
    if not debug_environment():
        print("\n❌ Environment check failed. Fix environment variables first.")
        return
    
    # Step 2: Test client creation
    client = debug_client_creation()
    if not client:
        print("\n❌ Cannot create client. Check your credentials.")
        return
    
    # Step 3: Test simple query
    if not debug_simple_query(client):
        print("\n❌ Basic query failed. This is the main issue.")
        
        # Additional debugging for auth failures
        print("\n🔧 Additional Debugging Steps:")
        print("1. Go to your Supabase Dashboard → Settings → API")
        print("2. Verify the URL matches exactly (including project ID)")
        print("3. Copy the 'service_role' key (not 'anon' key)")
        print("4. Make sure the key starts with 'eyJ' and is very long")
        print("5. Check if your project is active/not paused")
        return
    
    # Step 4: Check table structure
    debug_table_existence(client)
    
    # Step 5: Check permission level
    debug_permissions(client)
    
    print("\n✅ All checks passed! Supabase connection is working.")

if __name__ == "__main__":
    main()
