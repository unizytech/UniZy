#!/usr/bin/env python3
"""
Apply migration to fix validate_segment_configuration RPC function.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Read migration file
migration_file = Path(__file__).parent / "supabase" / "migrations" / "20251124000100_fix_validate_segment_configuration_rpc.sql"

print(f"📂 Reading migration file: {migration_file}")

if not migration_file.exists():
    print(f"❌ Migration file not found: {migration_file}")
    sys.exit(1)

migration_sql = migration_file.read_text()

print("🔄 Applying migration...")
print("=" * 80)

try:
    # Execute the migration
    result = supabase.rpc("exec_sql", {"sql": migration_sql}).execute()

    print("✅ Migration applied successfully!")
    print("=" * 80)
    print("\n📋 Migration Summary:")
    print("  - Dropped old validate_segment_configuration RPC function")
    print("  - Created new template-based validate_segment_configuration RPC function")
    print("  - Function now validates across activated templates (counsellor_templates junction)")
    print("  - No longer references dropped doctor_segment_configurations table")

except Exception as e:
    print(f"❌ Error applying migration: {e}")
    print("\nTrying alternative method (direct SQL execution)...")

    # Split migration into statements
    statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]

    success_count = 0
    error_count = 0

    for i, statement in enumerate(statements, 1):
        if not statement:
            continue

        print(f"\n[{i}/{len(statements)}] Executing statement...")
        try:
            # Use PostgREST query
            result = supabase.postgrest.rpc("exec", {"query": statement}).execute()
            success_count += 1
            print(f"  ✅ Success")
        except Exception as stmt_error:
            error_count += 1
            print(f"  ⚠️ Error: {stmt_error}")

    print("\n" + "=" * 80)
    print(f"📊 Results: {success_count} succeeded, {error_count} failed")

    if error_count > 0:
        print("\n⚠️ Manual application required:")
        print(f"   psql [connection-string] -f {migration_file}")
        sys.exit(1)
