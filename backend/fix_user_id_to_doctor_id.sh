#!/bin/bash
# Complete fix for user_id → doctor_id migration
# This script fixes ALL occurrences across the codebase

set -e

echo "🔧 Complete user_id → doctor_id Migration"
echo "=========================================="
echo ""

# Navigate to backend directory
cd "$(dirname "$0")"

# Create backups
echo "📦 Creating backups..."
cp routers/summary.py routers/summary.py.backup_user_id
cp services/uuid_utils.py services/uuid_utils.py.backup_user_id
cp services/gemini_service.py services/gemini_service.py.backup_user_id
cp services/segment_registry.py services/segment_registry.py.backup_user_id
echo "✅ Backups created"
echo ""

# ============================================================================
# Fix 1: routers/summary.py
# ============================================================================
echo "🔄 Fixing routers/summary.py..."

# Fix import
sed -i '' 's/from services.uuid_utils import normalize_user_id/from services.uuid_utils import normalize_doctor_id/' routers/summary.py

# Fix all normalize_user_id() calls → normalize_doctor_id()
sed -i '' 's/normalize_user_id(/normalize_doctor_id(/g' routers/summary.py

# Fix variable name mismatches in line 203: user_id → doctor_id
sed -i '' 's/if user_id else None/if doctor_id else None/g' routers/summary.py

# Fix variable name user_uuid → doctor_uuid in function calls
sed -i '' 's/user_id=user_uuid/doctor_id=doctor_uuid/g' routers/summary.py

# Fix validate_segment_configuration(user_uuid) → (doctor_uuid)
sed -i '' 's/validate_segment_configuration(user_uuid)/validate_segment_configuration(doctor_uuid)/g' routers/summary.py

# Fix request.user_id → request.doctor_id (ExtractionRequest model field)
sed -i '' 's/user_id=request\.user_id/doctor_id=request.doctor_id/g' routers/summary.py

# Fix JSON responses: "user_id" → "doctor_id"
sed -i '' 's/"user_id": request\.user_id/"doctor_id": request.doctor_id/g' routers/summary.py

# Fix docstring references: User ID → Doctor ID
sed -i '' 's/- `user_id`: Optional user ID/- `doctor_id`: Optional doctor ID/g' routers/summary.py
sed -i '' 's/- `user_id`: User ID (required)/- `doctor_id`: Doctor ID (required)/g' routers/summary.py
sed -i '' 's/"user_id": "user-123"/"doctor_id": "doctor-123"/g' routers/summary.py

echo "✅ routers/summary.py fixed"

# ============================================================================
# Fix 2: services/uuid_utils.py
# ============================================================================
echo ""
echo "🔄 Fixing services/uuid_utils.py..."

# Rename function
sed -i '' 's/def normalize_user_id(user_id: Optional\[str\])/def normalize_doctor_id(doctor_id: Optional[str])/' services/uuid_utils.py

# Update docstring
sed -i '' 's/Convert a string user_id to a valid UUID/Convert a string doctor_id to a valid UUID/' services/uuid_utils.py
sed -i '' 's/user_id: User identifier/doctor_id: Doctor identifier/' services/uuid_utils.py

# Update function body parameter references
sed -i '' 's/if user_id is None:/if doctor_id is None:/' services/uuid_utils.py
sed -i '' 's/return uuid.UUID(user_id)/return uuid.UUID(doctor_id)/' services/uuid_utils.py
sed -i '' 's/return uuid.uuid5(USER_NAMESPACE, user_id)/return uuid.uuid5(USER_NAMESPACE, doctor_id)/' services/uuid_utils.py

# Update docstring examples
sed -i '' 's/>>> normalize_user_id(None)/>>> normalize_doctor_id(None)/' services/uuid_utils.py
sed -i '' "s/>>> normalize_user_id('550e8400/>>> normalize_doctor_id('550e8400/" services/uuid_utils.py
sed -i '' "s/>>> normalize_user_id('test-user-123')/>>> normalize_doctor_id('test-doctor-123')/" services/uuid_utils.py
sed -i '' 's/deterministic-uuid-for-test-user-123/deterministic-uuid-for-test-doctor-123/' services/uuid_utils.py

# Update ensure_uuid function to use new name
sed -i '' 's/return normalize_user_id(value)/return normalize_doctor_id(value)/' services/uuid_utils.py
sed -i '' 's/return normalize_user_id(None)/return normalize_doctor_id(None)/' services/uuid_utils.py

# Update namespace comment
sed -i '' 's/# Namespace UUID for deterministic user ID generation/# Namespace UUID for deterministic doctor ID generation/' services/uuid_utils.py
sed -i '' 's/# Using DNS namespace as a base for user-related UUIDs/# Using DNS namespace as a base for doctor-related UUIDs/' services/uuid_utils.py
sed -i '' "s/USER_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'ai-live-recorder.user-ids')/DOCTOR_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'ai-live-recorder.doctor-ids')/" services/uuid_utils.py
sed -i '' 's/USER_NAMESPACE/DOCTOR_NAMESPACE/g' services/uuid_utils.py

# Update other function names and descriptions
sed -i '' 's/def user_id_to_string(user_uuid: uuid.UUID)/def doctor_id_to_string(doctor_uuid: uuid.UUID)/' services/uuid_utils.py
sed -i '' 's/user_uuid: UUID object/doctor_uuid: UUID object/' services/uuid_utils.py
sed -i '' 's/return str(user_uuid)/return str(doctor_uuid)/' services/uuid_utils.py
sed -i '' "s/>>> user_id_to_string(UUID('550e8400/>>> doctor_id_to_string(UUID('550e8400/" services/uuid_utils.py

sed -i '' 's/def generate_anonymous_user_id()/def generate_anonymous_doctor_id()/' services/uuid_utils.py
sed -i '' 's/Generate a random UUID for anonymous users/Generate a random UUID for anonymous doctors/' services/uuid_utils.py
sed -i '' 's/>>> generate_anonymous_user_id()/>>> generate_anonymous_doctor_id()/' services/uuid_utils.py

sed -i '' 's/def generate_deterministic_user_id(identifier: str)/def generate_deterministic_doctor_id(identifier: str)/' services/uuid_utils.py
sed -i '' 's/>>> generate_deterministic_user_id/>>> generate_deterministic_doctor_id/g' services/uuid_utils.py

# Update module docstring
sed -i '' 's/Provides functions to convert string user IDs to valid UUIDs/Provides functions to convert string doctor IDs to valid UUIDs/' services/uuid_utils.py
sed -i '' 's/UUID Normalization Utilities/Doctor ID UUID Normalization Utilities/' services/uuid_utils.py

echo "✅ services/uuid_utils.py fixed"

# ============================================================================
# Fix 3: services/gemini_service.py
# ============================================================================
echo ""
echo "🔄 Fixing services/gemini_service.py..."

# Fix extract_summary_dynamic function signature
sed -i '' 's/user_id: Optional\[str\] = None,/doctor_id: Optional[str] = None,/' services/gemini_service.py

# Fix docstring
sed -i '' 's/user_id: User ID for personalized configuration/doctor_id: Doctor ID for personalized configuration/' services/gemini_service.py

# Fix function body internal usage
# Line 1223: logger message
sed -i '' 's/user_id: {user_id}/doctor_id: {doctor_id}/' services/gemini_service.py

# Line 1228: user_uuid = uuid.UUID(user_id) → doctor_uuid = uuid.UUID(doctor_id)
sed -i '' 's/user_uuid = uuid.UUID(user_id) if user_id else None/doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None/' services/gemini_service.py

# Line 1233: user_id=user_uuid → doctor_id=doctor_uuid
sed -i '' 's/user_id=user_uuid,/doctor_id=doctor_uuid,/' services/gemini_service.py

echo "✅ services/gemini_service.py fixed"

# ============================================================================
# Fix 4: services/segment_registry.py
# ============================================================================
echo ""
echo "🔄 Fixing services/segment_registry.py..."

# Fix function parameters
sed -i '' 's/user_id: Optional\[uuid.UUID\] = None,/doctor_id: Optional[uuid.UUID] = None,/' services/segment_registry.py
sed -i '' 's/user_id: Optional\[uuid.UUID\],/doctor_id: Optional[uuid.UUID],/' services/segment_registry.py

# Fix docstrings
sed -i '' 's/user_id: User ID for personalized configuration/doctor_id: Doctor ID for personalized configuration/' services/segment_registry.py
sed -i '' 's/user_id: User ID for database validation/doctor_id: Doctor ID for database validation/' services/segment_registry.py

# Fix function call parameters
sed -i '' 's/user_id=user_id,/doctor_id=doctor_id,/' services/segment_registry.py

# Fix conditional checks
sed -i '' 's/if user_id:/if doctor_id:/' services/segment_registry.py
sed -i '' 's/validate_segment_configuration(user_id)/validate_segment_configuration(doctor_id)/' services/segment_registry.py

echo "✅ services/segment_registry.py fixed"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "=========================================="
echo "✅ Migration Complete!"
echo ""
echo "Files modified:"
echo "  - routers/summary.py"
echo "  - services/uuid_utils.py"
echo "  - services/gemini_service.py"
echo "  - services/segment_registry.py"
echo ""
echo "Backups saved with .backup_user_id extension"
echo ""
echo "⚠️  IMPORTANT NEXT STEPS:"
echo "1. Test all endpoints after migration"
echo "2. Update any remaining test files or documentation"
echo "3. Restart backend server"
echo ""
echo "🔍 Verify changes:"
echo "   # Should return NO results:"
echo "   grep -r 'user_id' backend/routers/summary.py backend/services/gemini_service.py backend/services/segment_registry.py"
echo ""
echo "   # Should return NO normalize_user_id:"
echo "   grep -r 'normalize_user_id' backend/services/ backend/routers/"
echo ""
