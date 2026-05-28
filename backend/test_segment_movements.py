"""
Test Segment Movement Between Categories
Tests dragging segments between CORE, ADDITIONAL, and EXCLUDED columns
for both consultation types and templates.
"""

import httpx
import asyncio
from typing import Dict, Any, List
import json

API_BASE_URL = "http://localhost:8000/api/v1/summary"
ADMIN_ID = "admin-user-1"

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_test(text: str):
    print(f"{Colors.OKBLUE}{Colors.BOLD}▶ {text}{Colors.ENDC}")

def print_success(text: str):
    print(f"{Colors.OKGREEN}  ✓ {text}{Colors.ENDC}")

def print_error(text: str):
    print(f"{Colors.FAIL}  ✗ {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.WARNING}  ⚠ {text}{Colors.ENDC}")

def print_info(text: str):
    print(f"{Colors.OKCYAN}  ℹ {text}{Colors.ENDC}")


class SegmentMovementTester:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.consultation_type = "OP"
        self.template_code = None  # Will be set during tests

        # Test segments
        self.non_required_consultation_segment = None  # Will find one
        self.non_required_common_segment = None  # Will find one
        self.required_consultation_segment = None  # Will find one
        self.required_common_segment = None  # Will find one

        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": []
        }

    def setup_test_segments(self):
        """Find suitable test segments from the database."""
        print_header("SETUP: Finding Test Segments")

        # Get all segments for OP consultation type
        response = self.client.get(
            f"{API_BASE_URL}/admin/consultation-types/{self.consultation_type}/segments"
        )

        if response.status_code != 200:
            print_error(f"Failed to fetch segments: {response.text}")
            return False

        data = response.json()
        segments = data.get("segments", [])

        # Find segments for testing
        for segment in segments:
            segment_code = segment["segment_code"]
            is_required = segment.get("is_required", False)
            is_common = segment.get("is_common", False)
            consultation_type_id = segment.get("consultation_type_id")

            # Non-required consultation-type-specific segment
            if (not is_required and not is_common and consultation_type_id and
                not self.non_required_consultation_segment):
                self.non_required_consultation_segment = segment_code
                print_success(f"Found non-required consultation-specific: {segment_code}")

            # Non-required common segment
            if not is_required and is_common and not self.non_required_common_segment:
                self.non_required_common_segment = segment_code
                print_success(f"Found non-required common: {segment_code}")

            # Required consultation-type-specific segment
            if (is_required and not is_common and consultation_type_id and
                not self.required_consultation_segment):
                self.required_consultation_segment = segment_code
                print_success(f"Found required consultation-specific: {segment_code}")

            # Required common segment
            if is_required and is_common and not self.required_common_segment:
                self.required_common_segment = segment_code
                print_success(f"Found required common: {segment_code}")

        # If we don't have a consultation-specific segment, create one
        if not self.non_required_consultation_segment:
            print_warning("No consultation-specific non-required segment found, creating one...")
            self.non_required_consultation_segment = "TEST_CONSULTATION_SEGMENT"
            # We'll create it during tests

        return True

    def get_template_for_testing(self):
        """Get or create a template for testing."""
        print_header("SETUP: Finding Test Template")

        # Get templates for OP consultation type
        response = self.client.get(
            f"{API_BASE_URL}/templates",
            params={"consultation_type_code": self.consultation_type}
        )

        if response.status_code == 200:
            data = response.json()
            templates = data.get("templates", [])

            if templates:
                self.template_code = templates[0]["template_code"]
                print_success(f"Using existing template: {self.template_code}")
                return True

        print_warning("No templates found. Tests will focus on consultation type configuration only.")
        return False

    def move_segment_consultation_type(self, segment_code: str, new_category: str) -> bool:
        """Move segment in consultation type configuration."""
        self.results["total_tests"] += 1

        try:
            response = self.client.put(
                f"{API_BASE_URL}/admin/consultation-types/{self.consultation_type}/segments/{segment_code}",
                json={"default_category": new_category}
            )

            if response.status_code == 200:
                self.results["passed"] += 1
                return True
            else:
                self.results["failed"] += 1
                self.results["errors"].append({
                    "segment": segment_code,
                    "category": new_category,
                    "error": response.text
                })
                return False
        except Exception as e:
            self.results["failed"] += 1
            self.results["errors"].append({
                "segment": segment_code,
                "category": new_category,
                "error": str(e)
            })
            return False

    def move_segment_template(self, segment_code: str, new_category: str) -> bool:
        """Move segment in template configuration."""
        if not self.template_code:
            print_warning("No template available for testing")
            return None

        self.results["total_tests"] += 1

        try:
            # display_order is required, using a default value
            response = self.client.put(
                f"{API_BASE_URL}/admin/templates/{self.template_code}/segments/{segment_code}",
                json={
                    "category": new_category,
                    "display_order": 1  # Using default order for testing
                }
            )

            if response.status_code == 200:
                self.results["passed"] += 1
                return True
            else:
                self.results["failed"] += 1
                self.results["errors"].append({
                    "template": self.template_code,
                    "segment": segment_code,
                    "category": new_category,
                    "error": response.text
                })
                return False
        except Exception as e:
            self.results["failed"] += 1
            self.results["errors"].append({
                "template": self.template_code,
                "segment": segment_code,
                "category": new_category,
                "error": str(e)
            })
            return False

    def test_movement_sequence(self, segment_code: str, segment_type: str, is_required: bool = False):
        """Test a complete movement sequence for a segment."""
        print_header(f"Testing Movement Sequence: {segment_type} - {segment_code}")

        # Sequence 1: core → additional → core
        print_test("Sequence 1: CORE → ADDITIONAL → CORE")

        print_info("Moving to ADDITIONAL...")
        result = self.move_segment_consultation_type(segment_code, "additional")
        if result:
            print_success("Moved to ADDITIONAL")
        else:
            print_error("Failed to move to ADDITIONAL")

        print_info("Moving back to CORE...")
        result = self.move_segment_consultation_type(segment_code, "core")
        if result:
            print_success("Moved back to CORE")
        else:
            print_error("Failed to move back to CORE")

        # Sequence 2: core → excluded → core
        print_test("\nSequence 2: CORE → EXCLUDED → CORE")

        print_info("Moving to EXCLUDED...")
        result = self.move_segment_consultation_type(segment_code, "excluded")
        if result:
            print_success("Moved to EXCLUDED")
        else:
            print_error("Failed to move to EXCLUDED")

        print_info("Moving back to CORE...")
        result = self.move_segment_consultation_type(segment_code, "core")
        if result:
            print_success("Moved back to CORE")
        else:
            print_error("Failed to move back to CORE")

        # Sequence 3: additional → excluded → additional
        print_test("\nSequence 3: ADDITIONAL → EXCLUDED → ADDITIONAL")

        print_info("Moving to ADDITIONAL first...")
        self.move_segment_consultation_type(segment_code, "additional")

        print_info("Moving to EXCLUDED...")
        result = self.move_segment_consultation_type(segment_code, "excluded")
        if result:
            print_success("Moved to EXCLUDED")
        else:
            print_error("Failed to move to EXCLUDED")

        print_info("Moving back to ADDITIONAL...")
        result = self.move_segment_consultation_type(segment_code, "additional")
        if result:
            print_success("Moved back to ADDITIONAL")
        else:
            print_error("Failed to move back to ADDITIONAL")

        # Sequence 4: additional → core → additional
        print_test("\nSequence 4: ADDITIONAL → CORE → ADDITIONAL")

        print_info("Moving to CORE...")
        result = self.move_segment_consultation_type(segment_code, "core")
        if result:
            print_success("Moved to CORE")
        else:
            print_error("Failed to move to CORE")

        print_info("Moving back to ADDITIONAL...")
        result = self.move_segment_consultation_type(segment_code, "additional")
        if result:
            print_success("Moved back to ADDITIONAL")
        else:
            print_error("Failed to move back to ADDITIONAL")

        # Reset to CORE
        print_info("\nResetting to CORE...")
        self.move_segment_consultation_type(segment_code, "core")

    def test_template_movement_sequence(self, segment_code: str, segment_type: str):
        """Test movement sequence in template configuration."""
        if not self.template_code:
            return

        print_header(f"Testing Template Movement Sequence: {segment_type} - {segment_code}")

        # Sequence 1: core → additional → core
        print_test("Template Sequence 1: CORE → ADDITIONAL → CORE")

        print_info("Moving to ADDITIONAL...")
        result = self.move_segment_template(segment_code, "additional")
        if result:
            print_success("Moved to ADDITIONAL")
        else:
            print_error("Failed to move to ADDITIONAL")

        print_info("Moving back to CORE...")
        result = self.move_segment_template(segment_code, "core")
        if result:
            print_success("Moved back to CORE")
        else:
            print_error("Failed to move back to CORE")

        # Sequence 2: core → excluded → core
        print_test("\nTemplate Sequence 2: CORE → EXCLUDED → CORE")

        print_info("Moving to EXCLUDED...")
        result = self.move_segment_template(segment_code, "excluded")
        if result:
            print_success("Moved to EXCLUDED")
        else:
            print_error("Failed to move to EXCLUDED")

        print_info("Moving back to CORE...")
        result = self.move_segment_template(segment_code, "core")
        if result:
            print_success("Moved back to CORE")
        else:
            print_error("Failed to move back to CORE")

    def test_required_segment_restrictions(self, segment_code: str, segment_type: str):
        """Test that required segments cannot be moved from CORE."""
        print_header(f"Testing Required Segment Restrictions: {segment_type} - {segment_code}")

        print_test("Attempting to move required segment from CORE to ADDITIONAL (should fail)")

        result = self.move_segment_consultation_type(segment_code, "additional")
        if not result:
            print_success("✓ Correctly prevented moving required segment from CORE")
            # Adjust counts - this is expected to fail
            self.results["failed"] -= 1
            self.results["passed"] += 1
            # Remove from errors
            self.results["errors"] = [e for e in self.results["errors"]
                                     if e.get("segment") != segment_code or e.get("category") != "additional"]
        else:
            print_error("✗ ERROR: Required segment was allowed to move from CORE (should be prevented!)")

        print_test("\nAttempting to move required segment from CORE to EXCLUDED (should fail)")

        result = self.move_segment_consultation_type(segment_code, "excluded")
        if not result:
            print_success("✓ Correctly prevented moving required segment from CORE")
            # Adjust counts - this is expected to fail
            self.results["failed"] -= 1
            self.results["passed"] += 1
            # Remove from errors
            self.results["errors"] = [e for e in self.results["errors"]
                                     if e.get("segment") != segment_code or e.get("category") != "excluded"]
        else:
            print_error("✗ ERROR: Required segment was allowed to move from CORE (should be prevented!)")

    def run_all_tests(self):
        """Run all test scenarios."""
        print_header("SEGMENT MOVEMENT COMPREHENSIVE TEST SUITE")
        print_info(f"Testing against: {API_BASE_URL}")
        print_info(f"Consultation Type: {self.consultation_type}")
        print_info(f"Admin ID: {ADMIN_ID}\n")

        # Setup
        if not self.setup_test_segments():
            print_error("Failed to setup test segments")
            return

        self.get_template_for_testing()

        # Scenario 1: Non-required consultation-type-specific segment
        if self.non_required_consultation_segment:
            self.test_movement_sequence(
                self.non_required_consultation_segment,
                "Non-Required Consultation-Specific Segment"
            )
            if self.template_code:
                self.test_template_movement_sequence(
                    self.non_required_consultation_segment,
                    "Non-Required Consultation-Specific Segment"
                )

        # Scenario 2: Non-required common segment
        if self.non_required_common_segment:
            self.test_movement_sequence(
                self.non_required_common_segment,
                "Non-Required Common Segment"
            )
            if self.template_code:
                self.test_template_movement_sequence(
                    self.non_required_common_segment,
                    "Non-Required Common Segment"
                )

        # Scenario 3: Required consultation-type-specific segment
        if self.required_consultation_segment:
            self.test_required_segment_restrictions(
                self.required_consultation_segment,
                "Required Consultation-Specific Segment"
            )

        # Scenario 4: Required common segment
        if self.required_common_segment:
            self.test_required_segment_restrictions(
                self.required_common_segment,
                "Required Common Segment"
            )

        # Print final results
        self.print_final_results()

    def print_final_results(self):
        """Print final test results."""
        print_header("TEST RESULTS SUMMARY")

        print(f"{Colors.BOLD}Total Tests:{Colors.ENDC} {self.results['total_tests']}")
        print(f"{Colors.OKGREEN}{Colors.BOLD}Passed:{Colors.ENDC} {self.results['passed']}")
        print(f"{Colors.FAIL}{Colors.BOLD}Failed:{Colors.ENDC} {self.results['failed']}")

        if self.results["errors"]:
            print_header("ERRORS")
            for i, error in enumerate(self.results["errors"], 1):
                print(f"\n{Colors.FAIL}{i}. Error Details:{Colors.ENDC}")
                print(f"   {json.dumps(error, indent=3)}")

        # Calculate success rate
        if self.results["total_tests"] > 0:
            success_rate = (self.results["passed"] / self.results["total_tests"]) * 100
            print(f"\n{Colors.BOLD}Success Rate:{Colors.ENDC} {success_rate:.2f}%")

            if success_rate == 100:
                print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! 🎉{Colors.ENDC}\n")
            elif success_rate >= 80:
                print(f"\n{Colors.WARNING}{Colors.BOLD}⚠ Most tests passed, but some issues found{Colors.ENDC}\n")
            else:
                print(f"\n{Colors.FAIL}{Colors.BOLD}❌ Many tests failed - investigation needed{Colors.ENDC}\n")


def main():
    """Main test runner."""
    tester = SegmentMovementTester()

    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Test interrupted by user{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.FAIL}Test suite error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
    finally:
        tester.client.close()


if __name__ == "__main__":
    main()
