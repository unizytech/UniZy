"""
Test script for Doctor Management API endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_get_doctors():
    """Test GET /api/v1/doctors"""
    print("\n=== Test 1: GET /api/v1/doctors ===")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/doctors", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Doctor count: {data['count']}")
            if data['doctors']:
                print(f"\nFirst doctor:")
                print(json.dumps(data['doctors'][0], indent=2))
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_get_doctor_by_id():
    """Test GET /api/v1/doctors/{id}"""
    print("\n=== Test 2: GET /api/v1/doctors/{id} ===")
    doctor_id = "a1b2c3d4-e5f6-7890-abcd-111111111111"  # Dr. Sarah Johnson
    try:
        response = requests.get(f"{BASE_URL}/api/v1/doctors/{doctor_id}", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Doctor: {data['doctor']['full_name']} ({data['doctor']['specialization']})")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_search_doctors():
    """Test GET /api/v1/doctors/search?q=query"""
    print("\n=== Test 3: GET /api/v1/doctors/search ===")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/doctors/search?q=sarah", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Query: {data['query']}")
            print(f"Results: {data['count']}")
            if data['doctors']:
                for doctor in data['doctors']:
                    print(f"  - {doctor['full_name']} ({doctor['email']})")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

def test_get_doctor_configurations():
    """Test GET /api/v1/doctors/{id}/configurations"""
    print("\n=== Test 4: GET /api/v1/doctors/{id}/configurations ===")
    doctor_id = "a1b2c3d4-e5f6-7890-abcd-111111111111"
    try:
        response = requests.get(f"{BASE_URL}/api/v1/doctors/{doctor_id}/configurations", timeout=15)
        print(f"Status: {response.status_code}")
        if response.ok:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Doctor: {data['doctor']['full_name']}")
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
    print("Doctor Management API Test Suite")
    print("=" * 60)

    test_health_check()
    test_get_doctors()
    test_get_doctor_by_id()
    test_search_doctors()
    test_get_doctor_configurations()

    print("\n" + "=" * 60)
    print("Tests completed")
    print("=" * 60)
