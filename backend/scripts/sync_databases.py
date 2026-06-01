#!/usr/bin/env python3
"""
Database sync script to copy data from main-dev to main Supabase project.
"""
import os
import json
from supabase import create_client

# Source (main-dev)
SOURCE_URL = "https://sicvgpofrpzchnjuaqxa.supabase.co"
SOURCE_KEY = os.environ.get("SOURCE_SUPABASE_KEY")

# Target (main)
TARGET_URL = "https://xyhzvokuxzwcmdefbhcn.supabase.co"
TARGET_KEY = os.environ.get("TARGET_SUPABASE_KEY")

# Tables to sync in order (respecting foreign key dependencies)
TABLES_TO_SYNC = [
    # Base tables (no foreign keys)
    "schools",
    "processing_modes",
    "consultation_types",

    # Tables with school FK
    "counsellors",
    "assistants",
    "api_clients",

    # Tables with counsellor FK
    "students",

    # Prompt system tables
    "segment_definitions",
    "system_prompt_components",
    "system_prompt_configurations",
    "system_prompt_config_components",

    # Template tables
    "templates",
    "template_segments",
    "counsellor_templates",
    "assistant_templates",

    # Consultation type junction tables
    "consultation_type_segments",
    "consultation_type_system_prompts",

    # Medicine/Investigation tables
    "counsellor_medicines",
    "counsellor_investigations",
    "hospital_medicine_list",
    "hospital_investigation_list",
    "medicine_list_uploads",
    "investigation_list_uploads",

    # Other tables
    "assistant_counsellors",
    "intervention_definitions",
]

def sync_table(source_client, target_client, table_name: str, batch_size: int = 1000):
    """Sync a single table from source to target."""
    print(f"\n{'='*60}")
    print(f"Syncing table: {table_name}")
    print(f"{'='*60}")

    try:
        # Get all data from source
        print(f"  Fetching data from source...")
        response = source_client.table(table_name).select("*").execute()
        data = response.data

        if not data:
            print(f"  No data found in source table")
            return True

        print(f"  Found {len(data)} records")

        # Clear target table
        print(f"  Clearing target table...")
        # Use a dummy condition to delete all (Supabase requires a filter)
        target_client.table(table_name).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

        # Insert data in batches
        print(f"  Inserting data into target...")
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            target_client.table(table_name).insert(batch).execute()
            print(f"    Inserted batch {i//batch_size + 1} ({len(batch)} records)")

        print(f"  ✅ Successfully synced {len(data)} records")
        return True

    except Exception as e:
        print(f"  ❌ Error syncing {table_name}: {str(e)}")
        return False

def main():
    if not SOURCE_KEY or not TARGET_KEY:
        print("Error: Set SOURCE_SUPABASE_KEY and TARGET_SUPABASE_KEY environment variables")
        print("These should be the service_role keys for each project")
        return

    source_client = create_client(SOURCE_URL, SOURCE_KEY)
    target_client = create_client(TARGET_URL, TARGET_KEY)

    print("Starting database sync...")
    print(f"Source: {SOURCE_URL}")
    print(f"Target: {TARGET_URL}")

    results = {}
    for table in TABLES_TO_SYNC:
        success = sync_table(source_client, target_client, table)
        results[table] = "✅" if success else "❌"

    print("\n" + "="*60)
    print("SYNC SUMMARY")
    print("="*60)
    for table, status in results.items():
        print(f"  {status} {table}")

if __name__ == "__main__":
    main()
