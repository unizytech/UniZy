"""
Test script for Counsellor Template Activation and Segment Management

Tests:
1. Activate template for a counsellor
2. Load segments for the activated template
3. Move segments between categories
4. Update segment configuration (brevity, terminology)
5. Request new segment (submit to admin for approval)
6. Cancel segment request

Usage:
    python test_doctor_activation.py
"""

import requests
import json
from typing import Dict, Any, List

# Configuration
API_BASE_URL = "http://localhost:8000"
DOCTOR_ID = "a1b2c3d4-e5f6-7890-abcd-555555555555"
CONSULTATION_TYPE_CODE = "OP"
TEMPLATE_CODE = "OP_CORE"
TEMPLATE_NAME = "My OP Template"  # Custom name given when activating template

def print_response(title: str, response: requests.Response):
    """Print formatted response"""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")
    print(f"Status Code: {response.status_code}")
    print(f"URL: {response.url}")

    if response.status_code < 400:
        try:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
        except:
            print(f"Response: {response.text}")
    else:
        print(f"Error: {response.text}")

def test_1_activate_template():
    """Test 1: Activate template for counsellor"""
    print("\n" + "="*80)
    print("TEST 1: Activate Template")
    print("="*80)

    url = f"{API_BASE_URL}/api/v1/summary/templates/{CONSULTATION_TYPE_CODE}/activate/{TEMPLATE_CODE}"
    params = {"counsellor_id": DOCTOR_ID}

    response = requests.post(url, params=params)
    print_response("Activate Template Response", response)

    return response.status_code == 200

def test_2_load_segments():
    """Test 2: Load segments for consultation type"""
    print("\n" + "="*80)
    print("TEST 2: Load Segments")
    print("="*80)

    url = f"{API_BASE_URL}/api/v1/summary/segments/{CONSULTATION_TYPE_CODE}"
    params = {
        "counsellor_id": DOCTOR_ID,
        "mode": "full"
    }

    response = requests.get(url, params=params)
    print_response("Load Segments Response", response)

    if response.status_code == 200:
        data = response.json()
        segments = data.get("segments", [])

        # Count segments by category
        core = [s for s in segments if s.get("default_category") == "core"]
        additional = [s for s in segments if s.get("default_category") == "additional"]
        excluded = [s for s in segments if s.get("default_category") == "excluded"]

        print(f"\nSegment Summary:")
        print(f"  CORE: {len(core)} segments")
        print(f"  ADDITIONAL: {len(additional)} segments")
        print(f"  EXCLUDED: {len(excluded)} segments")
        print(f"  TOTAL: {len(segments)} segments")

        # Print first 3 segments
        print(f"\nFirst 3 segments:")
        for i, seg in enumerate(segments[:3]):
            print(f"  {i+1}. {seg.get('segment_name')} ({seg.get('segment_code')}) - {seg.get('default_category')}")

        return segments

    return []

def test_3_move_segment(segments: List[Dict[str, Any]]):
    """Test 3: Move a segment between categories"""
    print("\n" + "="*80)
    print("TEST 3: Move Segment")
    print("="*80)

    if not segments:
        print("No segments available to move. Skipping test.")
        return False

    # Find first CORE segment to move to ADDITIONAL
    core_segment = next((s for s in segments if s.get("default_category") == "core"), None)

    if not core_segment:
        print("No CORE segments found. Skipping test.")
        return False

    segment_code = core_segment.get("segment_code")
    print(f"Moving segment: {core_segment.get('segment_name')} ({segment_code}) from CORE to ADDITIONAL")

    url = f"{API_BASE_URL}/api/v1/summary/segments/move"
    params = {
        "counsellor_id": DOCTOR_ID,
        "template_name": TEMPLATE_NAME
    }
    payload = {
        "segment_code": segment_code,
        "new_category": "additional"
    }

    response = requests.post(url, params=params, json=payload)
    print_response("Move Segment Response", response)

    # Move it back
    if response.status_code == 200:
        print(f"\nMoving segment back to CORE...")
        payload["new_category"] = "core"
        response2 = requests.post(url, params=params, json=payload)
        print_response("Move Segment Back Response", response2)

    return response.status_code == 200

def test_4_update_segment_config(segments: List[Dict[str, Any]]):
    """Test 4: Update segment configuration"""
    print("\n" + "="*80)
    print("TEST 4: Update Segment Configuration")
    print("="*80)

    if not segments:
        print("No segments available to update. Skipping test.")
        return False

    segment = segments[0]
    segment_code = segment.get("segment_code")

    print(f"Updating configuration for: {segment.get('segment_name')} ({segment_code})")

    url = f"{API_BASE_URL}/api/v1/summary/segments/{segment_code}"
    params = {
        "counsellor_id": DOCTOR_ID,
        "template_name": TEMPLATE_NAME
    }
    payload = {
        "brevity_level": "detailed",
        "terminology_style": "simple_terms"
    }

    response = requests.put(url, params=params, json=payload)
    print_response("Update Segment Config Response", response)

    return response.status_code == 200

def test_5_request_new_segment():
    """Test 5: Request new segment (submit to admin for approval)"""
    print("\n" + "="*80)
    print("TEST 5: Request New Segment")
    print("="*80)

    url = f"{API_BASE_URL}/api/v1/summary/segments/request"
    params = {
        "template_code": TEMPLATE_CODE,
        "counsellor_id": DOCTOR_ID
    }
    payload = {
        "segment_name": "Test Segment Custom",
        "description": "This is a test segment request from the automated test script to extract custom information",
        "default_category": "additional",
        "default_brevity": "balanced",
        "default_terminology": "medical_terms"
    }

    response = requests.post(url, params=params, json=payload)
    print_response("Request New Segment Response", response)

    return response.status_code == 200

def test_6_list_pending_requests():
    """Test 6: List pending segment requests"""
    print("\n" + "="*80)
    print("TEST 6: List Pending Segment Requests")
    print("="*80)

    url = f"{API_BASE_URL}/api/v1/summary/admin/segments/pending"

    response = requests.get(url)
    print_response("Pending Segment Requests Response", response)

    if response.status_code == 200:
        data = response.json()
        requests_list = data.get("requests", [])
        print(f"\nTotal pending requests: {len(requests_list)}")

        for i, req in enumerate(requests_list[:5]):
            print(f"  {i+1}. {req.get('segment_name')} ({req.get('segment_code')}) - Status: {req.get('status')}")

    return response.status_code == 200

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("COUNSELLOR TEMPLATE ACTIVATION AND SEGMENT MANAGEMENT TEST SUITE")
    print("="*80)
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Counsellor ID: {DOCTOR_ID}")
    print(f"Consultation Type: {CONSULTATION_TYPE_CODE}")
    print(f"Template Code: {TEMPLATE_CODE}")

    results = {}

    # Test 1: Activate template
    results["activate_template"] = test_1_activate_template()

    # Test 2: Load segments
    segments = test_2_load_segments()
    results["load_segments"] = len(segments) > 0

    # Test 3: Move segment
    results["move_segment"] = test_3_move_segment(segments)

    # Test 4: Update segment config
    results["update_segment_config"] = test_4_update_segment_config(segments)

    # Test 5: Request new segment
    results["request_new_segment"] = test_5_request_new_segment()

    # Test 6: List pending requests
    results["list_pending_requests"] = test_6_list_pending_requests()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {test_name}")

    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)

    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    return all(results.values())

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
