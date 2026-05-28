"""
Extraction Latency Benchmark Script

Benchmarks extraction time to measure the impact of medicine/investigation list
injection optimization. Tests doctors WITH and WITHOUT lists to verify savings.

Test Variations:
1. Baseline (transcript only) - No doctor context, no lists
2. With doctor context - Medicine/Investigation lists injected (if doctor has them)

Tests run for:
- Doctor WITH lists (Mithra S) - should show list injection overhead
- Doctor WITHOUT lists (Kavinkumar M P) - should be close to baseline after optimization

Templates tested:
- OP_CORE
- CONCISE_OP

Usage:
    cd backend
    source venv/bin/activate
    python -m tests.benchmark_extraction_latency
"""

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from services.supabase_service import supabase
from services.segment_registry import generate_extraction_artifacts
from services.gemini_service import extract_summary_dynamic
from services.medicine_service import has_medicine_lists
from services.investigation_service import has_investigation_lists

# Configuration
RUNS_PER_TEST = 2
MODEL = "gemini-2.5-pro"

# Test doctors
DOCTOR_WITH_LISTS = {
    "id": "8aea65da-d54a-4e41-9216-943bf5542276",
    "name": "Mithra S",
    "patient_identifier": "Lak123"
}

DOCTOR_WITHOUT_LISTS = {
    "id": "23090766-880d-4d7e-9557-c5aacf5cbd27",
    "name": "Kavinkumar M P",
    "patient_identifier": None  # Will use same transcript
}

# Templates to test
TEMPLATES = ["OP_SHORT"]

# Consultation type (OP)
CONSULTATION_TYPE_ID = "6af5251b-63ea-4767-85d2-802e403eca73"


class BenchmarkResult:
    """Stores results for a single test variation."""

    def __init__(self, test_name: str, description: str):
        self.test_name = test_name
        self.description = description
        self.prompt_size = 0
        self.runs: List[float] = []
        self.segments_extracted = 0
        self.error: Optional[str] = None
        self.has_medicine_list: Optional[bool] = None
        self.has_investigation_list: Optional[bool] = None

    @property
    def average_time(self) -> float:
        return sum(self.runs) / len(self.runs) if self.runs else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "description": self.description,
            "prompt_size": self.prompt_size,
            "runs": self.runs,
            "average_time": round(self.average_time, 3),
            "segments_extracted": self.segments_extracted,
            "has_medicine_list": self.has_medicine_list,
            "has_investigation_list": self.has_investigation_list,
            "error": self.error
        }


def fetch_transcript(patient_identifier: str) -> str:
    """Fetch transcript for a patient."""
    # Get most recent recording session for patient
    session_result = supabase.table("recording_sessions") \
        .select("id") \
        .eq("patient_identifier", patient_identifier) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if not session_result.data:
        raise ValueError(f"No recording session found for patient {patient_identifier}")

    session_id = session_result.data[0]["id"]

    # Get transcript from processing_jobs
    job_result = supabase.table("processing_jobs") \
        .select("transcript") \
        .eq("session_id", session_id) \
        .eq("status", "COMPLETED") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if not job_result.data or not job_result.data[0]["transcript"]:
        raise ValueError(f"No transcript found for session {session_id}")

    return job_result.data[0]["transcript"]


def check_doctor_lists(doctor_id: str) -> Dict[str, bool]:
    """Check if doctor has medicine/investigation lists."""
    med_status = has_medicine_lists(uuid.UUID(doctor_id))
    inv_status = has_investigation_lists(uuid.UUID(doctor_id))
    return {
        "has_medicine_list": med_status["has_any_list"],
        "has_investigation_list": inv_status["has_any_list"]
    }


async def run_extraction(
    transcript: str,
    consultation_type_id: str,
    template_code: str,
    doctor_id: Optional[str] = None
) -> tuple[float, int, int, bool, bool]:
    """
    Run a single extraction and return timing info.

    Returns:
        Tuple of (api_time_seconds, prompt_size, segments_extracted, has_med_list, has_inv_list)
    """
    start_time = time.time()

    # Generate artifacts
    artifacts = generate_extraction_artifacts(
        consultation_type_id=uuid.UUID(consultation_type_id),
        doctor_id=uuid.UUID(doctor_id) if doctor_id else None,
        template_code=template_code,
        mode="full",
        transcript=transcript,
        patient_id=None  # No patient context for this benchmark
    )

    prompt_size = len(artifacts.get("user_prompt", ""))
    has_med_list = artifacts.get("has_medicine_list", False)
    has_inv_list = artifacts.get("has_investigation_list", False)

    # Call Gemini extraction
    result = await extract_summary_dynamic(
        transcript=transcript,
        consultation_type_id=consultation_type_id,
        doctor_id=doctor_id,
        template_code=template_code,
        mode="full",
        model=MODEL,
        cached_artifacts=artifacts,
        patient_id=None
    )

    api_time = time.time() - start_time
    segments_extracted = len(result.get("data", {}))

    return api_time, prompt_size, segments_extracted, has_med_list, has_inv_list


async def test_baseline(transcript: str, template_code: str) -> BenchmarkResult:
    """Test baseline: No doctor context, no lists."""
    result = BenchmarkResult(
        f"baseline_{template_code.lower()}",
        f"Baseline (no lists) - {template_code}"
    )

    print(f"\n--- Baseline (no doctor) - {template_code} ---")

    try:
        for run in range(RUNS_PER_TEST):
            api_time, prompt_size, segments, has_med, has_inv = await run_extraction(
                transcript=transcript,
                consultation_type_id=CONSULTATION_TYPE_ID,
                template_code=template_code,
                doctor_id=None  # No doctor = no lists
            )
            result.runs.append(api_time)
            result.prompt_size = prompt_size
            result.segments_extracted = segments
            result.has_medicine_list = has_med
            result.has_investigation_list = has_inv
            print(f"  Run {run + 1}: {api_time:.2f}s")

        print(f"  Average: {result.average_time:.2f}s | Prompt: {result.prompt_size} chars")
        print(f"  Lists injected: med={result.has_medicine_list}, inv={result.has_investigation_list}")

    except Exception as e:
        result.error = str(e)
        print(f"  ERROR: {e}")

    return result


async def test_with_doctor(
    transcript: str,
    template_code: str,
    doctor_id: str,
    doctor_name: str,
    has_lists: bool
) -> BenchmarkResult:
    """Test with doctor context."""
    list_status = "WITH lists" if has_lists else "NO lists"
    result = BenchmarkResult(
        f"doctor_{doctor_name.lower().replace(' ', '_')}_{template_code.lower()}",
        f"{doctor_name} ({list_status}) - {template_code}"
    )

    print(f"\n--- {doctor_name} ({list_status}) - {template_code} ---")

    try:
        for run in range(RUNS_PER_TEST):
            api_time, prompt_size, segments, has_med, has_inv = await run_extraction(
                transcript=transcript,
                consultation_type_id=CONSULTATION_TYPE_ID,
                template_code=template_code,
                doctor_id=doctor_id
            )
            result.runs.append(api_time)
            result.prompt_size = prompt_size
            result.segments_extracted = segments
            result.has_medicine_list = has_med
            result.has_investigation_list = has_inv
            print(f"  Run {run + 1}: {api_time:.2f}s")

        print(f"  Average: {result.average_time:.2f}s | Prompt: {result.prompt_size} chars")
        print(f"  Lists injected: med={result.has_medicine_list}, inv={result.has_investigation_list}")

    except Exception as e:
        result.error = str(e)
        print(f"  ERROR: {e}")

    return result


def print_summary(results: List[BenchmarkResult], transcript_length: int):
    """Print summary table of all results."""
    print(f"\n{'='*90}")
    print("BENCHMARK SUMMARY - Medicine/Investigation List Optimization")
    print(f"{'='*90}")
    print(f"Model: {MODEL} | Transcript: {transcript_length} chars | Runs per test: {RUNS_PER_TEST}")
    print(f"{'='*90}")

    # Group by template
    for template in TEMPLATES:
        template_results = [r for r in results if template.lower() in r.test_name.lower()]
        baseline = next((r for r in template_results if "baseline" in r.test_name), None)
        baseline_time = baseline.average_time if baseline else 0

        print(f"\n{template}:")
        print(f"{'Variation':<45} {'Prompt':>8} {'Avg Time':>10} {'vs Base':>10} {'Lists':>12}")
        print(f"{'-'*45} {'-'*8} {'-'*10} {'-'*10} {'-'*12}")

        for r in template_results:
            if r.error:
                print(f"{r.description:<45} {'ERROR':>8} {'-':>10} {'-':>10} {'-':>12}")
            else:
                delta = ((r.average_time - baseline_time) / baseline_time * 100) if baseline_time else 0
                delta_str = f"{delta:+.1f}%" if baseline_time else "N/A"
                list_str = f"med={r.has_medicine_list}, inv={r.has_investigation_list}"
                print(f"{r.description:<45} {r.prompt_size:>8} {r.average_time:>9.2f}s {delta_str:>10} {list_str:>12}")

    print(f"\n{'='*90}")
    print("OPTIMIZATION ANALYSIS:")
    print(f"{'='*90}")

    for template in TEMPLATES:
        template_results = [r for r in results if template.lower() in r.test_name.lower()]
        baseline = next((r for r in template_results if "baseline" in r.test_name), None)
        with_lists = next((r for r in template_results if "mithra" in r.test_name.lower()), None)
        without_lists = next((r for r in template_results if "kavinkumar" in r.test_name.lower()), None)

        if baseline and with_lists and without_lists:
            overhead_with = with_lists.average_time - baseline.average_time
            overhead_without = without_lists.average_time - baseline.average_time
            savings = overhead_with - overhead_without

            print(f"\n{template}:")
            print(f"  Baseline (no doctor):        {baseline.average_time:.2f}s")
            print(f"  Doctor WITH lists (Mithra):  {with_lists.average_time:.2f}s (+{overhead_with:.2f}s overhead)")
            print(f"  Doctor WITHOUT lists:        {without_lists.average_time:.2f}s (+{overhead_without:.2f}s overhead)")
            print(f"  Optimization savings:        {savings:.2f}s")

            if overhead_without < 1.0:
                print(f"  -> SUCCESS: Doctor without lists is close to baseline!")
            elif overhead_without < overhead_with:
                print(f"  -> PARTIAL: Some savings, but Gemini API variance may mask results")
            else:
                print(f"  -> NOTE: API variance may be masking optimization effect")


def save_results(results: List[BenchmarkResult], transcript_length: int):
    """Save results to JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent / f"benchmark_results_{timestamp}.json"

    output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "model": MODEL,
            "runs_per_test": RUNS_PER_TEST,
            "transcript_length": transcript_length,
            "consultation_type_id": CONSULTATION_TYPE_ID,
            "templates_tested": TEMPLATES,
            "doctor_with_lists": DOCTOR_WITH_LISTS,
            "doctor_without_lists": DOCTOR_WITHOUT_LISTS
        },
        "results": [r.to_dict() for r in results]
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_file}")


async def main():
    """Run all benchmark tests."""
    print("\n" + "="*60)
    print("EXTRACTION LATENCY BENCHMARK")
    print("Medicine/Investigation List Optimization Test")
    print("="*60)

    try:
        # Fetch transcript from Lak123 (use same transcript for all tests)
        print(f"\nFetching transcript from patient {DOCTOR_WITH_LISTS['patient_identifier']}...")
        transcript = fetch_transcript(DOCTOR_WITH_LISTS["patient_identifier"])
        print(f"Transcript length: {len(transcript)} chars")

        # Verify doctor list status
        print(f"\nVerifying doctor list status:")

        doc1_lists = check_doctor_lists(DOCTOR_WITH_LISTS["id"])
        print(f"  {DOCTOR_WITH_LISTS['name']}: med={doc1_lists['has_medicine_list']}, inv={doc1_lists['has_investigation_list']}")

        doc2_lists = check_doctor_lists(DOCTOR_WITHOUT_LISTS["id"])
        print(f"  {DOCTOR_WITHOUT_LISTS['name']}: med={doc2_lists['has_medicine_list']}, inv={doc2_lists['has_investigation_list']}")

        # Run all test variations
        results: List[BenchmarkResult] = []

        for template in TEMPLATES:
            print(f"\n{'='*60}")
            print(f"TESTING TEMPLATE: {template}")
            print(f"{'='*60}")

            # 1. Baseline (no doctor)
            results.append(await test_baseline(transcript, template))

            # 2. Doctor WITH lists (Mithra S)
            results.append(await test_with_doctor(
                transcript=transcript,
                template_code=template,
                doctor_id=DOCTOR_WITH_LISTS["id"],
                doctor_name=DOCTOR_WITH_LISTS["name"],
                has_lists=True
            ))

            # 3. Doctor WITHOUT lists (Kavinkumar M P)
            results.append(await test_with_doctor(
                transcript=transcript,
                template_code=template,
                doctor_id=DOCTOR_WITHOUT_LISTS["id"],
                doctor_name=DOCTOR_WITHOUT_LISTS["name"],
                has_lists=False
            ))

        # Print summary
        print_summary(results, len(transcript))

        # Save results
        save_results(results, len(transcript))

    except Exception as e:
        print(f"\n BENCHMARK FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
