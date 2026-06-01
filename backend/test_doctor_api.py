"""
Test script for Counsellor Management API endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_get_counsellors():
    """Test GET /api/v1/counsellors"""
    print("\n=== Test 1: GET /api/v1/counsellors ===")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/counsellors", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Counsellor count: {data['count']}")
            if data['counsellors']:
                print(f"\nFirst counsellor:")
                print(json.dumps(data['counsellors'][0], indent=2))
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_get_counsellor_by_id():
    """Test GET /api/v1/counsellors/{id}"""
    print("\n=== Test 2: GET /api/v1/counsellors/{id} ===")
    counsellor_id = "a1b2c3d4-e5f6-7890-abcd-111111111111"  # Dr. Sarah Johnson
    try:
        response = requests.get(f"{BASE_URL}/api/v1/counsellors/{counsellor_id}", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Counsellor: {data['doctor']['full_name']} ({data['doctor']['specialization']})")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_search_counsellors():
    """Test GET /api/v1/counsellors/search?q=query"""
    print("\n=== Test 3: GET /api/v1/counsellors/search ===")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/counsellors/search?q=sarah", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Query: {data['query']}")
            print(f"Results: {data['count']}")
            if data['counsellors']:
                for doctor in data['counsellors']:
                    print(f"  - {doctor['full_name']} ({doctor['email']})")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_get_counsellor_configurations():
    """Test GET /api/v1/counsellors/{id}/configurations"""
    print("\n=== Test 4: GET /api/v1/counsellors/{id}/configurations ===")
    counsellor_id = "a1b2c3d4-e5f6-7890-abcd-111111111111"
    try:
        response = requests.get(f"{BASE_URL}/api/v1/counsellors/{counsellor_id}/configurations", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Counsellor: {data['doctor']['full_name']}")
            print(f"Global configs: {len(data['global_config'])}")
            print(f"Consultation configs: {list(data['consultation_configs'].keys())}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_health_check():
    """Test health check endpoint"""
    print("\n=== Test 0: Health Check ===")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Status: {response.status_code}")
        if response.ok:
            print(f"Response: {response.json()}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Counsellor Management API Test Suite")
    print("=" * 60)

    test_health_check()
    test_get_counsellors()
    test_get_counsellor_by_id()
    test_search_counsellors()
    test_get_counsellor_configurations()

    print("\n" + "=" * 60)
    print("Tests completed")
    print("=" * 60)
