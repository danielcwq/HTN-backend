#!/usr/bin/env python3
"""
Simple test script to verify local-worker setup
"""

import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

def test_imports():
    """Test that all required modules can be imported"""
    try:
        from supa import SupabaseClient
        print("✓ supa module imported successfully")
        
        from worker_logging import setup_logging, MetricsLogger
        print("✓ logging module imported successfully")
        
        from windows import multiday_historical_window, get_timezone
        print("✓ windows module imported successfully")
        
        from features import FeatureComputer
        print("✓ features module imported successfully")
        
        from cohere_client import CohereClient
        print("✓ cohere_client module imported successfully")
        
        from prompts import get_multiday_system_prompt
        print("✓ prompts module imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_environment():
    """Test environment variable loading"""
    try:
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        
        # Check if .env exists
        env_file = Path(".env")
        if env_file.exists():
            print("✓ .env file found")
        else:
            print("⚠ .env file not found - using env.template as reference")
        
        # Check critical variables (without printing values)
        required_vars = ["SUPABASE_URL", "SERVICE_ROLE_KEY", "COHERE_API_KEY"]
        missing = []
        
        for var in required_vars:
            if os.getenv(var):
                print(f"✓ {var} is set")
            else:
                print(f"✗ {var} is missing")
                missing.append(var)
        
        return len(missing) == 0
        
    except Exception as e:
        print(f"✗ Environment test failed: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without external dependencies"""
    try:
        from windows import get_timezone, now_in_tz
        from features import FeatureComputer
        
        # Test timezone handling
        tz = get_timezone()
        current_time = now_in_tz()
        print(f"✓ Timezone: {tz}, Current time: {current_time}")
        
        # Test feature computer initialization
        fc = FeatureComputer()
        print(f"✓ FeatureComputer initialized with version: {fc.feature_version}")
        
        return True
        
    except Exception as e:
        print(f"✗ Basic functionality test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing local-worker setup...\n")
    
    tests_passed = 0
    total_tests = 3
    
    print("1. Testing module imports:")
    if test_imports():
        tests_passed += 1
    print()
    
    print("2. Testing environment configuration:")
    if test_environment():
        tests_passed += 1
    print()
    
    print("3. Testing basic functionality:")
    if test_basic_functionality():
        tests_passed += 1
    print()
    
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("✓ Setup looks good! You can now run:")
        print("  python run.py multiday --dry-run")
    else:
        print("✗ Setup incomplete. Please check the errors above.")
        if tests_passed >= 1:
            print("\nHint: Create .env file from env.template and fill in your credentials")
    
    return tests_passed == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
