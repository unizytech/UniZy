"""
PSG.mp3 Extraction Test Script

Tests the complete extraction pipeline with PSG.mp3 audio file via HTTP API.

Tests:
1. Start recording session
2. Upload audio chunk
3. Wait for transcription
4. Run extraction
5. Wait for background tasks
6. Verify all generated data:
   - Extraction (medical_extractions)
   - Consultation Insights
   - Triage
   - Assessments (5 types)
   - Interventions

Usage:
    cd backend
    source venv/bin/activate
    python tests/test_psg_extraction.py

Author: 1hat Health
"""

import asyncio
import base64
import httpx
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime

# Configuration
BACKEND_URL = "http://localhost:8000"
API_KEY = "ehr_PNUEhSQKwMZHg96fJCJMS7qZckm52FNarXI_0neFFdM"
AUDIO_FILE = Path(__file__).parent.parent.parent / "references" / "PSG.mp3"

# Test data
DOCTOR_ID = "3a913f3c-24d5-4c11-a968-52c8024de2db"  # Harish Kumar (Hospital: d9a4b166)
TEMPLATE_CODE = "OP_CORE"
PATIENT_ID = f"TEST_PSG_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    color = {
        "INFO": Colors.BLUE,
        "SUCCESS": Colors.GREEN,
        "ERROR": Colors.RED,
        "WARNING": Colors.YELLOW,
    }.get(level, "")
    print(f"[{timestamp}] [{color}{level}{Colors.END}] {message}")


def step(step_num: int, description: str):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}STEP {step_num}: {description}{Colors.END}")
    print(f"{'='*60}")


class ExtractionTester:
    def __init__(self):
        self.client = httpx.Client(
            timeout=300.0,  # 5 min timeout
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        self.correlation_id = None
        self.session_id = None
        self.submission_id = None
        self.extraction_id = None

    def check_backend(self) -> bool:
        """Check if backend is running"""
        try:
            response = self.client.get(f"{BACKEND_URL}/health")
            if response.status_code == 200:
                log("Backend is healthy", "SUCCESS")
                return True
        except Exception as e:
            log(f"Backend not reachable: {e}", "ERROR")
        return False

    def start_recording_session(self) -> bool:
        """Step 1: Start a recording session"""
        step(1, "Starting Recording Session")

        payload = {
            "doctor_id": DOCTOR_ID,
            "patient_id": PATIENT_ID,
            "template_code": TEMPLATE_CODE,
            "processing_mode": "default"
        }

        log(f"POST /api/v1/option1/recording/start")
        log(f"Doctor: {DOCTOR_ID}, Template: {TEMPLATE_CODE}")

        try:
            response = self.client.post(
                f"{BACKEND_URL}/api/v1/option1/recording/start",
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                self.correlation_id = data.get("correlation_id")
                self.session_id = data.get("session_id")
                log(f"Session started!", "SUCCESS")
                log(f"Correlation ID: {self.correlation_id}")
                log(f"Session ID: {self.session_id}")
                return True
            else:
                log(f"Failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            return False

    def upload_audio(self) -> bool:
        """Step 2: Upload audio file"""
        step(2, "Uploading Audio File")

        if not AUDIO_FILE.exists():
            log(f"Audio file not found: {AUDIO_FILE}", "ERROR")
            return False

        with open(AUDIO_FILE, "rb") as f:
            audio_bytes = f.read()

        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        file_size_mb = len(audio_bytes) / (1024 * 1024)

        log(f"File: {AUDIO_FILE.name} ({file_size_mb:.2f} MB)")

        payload = {
            "correlation_id": self.correlation_id,
            "chunk_index": 0,
            "audio_data": audio_base64,
            "mime_type": "audio/mpeg",
            "is_last": True
        }

        log("Uploading chunk (is_last=True)...")

        try:
            response = self.client.post(
                f"{BACKEND_URL}/api/v1/option1/recording/chunk",
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                self.submission_id = data.get("submissionId") or data.get("submission_id")
                log(f"Upload complete!", "SUCCESS")
                log(f"Submission ID: {self.submission_id}")
                return True
            else:
                log(f"Failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            return False

    def wait_for_transcription(self, max_wait: int = 300) -> str:
        """Step 3: Wait for transcription"""
        step(3, "Waiting for Transcription")

        log(f"Polling status (max {max_wait}s)...")

        start_time = time.time()
        last_status = None
        last_progress = -1

        while time.time() - start_time < max_wait:
            try:
                response = self.client.get(
                    f"{BACKEND_URL}/api/v1/option1/recording/status/{self.submission_id}"
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "").upper()
                    progress = data.get("progress", 0)
                    message = data.get("message", "")
                    transcript = data.get("transcript")

                    if status != last_status or progress != last_progress:
                        log(f"Status: {status} ({progress}%) - {message}")
                        last_status = status
                        last_progress = progress

                    # Check for transcript availability
                    if transcript and len(transcript) > 100:
                        log(f"Transcript available! ({len(transcript)} chars)", "SUCCESS")
                        print(f"\n{Colors.BLUE}Transcript Preview:{Colors.END}")
                        print(f"{transcript[:500]}..." if len(transcript) > 500 else transcript)
                        return transcript

                    # Check for completion or extraction phase (transcript should be ready)
                    if status in ("COMPLETED", "EXTRACTING", "DONE"):
                        if transcript:
                            log(f"Transcription complete! ({len(transcript)} chars)", "SUCCESS")
                            print(f"\n{Colors.BLUE}Transcript Preview:{Colors.END}")
                            print(f"{transcript[:500]}..." if len(transcript) > 500 else transcript)
                            return transcript
                        else:
                            # Extraction started but no transcript in response - fetch from session
                            log("Extraction phase - fetching transcript from session...")
                            session_resp = self.client.get(
                                f"{BACKEND_URL}/api/v1/option1/recording/session/{self.session_id}"
                            )
                            if session_resp.status_code == 200:
                                session_data = session_resp.json()
                                transcript = session_data.get("transcript_text") or session_data.get("transcript")
                                if transcript:
                                    log(f"Got transcript from session! ({len(transcript)} chars)", "SUCCESS")
                                    print(f"\n{Colors.BLUE}Transcript Preview:{Colors.END}")
                                    print(f"{transcript[:500]}..." if len(transcript) > 500 else transcript)
                                    return transcript

                    elif status == "FAILED":
                        log(f"Transcription failed: {message}", "ERROR")
                        return None

            except Exception as e:
                log(f"Poll error: {e}", "WARNING")

            time.sleep(3)

        log("Transcription timeout!", "ERROR")
        return None

    def run_extraction(self, transcript: str) -> bool:
        """Step 4: Run extraction"""
        step(4, "Running Medical Extraction")

        payload = {
            "transcript": transcript,
            "submission_id": self.submission_id,
            "template_code": TEMPLATE_CODE,
            "doctor_id": DOCTOR_ID,
            "mode": "full"
        }

        log(f"POST /api/v1/summary/extract")
        log(f"Mode: full, Template: {TEMPLATE_CODE}")

        try:
            start_time = time.time()
            response = self.client.post(
                f"{BACKEND_URL}/api/v1/summary/extract",
                json=payload
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                metadata = data.get("metadata", {})
                self.extraction_id = metadata.get("extraction_id")
                segment_count = metadata.get("segment_count", 0)

                log(f"Extraction complete in {elapsed:.1f}s!", "SUCCESS")
                log(f"Extraction ID: {self.extraction_id}")
                log(f"Segments: {segment_count}")
                return True
            else:
                log(f"Failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            return False

    def wait_for_background_tasks(self, wait_time: int = 45):
        """Step 5: Wait for background tasks"""
        step(5, "Waiting for Background Tasks")

        log("Background tasks: Triage, Insights, Assessments, Interventions")
        log(f"Waiting {wait_time} seconds...")

        for i in range(wait_time):
            time.sleep(1)
            if (i + 1) % 10 == 0:
                log(f"Waited {i + 1}s...")

        log("Wait complete", "SUCCESS")

    def verify_data(self) -> dict:
        """Step 6: Verify all generated data"""
        step(6, "Verifying Generated Data")

        if not self.extraction_id:
            log("No extraction_id!", "ERROR")
            return {}

        results = {}

        # API endpoints to check
        checks = [
            ("consultation_insights", f"/api/v1/consultation-insights/extraction/{self.extraction_id}"),
            ("triage", f"/api/v1/triage/extraction/{self.extraction_id}"),
            ("clinical_severity", f"/api/v1/clinical-severity/extraction/{self.extraction_id}"),
            ("allied_health_needs", f"/api/v1/allied-health/extraction/{self.extraction_id}"),
            ("other_clinical_needs", f"/api/v1/other-clinical-needs/extraction/{self.extraction_id}"),
            ("patient_dropoff_risk", f"/api/v1/patient-dropoff/extraction/{self.extraction_id}"),
            ("care_quality_risk", f"/api/v1/care-quality/extraction/{self.extraction_id}"),
            ("interventions", f"/api/v1/extractions/{self.extraction_id}/interventions"),
        ]

        for name, endpoint in checks:
            try:
                response = self.client.get(f"{BACKEND_URL}{endpoint}")

                if response.status_code == 200:
                    data = response.json()

                    # Count records based on response structure
                    if isinstance(data, list):
                        count = len(data)
                    elif isinstance(data, dict):
                        if "interventions" in data:
                            count = len(data.get("interventions", []))
                        elif "data" in data:
                            # Some endpoints wrap data in a "data" key
                            inner = data.get("data")
                            count = len(inner) if isinstance(inner, list) else (1 if inner else 0)
                        elif "id" in data:
                            # Single record with id field
                            count = 1
                        else:
                            count = 1 if data else 0
                    else:
                        count = 1 if data else 0

                    results[name] = {"status": "found", "count": count, "data": data}

                    if count > 0:
                        log(f"✓ {name}: {count} record(s)", "SUCCESS")

                        # Show intervention breakdown
                        if name == "interventions":
                            # Handle both list and dict response formats
                            if isinstance(data, list):
                                interventions = data
                            else:
                                interventions = data.get("interventions", [])

                            by_category = {}
                            by_priority = {}
                            for i in interventions:
                                # API uses "category" and "priority" (not intervention_category/priority_level)
                                cat = i.get("category") or i.get("intervention_category", "UNKNOWN")
                                pri = i.get("priority") or i.get("priority_level", "UNKNOWN")
                                by_category[cat] = by_category.get(cat, 0) + 1
                                by_priority[pri] = by_priority.get(pri, 0) + 1
                            if by_category:
                                log(f"  Categories: {by_category}")
                                log(f"  Priorities: {by_priority}")
                    else:
                        log(f"✗ {name}: Empty response", "WARNING")

                elif response.status_code == 404:
                    results[name] = {"status": "not_found", "count": 0}
                    log(f"✗ {name}: Not found (404)", "WARNING")
                else:
                    results[name] = {"status": "error", "code": response.status_code}
                    log(f"✗ {name}: Error {response.status_code}", "WARNING")

            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                log(f"✗ {name}: {e}", "ERROR")

        return results

    def print_summary(self, results: dict):
        """Print test summary"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
        print(f"{'='*60}")

        print(f"\nExtraction ID: {self.extraction_id}")
        print(f"Session ID: {self.session_id}")
        print(f"Patient ID: {PATIENT_ID}")

        print("\nData Generation Status:")
        print("-"*40)

        passed = 0
        failed = 0

        for name, info in results.items():
            count = info.get("count", 0)
            if info.get("status") == "found" and count > 0:
                print(f"  {Colors.GREEN}✓{Colors.END} {name}: {count} record(s)")
                passed += 1
            else:
                print(f"  {Colors.RED}✗{Colors.END} {name}: {info.get('status', 'unknown')}")
                failed += 1

        print("-"*40)
        print(f"Passed: {passed}/{passed + failed}")

        if failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL CHECKS PASSED!{Colors.END}")
        else:
            print(f"\n{Colors.YELLOW}⚠️  {failed} check(s) failed{Colors.END}")

    def run(self):
        """Run the complete test"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}PSG.mp3 EXTRACTION TEST{Colors.END}")
        print(f"{'='*60}")
        print(f"Audio: {AUDIO_FILE}")
        print(f"Template: {TEMPLATE_CODE}")
        print(f"Doctor: {DOCTOR_ID}")
        print(f"API Key: {API_KEY[:12]}...")
        print(f"{'='*60}")

        # Check backend
        if not self.check_backend():
            log("Start backend with: ./start-backend.sh", "ERROR")
            return

        # Step 1: Start session
        if not self.start_recording_session():
            return

        # Step 2: Upload audio
        if not self.upload_audio():
            return

        # Step 3: Wait for transcription
        transcript = self.wait_for_transcription()
        if not transcript:
            return

        # Step 4: Run extraction
        if not self.run_extraction(transcript):
            return

        # Step 5: Wait for background tasks
        self.wait_for_background_tasks(45)

        # Step 6: Verify data
        results = self.verify_data()

        # Print summary
        self.print_summary(results)

        return results


if __name__ == "__main__":
    tester = ExtractionTester()
    tester.run()
