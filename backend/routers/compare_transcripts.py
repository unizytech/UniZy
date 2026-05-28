"""
Transcript Comparison Router
Compares transcripts against ground truth for accuracy evaluation
"""

import json
import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from services.llm_client_factory import generate_json_output
from models.auth_models import ClientContext
from dependencies.auth import require_admin

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1", tags=["Transcript Comparison"])


class TranscriptInput(BaseModel):
    name: str
    text: str


class CompareRequest(BaseModel):
    ground_truth: str
    transcripts: List[TranscriptInput]


class ComparisonMetrics(BaseModel):
    content_accuracy: float
    medical_terminology_capture: float
    no_misrepresentation: float
    completeness: float
    overall_score: float
    detailed_analysis: str


class ComparisonResult(BaseModel):
    box_name: str
    transcript: str
    metrics: ComparisonMetrics
    error: Optional[str] = None


class CompareResponse(BaseModel):
    success: bool
    results: List[ComparisonResult]
    processing_time_seconds: float
    error: Optional[str] = None


COMPARISON_PROMPT = """You are an expert medical transcription quality analyst. Your task is to compare a test transcript against a ground truth transcription and evaluate its accuracy.

**GROUND TRUTH (may include diarization labels like "Doctor:", "Patient:", "Speaker 1:", etc.):**
{ground_truth}

**TEST TRANSCRIPT (may not have diarization labels):**
{test_transcript}

**EVALUATION CRITERIA:**

1. **Content Accuracy (0-100%)**: How accurately does the test transcript capture the actual spoken content from the ground truth? Ignore diarization labels when comparing content. Focus on whether the words, phrases, and sentences match.

2. **Medical Terminology Capture (0-100%)**: How well does the test transcript capture medical terms, diagnoses, medications, procedures, and clinical terminology? Even minor errors in medical terms can be critical.

3. **No Misrepresentation (0-100%)**: Does the test transcript avoid misrepresenting or distorting information? A score of 100% means no misrepresentation. Deduct points for:
   - Changed meanings
   - Incorrect medical terms that could lead to wrong interpretation
   - Missing critical context
   - Confusing speaker attribution (if applicable)

4. **Completeness (0-100%)**: How complete is the test transcript compared to the ground truth? Are all important statements, medical information, and context captured?

**IMPORTANT NOTES:**
- The ground truth may have diarization labels (Doctor:, Patient:, etc.). The test transcript may not.
- When comparing content, IGNORE the diarization labels and focus on the actual text content.
- Be strict with medical terminology - even small errors matter in medical contexts.
- Consider contextual accuracy, not just word-by-word matching.

**OUTPUT FORMAT (JSON):**
Provide your analysis in the following JSON format:

{{
  "content_accuracy": <score 0-100>,
  "medical_terminology_capture": <score 0-100>,
  "no_misrepresentation": <score 0-100>,
  "completeness": <score 0-100>,
  "overall_score": <average of all 4 scores>,
  "detailed_analysis": "<Single paragraph (no line breaks) detailed analysis explaining key strengths, specific errors or omissions, impact of medical terminology errors, overall assessment, and specific examples from the transcripts>"
}}

Return ONLY the JSON object, no additional text.
"""


async def compare_transcript_with_ground_truth(
    ground_truth: str,
    test_transcript: str,
    box_name: str
) -> ComparisonResult:
    """
    Compare a test transcript against ground truth using Gemini AI

    Args:
        ground_truth: Reference transcript (may include diarization)
        test_transcript: Transcript to evaluate
        box_name: Name/identifier for this comparison

    Returns:
        ComparisonResult with metrics and analysis
    """
    try:
        # Create the comparison prompt
        prompt = COMPARISON_PROMPT.format(
            ground_truth=ground_truth,
            test_transcript=test_transcript
        )

        # Use compare_model from processing_modes table (defaults to gemini-2.5-flash)
        from services.supabase_service import get_compare_model_by_mode
        compare_model = get_compare_model_by_mode("default")

        # Route through LLM factory (supports Gemini/Claude/OpenAI)
        llm_result = await generate_json_output(
            system_prompt="",
            user_prompt=prompt,
            model=compare_model,
            temperature=0.1,
        )

        # Data is already parsed by the factory
        metrics_data = llm_result.data

        # Create metrics object
        metrics = ComparisonMetrics(
            content_accuracy=float(metrics_data.get("content_accuracy", 0)),
            medical_terminology_capture=float(metrics_data.get("medical_terminology_capture", 0)),
            no_misrepresentation=float(metrics_data.get("no_misrepresentation", 0)),
            completeness=float(metrics_data.get("completeness", 0)),
            overall_score=float(metrics_data.get("overall_score", 0)),
            detailed_analysis=str(metrics_data.get("detailed_analysis", "No analysis available"))
        )

        return ComparisonResult(
            box_name=box_name,
            transcript=test_transcript,
            metrics=metrics
        )

    except Exception as e:
        import traceback
        logger.error(f"Error comparing transcript '{box_name}': {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        # Return error result
        from services.error_utils import sanitize_error_message
        sanitized = sanitize_error_message(str(e))
        return ComparisonResult(
            box_name=box_name,
            transcript=test_transcript,
            metrics=ComparisonMetrics(
                content_accuracy=0,
                medical_terminology_capture=0,
                no_misrepresentation=0,
                completeness=0,
                overall_score=0,
                detailed_analysis=f"Error during comparison: {sanitized}"
            ),
            error=sanitized
        )


@router.post("/compare-transcripts", response_model=CompareResponse)
async def compare_transcripts(
    request: CompareRequest,
    client: ClientContext = Depends(require_admin)
):
    """
    Compare multiple transcripts against a ground truth transcription.

    **Admin only** - This endpoint is for transcript accuracy testing.

    Args:
        request: Contains ground_truth and list of transcripts to compare

    Returns:
        CompareResponse with comparison results for each transcript
    """
    start_time = time.time()

    try:
        logger.info(f"[Compare] Starting comparison of {len(request.transcripts)} transcripts")

        # Validate inputs
        if not request.ground_truth or not request.ground_truth.strip():
            raise HTTPException(
                status_code=400,
                detail="Ground truth transcription is required"
            )

        if not request.transcripts or len(request.transcripts) == 0:
            raise HTTPException(
                status_code=400,
                detail="At least one transcript to compare is required"
            )

        # Process each transcript comparison
        results = []
        for transcript_input in request.transcripts:
            logger.info(f"[Compare] Comparing {transcript_input.name}...")

            result = await compare_transcript_with_ground_truth(
                ground_truth=request.ground_truth,
                test_transcript=transcript_input.text,
                box_name=transcript_input.name
            )

            results.append(result)

            logger.info(
                f"[Compare] {transcript_input.name} - Overall Score: "
                f"{result.metrics.overall_score:.1f}%"
            )

        processing_time = time.time() - start_time
        logger.info(f"[Compare] Completed all comparisons in {processing_time:.2f}s")

        return CompareResponse(
            success=True,
            results=results,
            processing_time_seconds=processing_time
        )

    except HTTPException:
        raise

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"[Compare] Request failed after {processing_time:.2f}s: {e}")

        from services.error_utils import sanitize_error_message
        return CompareResponse(
            success=False,
            results=[],
            processing_time_seconds=processing_time,
            error=sanitize_error_message(str(e))
        )
