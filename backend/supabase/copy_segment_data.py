#!/usr/bin/env python3
"""
Copy segment-related tables from production Supabase to preview branch.
This includes segment_definitions, consultation_type_segments, and template_segments.
"""

import sys
from supabase import create_client

# Production (main branch)
PROD_URL = "https://maindb.1hat.ai"
PROD_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh5aHp2b2t1eHp3Y21kZWZiaGNuIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczMDQ1MzQyNywiZXhwIjoyMDQ2MDI5NDI3fQ.vKZy_kPfOyW8IJrqwz8eG7xIjGH_nkgJDfBSN6xqTsc"

# Preview (main-dev branch)
PREVIEW_URL = "https://maindevdb.1hat.ai"
PREVIEW_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNpY3ZncG9mcnB6Y2huanVhcXhhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc4NDY4MSwiZXhwIjoyMDc5MzYwNjgxfQ.i8LEYD3rP3jTtguOVs7_LFFnY6ut9m4ijO1q-QT3VJ8"

# Tables to copy (in dependency order)
TABLES = [
    {
        "name": "segment_definitions",
        "filter": "is_active.eq.true",  # Only copy active segments
        "description": "Active segment definitions with prompts and schemas"
    },
    {
        "name": "consultation_type_segments",
        "filter": None,
        "description": "Segment configurations per consultation type (junction table)"
    },
    {
        "name": "template_segments",
        "filter": None,
        "description": "Segment configurations per template (junction table)"
    }
]

def copy_table(prod_client, preview_client, table_config):
    """Copy data from one table to another"""
    table_name = table_config["name"]
    filter_expr = table_config.get("filter")

    print(f"\n{'='*60}")
    print(f"Copying {table_name}")
    print(f"Description: {table_config['description']}")
    print(f"{'='*60}")

    try:
        # Fetch all data from production
        query = prod_client.table(table_name).select("*")
        if filter_expr:
            # Apply filter if specified
            parts = filter_expr.split(".")
            if len(parts) == 3:
                column, operator, value = parts
                if operator == "eq":
                    query = query.eq(column, value == "true")

        response = query.execute()
        data = response.data

        if not data:
            print(f"  ⚠️  No data found in production")
            return 0

        print(f"  📊 Found {len(data)} rows in production")

        # Insert into preview (batch insert)
        print(f"  ⏳ Inserting into preview branch...")
        preview_client.table(table_name).insert(data).execute()
        print(f"  ✅ Successfully copied {len(data)} rows")

        return len(data)

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return 0

def main():
    print("\n" + "="*60)
    print("SEGMENT DATA COPY: Production → Preview Branch")
    print("="*60)

    try:
        prod_client = create_client(PROD_URL, PROD_KEY)
        preview_client = create_client(PREVIEW_URL, PREVIEW_KEY)

        total_rows = 0
        successful_tables = 0

        for table_config in TABLES:
            rows_copied = copy_table(prod_client, preview_client, table_config)
            if rows_copied > 0:
                successful_tables += 1
                total_rows += rows_copied

        print(f"\n" + "="*60)
        print(f"✅ COPY COMPLETED")
        print(f"="*60)
        print(f"  Tables copied: {successful_tables}/{len(TABLES)}")
        print(f"  Total rows: {total_rows}")
        print(f"  Preview branch ready for testing!")
        print("="*60 + "\n")

        return 0

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
