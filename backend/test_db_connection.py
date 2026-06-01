"""
Quick test script to verify Supabase connection and table existence
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import after env loaded
from services.supabase_service import supabase

def test_table_exists(table_name):
    """Test if a table exists and can be queried"""
    try:
        print(f"\n{'='*60}")
        print(f"Testing table: {table_name}")
        print(f"{'='*60}")

        # Try to query the table
        response = supabase.table(table_name).select("*").limit(1).execute()

        if response.data is not None:
            count = len(response.data)
            print(f"✅ SUCCESS: Table '{table_name}' exists and is queryable")
            print(f"   Sample records: {count}")
            if count > 0:
                print(f"   First record keys: {list(response.data[0].keys())}")
            return True
        else:
            print(f"⚠️  WARNING: Table '{table_name}' exists but returned no data")
            return True

    except Exception as e:
        error_str = str(e)
        if "relation" in error_str.lower() and "does not exist" in error_str.lower():
            print(f"❌ ERROR: Table '{table_name}' DOES NOT EXIST")
        elif "JSON could not be generated" in error_str:
            print(f"❌ ERROR: Table '{table_name}' exists but has schema issues")
            print(f"   Error: {error_str}")
        else:
            print(f"❌ ERROR: {error_str}")
        return False


def main():
    print("="*60)
    print("SUPABASE DATABASE CONNECTION TEST")
    print("="*60)

    # Get connection info
    url = os.getenv('SUPABASE_URL', 'NOT_SET')
    if 'supabase.co' in url:
        project_id = url.split('//')[1].split('.')[0]
        print(f"Connected to: {project_id}.supabase.co")
    else:
        print(f"SUPABASE_URL: {url}")

    # Test tables
    tables_to_test = [
        "counsellors",
        "consultation_types",
        "processing_modes",
        "templates",
        "segment_definitions",
        "consultation_type_segments",
        "template_segments"
    ]

    results = {}
    for table in tables_to_test:
        results[table] = test_table_exists(table)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed

    print(f"✅ Passed: {passed}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")

    if failed > 0:
        print("\n⚠️  RECOMMENDATION:")
        print("   1. Check if migrations have been applied to Supabase")
        print("   2. Run: supabase db push (if using Supabase CLI)")
        print("   3. Or apply migrations manually in Supabase dashboard")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
