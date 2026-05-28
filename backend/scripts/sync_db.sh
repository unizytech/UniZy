#!/bin/bash
# Database sync script: main-dev → main
#
# INSTRUCTIONS:
# 1. Get your database passwords from Supabase Dashboard:
#    - Project Settings → Database → Connection string → Copy password
# 2. Set the passwords below
# 3. Run: chmod +x sync_db.sh && ./sync_db.sh

# ============================================
# CONFIGURE THESE - Get passwords from Supabase Dashboard
# ============================================
SOURCE_PASSWORD="YOUR_MAIN_DEV_DB_PASSWORD"  # main-dev project
TARGET_PASSWORD="YOUR_MAIN_DB_PASSWORD"  # main project

# ============================================
# Connection strings (using transaction pooler for compatibility)
# ============================================
SOURCE_REF="sicvgpofrpzchnjuaqxa"  # main-dev
TARGET_REF="xyhzvokuxzwcmdefbhcn"  # main

# Using direct connection (port 5432) for pg_dump compatibility
SOURCE_DB="postgresql://postgres:${SOURCE_PASSWORD}@db.${SOURCE_REF}.supabase.co:5432/postgres"
TARGET_DB="postgresql://postgres:${TARGET_PASSWORD}@db.${TARGET_REF}.supabase.co:5432/postgres"

# ============================================
# Tables to sync (in dependency order)
# ============================================
TABLES=(
    # Base tables
    "hospitals"
    "processing_modes"
    "consultation_types"

    # Core entities
    "doctors"
    "nurses"
    "api_clients"
    "patients"

    # Prompt system
    "segment_definitions"
    "system_prompt_components"
    "system_prompt_configurations"
    "system_prompt_config_components"

    # Templates
    "templates"
    "template_segments"
    "doctor_templates"
    "nurse_templates"

    # Junction tables
    "consultation_type_segments"
    "consultation_type_system_prompts"

    # Medicine/Investigation
    "doctor_medicines"
    "doctor_investigations"
    "hospital_medicine_list"
    "hospital_investigation_list"
    "medicine_list_uploads"
    "investigation_list_uploads"

    # Other
    "nurse_doctors"
    "intervention_definitions"
)

# ============================================
# Sync function
# ============================================
sync_table() {
    local table=$1
    echo ""
    echo "============================================"
    echo "Syncing: $table"
    echo "============================================"

    # Step 1: Truncate target table
    echo "  Truncating target..."
    psql "$TARGET_DB" -c "TRUNCATE public.$table CASCADE;" 2>&1

    # Step 2: Export from source and import to target
    echo "  Copying data..."
    pg_dump "$SOURCE_DB" \
        --table="public.$table" \
        --data-only \
        --disable-triggers \
        --no-owner \
        --no-acl \
        2>/dev/null | \
    psql "$TARGET_DB" 2>&1

    if [ $? -eq 0 ]; then
        echo "✅ $table synced successfully"
    else
        echo "❌ $table sync failed"
    fi
}

# ============================================
# Main execution
# ============================================
echo "================================================"
echo "Database Sync: main-dev → main"
echo "================================================"
echo "Source: $SOURCE_REF (main-dev)"
echo "Target: $TARGET_REF (main)"
echo ""

# Check if passwords are set
if [[ "$SOURCE_PASSWORD" == "YOUR_MAIN_DEV_DB_PASSWORD" ]] || [[ "$TARGET_PASSWORD" == "YOUR_MAIN_DB_PASSWORD" ]]; then
    echo "❌ ERROR: Please set the database passwords in this script"
    echo ""
    echo "Get passwords from Supabase Dashboard:"
    echo "  1. Go to Project Settings → Database"
    echo "  2. Copy the password from the connection string"
    exit 1
fi

# Check if psql and pg_dump are available
if ! command -v psql &> /dev/null; then
    echo "❌ ERROR: psql not found. Install PostgreSQL client tools."
    exit 1
fi

if ! command -v pg_dump &> /dev/null; then
    echo "❌ ERROR: pg_dump not found. Install PostgreSQL client tools."
    exit 1
fi

# Sync each table
for table in "${TABLES[@]}"; do
    sync_table "$table"
done

echo ""
echo "================================================"
echo "Sync Complete!"
echo "================================================"
