#!/bin/bash
#
# Quick Curl-based Tests for Template & Processing Mode Refactoring
# Run this after backend is running on port 8000
#

set -e

BASE_URL="http://localhost:8000"
API_BASE="${BASE_URL}/api/v1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration - UPDATE THESE!
TEST_DOCTOR_ID="00000000-0000-0000-0000-000000000001"  # Replace with actual doctor UUID!
TEMPLATE_NAME="Default Template"  # Replace with actual template name!

echo -e "${BLUE}================================================="
echo "Backend Refactoring Endpoint Tests (curl)"
echo -e "=================================================${NC}\n"

echo -e "${YELLOW}⚠ Configuration:${NC}"
echo "  Base URL: ${BASE_URL}"
echo "  Doctor ID: ${TEST_DOCTOR_ID}"
echo "  Template Name: ${TEMPLATE_NAME}"
echo ""
echo -e "${YELLOW}⚠ Update TEST_DOCTOR_ID and TEMPLATE_NAME variables in this script!${NC}"
echo ""
read -p "Press Enter to continue..."

# ============================================================================
# Test 1: Processing Modes Endpoint (NEW)
# ============================================================================

echo -e "\n${BLUE}[TEST 1] GET /api/v1/summary/processing-modes${NC}"
echo "Testing NEW processing modes endpoint..."

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  "${API_BASE}/summary/processing-modes")

http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓ Status: 200 OK${NC}"
  echo "$body" | jq '.'

  count=$(echo "$body" | jq -r '.count')
  echo -e "${GREEN}✓ Found ${count} processing modes${NC}"
else
  echo -e "${RED}✗ Status: ${http_code}${NC}"
  echo "$body" | jq '.'
fi

# ============================================================================
# Test 2: Consultation Types
# ============================================================================

echo -e "\n${BLUE}[TEST 2] GET /api/v1/summary/consultation-types${NC}"

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  "${API_BASE}/summary/consultation-types")

http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓ Status: 200 OK${NC}"
  count=$(echo "$body" | jq -r '.count')
  echo -e "${GREEN}✓ Found ${count} consultation types${NC}"
  echo "$body" | jq -r '.consultation_types[] | "  • \(.type_name) (\(.type_code))"'
else
  echo -e "${RED}✗ Status: ${http_code}${NC}"
  echo "$body" | jq '.'
fi

# ============================================================================
# Test 3: Activated Templates
# ============================================================================

echo -e "\n${BLUE}[TEST 3] GET /api/v1/doctors/${TEST_DOCTOR_ID}/activated-templates${NC}"

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  "${API_BASE}/doctors/${TEST_DOCTOR_ID}/activated-templates")

http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓ Status: 200 OK${NC}"
  count=$(echo "$body" | jq -r '.count')
  echo -e "${GREEN}✓ Found ${count} activated templates${NC}"
  echo "$body" | jq -r '.templates[] | "  • \(.template_name) (Override: \(.template_name_override))"'

  # Extract first template name for later tests
  TEMPLATE_NAME=$(echo "$body" | jq -r '.templates[0].template_name_override')
  echo -e "${YELLOW}ℹ Using template: ${TEMPLATE_NAME}${NC}"
elif [ "$http_code" = "404" ]; then
  echo -e "${RED}✗ Doctor not found: ${TEST_DOCTOR_ID}${NC}"
  echo -e "${YELLOW}⚠ Update TEST_DOCTOR_ID in script with valid UUID${NC}"
  exit 1
else
  echo -e "${RED}✗ Status: ${http_code}${NC}"
  echo "$body" | jq '.'
fi

# ============================================================================
# Test 4: Extraction with template_name and processing_mode
# ============================================================================

echo -e "\n${BLUE}[TEST 4] POST /api/v1/summary/extract (with template_name & processing_mode)${NC}"

SAMPLE_TRANSCRIPT="Doctor: Good morning. How are you feeling today?
Patient: I've been having severe headaches for the past week.
Doctor: Can you describe the headaches?
Patient: They're mainly on the right side, throbbing pain, about 7/10 severity.
Doctor: I'll prescribe sumatriptan for migraine relief."

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X POST "${API_BASE}/summary/extract" \
  -H "Content-Type: application/json" \
  -d "{
    \"transcript\": \"${SAMPLE_TRANSCRIPT}\",
    \"doctor_id\": \"${TEST_DOCTOR_ID}\",
    \"template_name\": \"${TEMPLATE_NAME}\",
    \"processing_mode\": \"default\",
    \"mode\": \"core\"
  }")

http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓ Status: 200 OK${NC}"
  segment_count=$(echo "$body" | jq -r '.metadata.segment_count')
  template_used=$(echo "$body" | jq -r '.metadata.template_name')
  mode_used=$(echo "$body" | jq -r '.metadata.processing_mode')
  echo -e "${GREEN}✓ Extracted ${segment_count} segments${NC}"
  echo -e "${GREEN}✓ Template: ${template_used}${NC}"
  echo -e "${GREEN}✓ Processing mode: ${mode_used}${NC}"
else
  echo -e "${RED}✗ Status: ${http_code}${NC}"
  echo "$body" | jq '.'
fi

# ============================================================================
# Test 5: Progressive Extraction (CORE + ADDITIONAL)
# ============================================================================

echo -e "\n${BLUE}[TEST 5] Progressive Extraction (CORE + ADDITIONAL)${NC}"

echo "Step 1: Extract CORE segments..."
start_time=$(date +%s)

response_core=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X POST "${API_BASE}/summary/extract" \
  -H "Content-Type: application/json" \
  -d "{
    \"transcript\": \"${SAMPLE_TRANSCRIPT}\",
    \"doctor_id\": \"${TEST_DOCTOR_ID}\",
    \"template_name\": \"${TEMPLATE_NAME}\",
    \"processing_mode\": \"fast\",
    \"mode\": \"core\"
  }")

http_code_core=$(echo "$response_core" | grep "HTTP_CODE" | cut -d: -f2)
body_core=$(echo "$response_core" | sed '/HTTP_CODE/d')

core_time=$(($(date +%s) - start_time))

if [ "$http_code_core" = "200" ]; then
  core_count=$(echo "$body_core" | jq -r '.metadata.segment_count')
  echo -e "${GREEN}✓ CORE: ${core_count} segments (${core_time}s)${NC}"
else
  echo -e "${RED}✗ CORE failed: ${http_code_core}${NC}"
  echo "$body_core" | jq '.'
  exit 1
fi

echo "Step 2: Extract ADDITIONAL segments..."
start_time=$(date +%s)

response_add=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X POST "${API_BASE}/summary/extract" \
  -H "Content-Type: application/json" \
  -d "{
    \"transcript\": \"${SAMPLE_TRANSCRIPT}\",
    \"doctor_id\": \"${TEST_DOCTOR_ID}\",
    \"template_name\": \"${TEMPLATE_NAME}\",
    \"processing_mode\": \"fast\",
    \"mode\": \"additional\"
  }")

http_code_add=$(echo "$response_add" | grep "HTTP_CODE" | cut -d: -f2)
body_add=$(echo "$response_add" | sed '/HTTP_CODE/d')

add_time=$(($(date +%s) - start_time))

if [ "$http_code_add" = "200" ]; then
  add_count=$(echo "$body_add" | jq -r '.metadata.segment_count')
  echo -e "${GREEN}✓ ADDITIONAL: ${add_count} segments (${add_time}s)${NC}"

  total_time=$((core_time + add_time))
  total_count=$((core_count + add_count))
  echo -e "${GREEN}✓ Total: ${total_count} segments (${total_time}s)${NC}"
else
  echo -e "${RED}✗ ADDITIONAL failed: ${http_code_add}${NC}"
  echo "$body_add" | jq '.'
fi

# ============================================================================
# Test 6: Recording API with new template parameters
# ============================================================================

echo -e "\n${BLUE}[TEST 6] POST /api/v1/option1/recording/start (with template parameters)${NC}"

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
  -X POST "${API_BASE}/option1/recording/start" \
  -H "Content-Type: application/json" \
  -d "{
    \"doctor_id\": \"${TEST_DOCTOR_ID}\",
    \"template_name\": \"${TEMPLATE_NAME}\",
    \"processing_mode\": \"default\",
    \"extraction_mode\": \"core\",
    \"patient_id\": \"TEST_PATIENT_001\",
    \"transcription_engine\": \"gemini\",
    \"transcription_model\": \"gemini-2.5-flash\",
    \"chunk_duration_seconds\": 10
  }")

http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
  echo -e "${GREEN}✓ Status: 200 OK${NC}"
  correlation_id=$(echo "$body" | jq -r '.correlation_id')
  echo -e "${GREEN}✓ Session started: ${correlation_id}${NC}"
  echo -e "${GREEN}✓ New parameters accepted!${NC}"

  # Cleanup: Cancel test session
  echo "Cancelling test session..."
  cancel_response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
    -X POST "${API_BASE}/option1/recording/cancel" \
    -H "Content-Type: application/json" \
    -d "{\"correlation_id\": \"${correlation_id}\"}")

  cancel_code=$(echo "$cancel_response" | grep "HTTP_CODE" | cut -d: -f2)
  if [ "$cancel_code" = "200" ]; then
    echo -e "${GREEN}✓ Test session cancelled${NC}"
  fi
else
  echo -e "${RED}✗ Status: ${http_code}${NC}"
  echo "$body" | jq '.'
fi

# ============================================================================
# Summary
# ============================================================================

echo -e "\n${BLUE}================================================="
echo "Test Summary"
echo -e "=================================================${NC}"
echo -e "${GREEN}All endpoint tests completed!${NC}"
echo ""
echo "Next steps:"
echo "  1. Review test results above"
echo "  2. Run Python test script for detailed testing:"
echo "     python3 backend/test_refactoring_endpoints.py"
echo "  3. Test frontend components"
echo "  4. Perform end-to-end integration testing"
