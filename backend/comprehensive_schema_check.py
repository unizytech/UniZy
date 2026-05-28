#!/usr/bin/env python3
"""
Comprehensive Database Schema Verification

Systematically verifies every table and column in the live database
against backend/supabase/schema_enhanced.sql
"""

from supabase import create_client
import re
from collections import defaultdict

SUPABASE_URL = "https://xyhzvokuxzwcmdefbhcn.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5aHp2b2t1eHp3Y21kZWZiaGNuIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTk5MzAyNywiZXhwIjoyMDc3NTY5MDI3fQ.T5EgNfpKJwbzAFsAp4pFtwEA0x-jO-EqcglxqEQiHzo"

def parse_schema_file():
    """Parse schema_enhanced.sql to extract table definitions"""
    schema_path = "/Users/karthi/Documents/AI Projects/AI-live-recorder/backend/supabase/schema_enhanced.sql"

    with open(schema_path, 'r') as f:
        content = f.read()

    # Extract CREATE TABLE statements
    table_pattern = r'CREATE TABLE\s+(\w+)\s*\((.*?)\);'
    tables = {}

    for match in re.finditer(table_pattern, content, re.DOTALL | re.IGNORECASE):
        table_name = match.group(1)
        table_body = match.group(2)

        # Extract column names from table body
        # Look for lines like: column_name TYPE constraints,
        column_pattern = r'^\s*(\w+)\s+(?:UUID|VARCHAR|TEXT|INTEGER|BIGINT|BOOLEAN|TIMESTAMP|JSONB|NUMERIC|DECIMAL)'
        columns = []

        for line in table_body.split('\n'):
            col_match = re.match(column_pattern, line.strip(), re.IGNORECASE)
            if col_match:
                col_name = col_match.group(1)
                # Skip constraint keywords
                if col_name.upper() not in ['PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK', 'CONSTRAINT', 'INDEX']:
                    columns.append(col_name)

        tables[table_name] = sorted(columns)

    return tables

def get_live_table_columns(supabase, table_name):
    """Get column names from live database table"""
    try:
        # First, try to get data
        response = supabase.table(table_name).select('*').limit(1).execute()

        if response.data and len(response.data) > 0:
            return sorted(list(response.data[0].keys())), 'from_data'

        # If no data, try to trigger an error that reveals columns
        try:
            supabase.table(table_name).insert({'__invalid_col__': 'test'}).execute()
        except Exception as e:
            error_msg = str(e)
            # The error message might contain schema information
            # For now, return empty if we can't determine
            return [], 'empty_table'

        return [], 'empty_table'

    except Exception as e:
        return None, f'error: {str(e)[:100]}'

def verify_all_tables():
    """Main verification function"""
    print("=" * 100)
    print("COMPREHENSIVE DATABASE SCHEMA VERIFICATION")
    print("=" * 100)
    print()

    # Parse schema file
    print("Step 1: Parsing schema_enhanced.sql...")
    expected_schema = parse_schema_file()
    print(f"✅ Found {len(expected_schema)} table definitions in schema file")
    print()

    # Connect to database
    print("Step 2: Connecting to Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    print("✅ Connected successfully")
    print()

    # Get all live tables
    print("Step 3: Discovering live tables...")
    all_tables = set(expected_schema.keys())

    # Try to query each expected table
    live_tables = {}
    for table in all_tables:
        try:
            supabase.table(table).select('*', count='exact').limit(0).execute()
            live_tables[table] = True
        except:
            live_tables[table] = False

    print(f"✅ Checked {len(all_tables)} expected tables")
    print()

    # Verification
    print("=" * 100)
    print("DETAILED TABLE-BY-TABLE VERIFICATION")
    print("=" * 100)
    print()

    results = {
        'perfect_match': [],
        'missing_tables': [],
        'column_mismatch': [],
        'empty_unverified': []
    }

    for table_name in sorted(expected_schema.keys()):
        print(f"{'─' * 100}")
        print(f"TABLE: {table_name}")
        print(f"{'─' * 100}")

        # Check if table exists
        if not live_tables.get(table_name):
            print(f"❌ TABLE DOES NOT EXIST IN DATABASE")
            results['missing_tables'].append(table_name)
            print()
            continue

        print(f"✅ Table exists")

        # Get expected columns
        expected_cols = expected_schema[table_name]
        print(f"\n📋 Expected columns ({len(expected_cols)}):")
        for col in expected_cols:
            print(f"    - {col}")

        # Get live columns
        live_cols, source = get_live_table_columns(supabase, table_name)

        if live_cols is None:
            print(f"\n❌ Error retrieving columns: {source}")
            results['column_mismatch'].append((table_name, 'error', source))
            print()
            continue

        if source == 'empty_table':
            print(f"\n⚠️  Table is empty - cannot verify columns via Supabase API")
            print(f"   (This is a limitation of the Supabase REST API)")
            results['empty_unverified'].append(table_name)
            print()
            continue

        print(f"\n📊 Live columns ({len(live_cols)}) [{source}]:")
        for col in live_cols:
            print(f"    - {col}")

        # Compare
        expected_set = set(expected_cols)
        live_set = set(live_cols)

        missing = expected_set - live_set
        extra = live_set - expected_set

        if missing or extra:
            print(f"\n⚠️  COLUMN MISMATCH:")
            if missing:
                print(f"    Missing in database: {', '.join(sorted(missing))}")
            if extra:
                print(f"    Extra in database: {', '.join(sorted(extra))}")
            results['column_mismatch'].append((table_name, missing, extra))
        else:
            print(f"\n✅ PERFECT MATCH - All columns present and correct")
            results['perfect_match'].append(table_name)

        print()

    # Summary
    print("=" * 100)
    print("VERIFICATION SUMMARY")
    print("=" * 100)
    print()

    print(f"✅ Perfect Match ({len(results['perfect_match'])} tables):")
    for table in results['perfect_match']:
        print(f"    ✓ {table}")
    print()

    if results['empty_unverified']:
        print(f"⚠️  Empty Tables - Cannot Verify Columns ({len(results['empty_unverified'])} tables):")
        for table in results['empty_unverified']:
            print(f"    ⚠ {table}")
        print()

    if results['missing_tables']:
        print(f"❌ Missing Tables ({len(results['missing_tables'])} tables):")
        for table in results['missing_tables']:
            print(f"    ✗ {table}")
        print()

    if results['column_mismatch']:
        print(f"⚠️  Column Mismatches ({len(results['column_mismatch'])} tables):")
        for table, missing, extra in results['column_mismatch']:
            if isinstance(missing, str):
                print(f"    ⚠ {table}: {missing}")
            else:
                status = []
                if missing:
                    status.append(f"missing: {', '.join(sorted(missing))}")
                if extra:
                    status.append(f"extra: {', '.join(sorted(extra))}")
                print(f"    ⚠ {table}: {'; '.join(status)}")
        print()

    # Overall status
    total_tables = len(expected_schema)
    verified_ok = len(results['perfect_match'])

    print("=" * 100)
    print(f"OVERALL STATUS: {verified_ok}/{total_tables} tables verified as correct")

    if results['empty_unverified']:
        print(f"Note: {len(results['empty_unverified'])} empty tables could not be verified via API")

    if verified_ok == total_tables and not results['missing_tables'] and not results['column_mismatch']:
        print("\n🎉 ALL VERIFIED TABLES MATCH schema_enhanced.sql!")
    else:
        print("\n⚠️  Some inconsistencies found - see details above")

    print("=" * 100)

    return results

if __name__ == "__main__":
    verify_all_tables()
