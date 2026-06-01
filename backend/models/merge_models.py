"""
Merge Models - Pydantic Models for Extraction Merge Feature

Request and response models for the extraction merge API endpoints.

Author: System
Date: 2025-11-19
Updated: 2025-12-11 - Added upload_type for merge strategy control, multiple JSON uploads support
"""

from pydantic import BaseModel, Field, UUID4, field_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# =====================================================
# Constants
# =====================================================

MAX_MERGE_SOURCES = 4  # Maximum total sources (extractions + JSON uploads combined)


# =====================================================
# Upload Type Enum and Merge Strategy
# =====================================================

class UploadType(str, Enum):
    """
    Type of uploaded JSON data - determines merge strategy.

    DEEP_MERGE types: Data is intelligently merged with existing data using AI.
    APPEND types: Data is appended to existing arrays/lists without replacement.
    """
    # DEEP_MERGE types - AI contextually merges with existing data
    OP_SUMMARY = "OP_SUMMARY"              # Outpatient consultation summary
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY" # Discharge summary
    EXAMINATION = "EXAMINATION"             # Physical examination findings
    OPTOMETRY = "OPTOMETRY"                 # Optometry/refraction data

    # APPEND types - Always appended to existing arrays
    INVESTIGATION = "INVESTIGATION"         # Lab results, imaging results
    PRESCRIPTION = "PRESCRIPTION"           # Rx/medication data
    NOTES = "NOTES"                         # Clinical notes, OT notes, etc.

    # Fallback
    OTHER = "OTHER"                         # Generic - uses DEEP_MERGE by default


# Merge strategy mapping
UPLOAD_TYPE_MERGE_STRATEGY: Dict[UploadType, str] = {
    # DEEP_MERGE - AI contextually merges, latest wins for conflicts
    UploadType.OP_SUMMARY: "DEEP_MERGE",
    UploadType.DISCHARGE_SUMMARY: "DEEP_MERGE",
    UploadType.EXAMINATION: "DEEP_MERGE",
    UploadType.OPTOMETRY: "DEEP_MERGE",
    UploadType.OTHER: "DEEP_MERGE",

    # APPEND - Always append to arrays, never replace
    UploadType.INVESTIGATION: "APPEND",
    UploadType.PRESCRIPTION: "APPEND",
    UploadType.NOTES: "APPEND",
}


def get_merge_strategy(upload_type: UploadType) -> str:
    """Get the merge strategy for a given upload type."""
    return UPLOAD_TYPE_MERGE_STRATEGY.get(upload_type, "DEEP_MERGE")


# =====================================================
# Request Models
# =====================================================

class UploadedJsonSource(BaseModel):
    """
    Uploaded JSON data for merge.

    Merge strategy is determined by `upload_type`:
    - DEEP_MERGE (OP_SUMMARY, DISCHARGE_SUMMARY, EXAMINATION, OPTOMETRY, OTHER):
      AI contextually merges with existing data, latest wins for conflicts.
    - APPEND (INVESTIGATION, PRESCRIPTION, NOTES):
      Data is appended to existing arrays without replacement.
    """
    data: Dict[str, Any] = Field(
        ...,
        description="JSON data to merge into the extraction"
    )
    upload_type: UploadType = Field(
        UploadType.OTHER,
        description="Type of uploaded data - determines merge strategy (DEEP_MERGE vs APPEND)"
    )
    source_name: Optional[str] = Field(
        "Uploaded JSON",
        description="Display name for the uploaded source (e.g., 'External Lab Report')"
    )
    source_date: Optional[str] = Field(
        None,
        description="Date of the source data (ISO format) for chronological ordering"
    )
    consultation_type_code: Optional[str] = Field(
        None,
        description="Optional consultation type code for the uploaded JSON (for field mapping)"
    )


class MergeRequest(BaseModel):
    """
    Request model for merging multiple extractions.

    **Source Limits:**
    - Minimum: 2 sources total (any combination of extractions + JSON uploads)
    - Maximum: 4 sources total (extractions + JSON uploads combined)

    **Supported Combinations:**
    1. 2-4 database extractions (source_extraction_ids)
    2. 1-3 extractions + 1-3 JSON uploads (totaling 2-4)
    3. 2-4 JSON uploads only (requires student_id)
    4. Using submission_ids instead of extraction_ids (source_submission_ids)

    **student_id Requirement:**
    - Optional when at least 1 extraction is provided (derived from extraction)
    - Required when using only JSON uploads (no extractions)

    **Merge Strategies by upload_type:**
    - DEEP_MERGE: OP_SUMMARY, DISCHARGE_SUMMARY, EXAMINATION, OPTOMETRY, OTHER
    - APPEND: INVESTIGATION, PRESCRIPTION, NOTES
    """
    source_extraction_ids: List[str] = Field(
        default=[],
        description="List of extraction UUIDs to merge (0-4, combined with uploads must be 2-4 total)"
    )
    source_submission_ids: List[str] = Field(
        default=[],
        description="Alternative: List of submission UUIDs (from recording flow). Will be resolved to extraction_ids automatically."
    )
    uploaded_json_sources: List[UploadedJsonSource] = Field(
        default=[],
        description="List of JSON sources to merge (0-4, combined with extractions must be 2-4 total). Each source has upload_type for merge strategy."
    )
    target_template_code: str = Field(
        ...,
        description="Target template code (e.g., 'OP_GENERAL', 'OP_SMITH_1225141530')"
    )
    counsellor_id: str = Field(
        ...,
        description="Counsellor ID performing the merge"
    )
    student_id: Optional[str] = Field(
        None,
        description="Student UUID. Required when merging only JSON uploads (no extractions). Optional when extractions are provided."
    )
    merge_notes: Optional[str] = Field(
        None,
        description="Optional notes about the merge operation"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "title": "Merge 2 extractions",
                    "value": {
                        "source_extraction_ids": [
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440002"
                        ],
                        "target_template_code": "OP_GENERAL",
                        "counsellor_id": "550e8400-e29b-41d4-a716-446655440099",
                        "merge_notes": "Follow-up consolidation"
                    }
                },
                {
                    "title": "Merge extraction + JSON uploads",
                    "value": {
                        "source_extraction_ids": ["550e8400-e29b-41d4-a716-446655440001"],
                        "uploaded_json_sources": [
                            {
                                "data": {"test_results": [{"test": "HbA1c", "value": "7.2%"}]},
                                "upload_type": "INVESTIGATION",
                                "source_name": "Lab Report",
                                "source_date": "2025-12-10"
                            }
                        ],
                        "target_template_code": "OP_GENERAL",
                        "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
                    }
                },
                {
                    "title": "Merge JSON uploads only (requires student_id)",
                    "value": {
                        "uploaded_json_sources": [
                            {
                                "data": {"chief_complaints": "Fever, cough"},
                                "upload_type": "OP_SUMMARY",
                                "source_name": "OP Visit 1",
                                "source_date": "2025-12-08"
                            },
                            {
                                "data": {"chief_complaints": "Follow-up for fever"},
                                "upload_type": "OP_SUMMARY",
                                "source_name": "OP Visit 2",
                                "source_date": "2025-12-10"
                            }
                        ],
                        "target_template_code": "OP_GENERAL",
                        "counsellor_id": "550e8400-e29b-41d4-a716-446655440099",
                        "student_id": "550e8400-e29b-41d4-a716-446655440088"
                    }
                }
            ]
        }


class MergePreviewRequest(BaseModel):
    """
    Request model for previewing merge without saving.
    Same as MergeRequest but explicitly indicates preview-only.

    See MergeRequest for full documentation on source limits and merge strategies.
    """
    source_extraction_ids: List[str] = Field(
        default=[],
        description="List of extraction UUIDs to merge (0-4, combined with uploads must be 2-4 total)"
    )
    source_submission_ids: List[str] = Field(
        default=[],
        description="Alternative: List of submission UUIDs (from recording flow). Will be resolved to extraction_ids automatically."
    )
    uploaded_json_sources: List[UploadedJsonSource] = Field(
        default=[],
        description="List of JSON sources to merge (0-4, combined with extractions must be 2-4 total)"
    )
    target_template_code: str = Field(
        ...,
        description="Target template code (e.g., 'OP_GENERAL', 'OP_SMITH_1225141530')"
    )
    counsellor_id: str = Field(
        ...,
        description="Counsellor ID performing the merge"
    )
    student_id: Optional[str] = Field(
        None,
        description="Student UUID. Required when merging only JSON uploads (no extractions)."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source_extraction_ids": [
                    "550e8400-e29b-41d4-a716-446655440001"
                ],
                "uploaded_json_sources": [
                    {
                        "data": {"external_notes": "Student referred from external clinic"},
                        "upload_type": "NOTES",
                        "source_name": "Referral Notes"
                    }
                ],
                "target_template_code": "DISCHARGE_GENERAL",
                "counsellor_id": "550e8400-e29b-41d4-a716-446655440099"
            }
        }


# =====================================================
# Response Models
# =====================================================

class MergeMetadata(BaseModel):
    """
    Metadata about the merge operation.
    """
    source_count: int = Field(..., description="Number of source extractions merged")
    target_template_code: str = Field(..., description="Target template code used for merge")
    merge_timestamp: str = Field(..., description="ISO timestamp of merge operation")
    doctor_confirmed: bool = Field(..., description="Whether counsellor confirmed the merge")
    merge_notes: Optional[str] = Field(None, description="Notes about the merge")
    conflict_count: int = Field(..., description="Number of conflicting fields detected")
    conflicts_resolved: List[str] = Field(..., description="List of field names with conflicts that were resolved")
    cross_type_scenario: str = Field(..., description="Merge scenario (SAME_TYPE, OP_to_DISCHARGE, etc.)")
    consultation_types_merged: List[str] = Field(..., description="List of consultation type codes that were merged")


class MergeResponse(BaseModel):
    """
    Response model for successful merge operation.
    """
    success: bool = Field(..., description="Whether merge was successful")
    extraction_id: Optional[str] = Field(None, description="ID of merged extraction (if saved)")
    submission_id: Optional[str] = Field(None, description="Submission ID of merged extraction (if saved) - for tracking/lookup")
    merged_data: Dict[str, Any] = Field(..., description="Merged extraction data")
    merge_metadata: MergeMetadata = Field(..., description="Metadata about the merge")
    preview: bool = Field(False, description="Whether this is a preview (not saved)")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
                "submission_id": "550e8400-e29b-41d4-a716-446655440099",
                "merged_data": {
                    "diagnosis": "Type 2 Diabetes Mellitus",
                    "chief_complaints": ["Fatigue", "Increased thirst"],
                    "prescription": [
                        {
                            "medication_name": "Metformin",
                            "dosage": "500mg",
                            "frequency": "Twice daily"
                        }
                    ]
                },
                "merge_metadata": {
                    "source_count": 2,
                    "target_template_code": "OP_GENERAL",
                    "merge_timestamp": "2025-11-19T10:30:00Z",
                    "doctor_confirmed": True,
                    "merge_notes": "Follow-up consolidation",
                    "conflict_count": 1,
                    "conflicts_resolved": ["diagnosis"],
                    "cross_type_scenario": "SAME_TYPE",
                    "consultation_types_merged": ["OP", "OP"]
                },
                "preview": False
            }
        }


class MergeErrorResponse(BaseModel):
    """
    Response model for failed merge operation.
    """
    success: bool = Field(False, description="Always False for error responses")
    error: str = Field(..., description="Error message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Cannot merge extractions from different students"
            }
        }


class MergeAsyncResponse(BaseModel):
    """
    Response model for async merge operation (returns immediately).
    """
    success: bool = Field(..., description="Whether merge was accepted for processing")
    extraction_id: str = Field(..., description="Pre-generated extraction ID for tracking")
    status: str = Field(..., description="Current status: 'processing', 'completed', 'failed'")
    message: str = Field(..., description="Status message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
                "status": "processing",
                "message": "Merge operation started. Use extraction_id to check status or receive webhook."
            }
        }


class MergeStatusResponse(BaseModel):
    """
    Response model for merge status check.
    """
    extraction_id: str = Field(..., description="Extraction ID being checked")
    status: str = Field(..., description="Current status: 'processing', 'completed', 'failed'")
    progress: Optional[str] = Field(None, description="Progress stage if processing")
    merged_data: Optional[Dict[str, Any]] = Field(None, description="Merged data if completed")
    merge_metadata: Optional[MergeMetadata] = Field(None, description="Merge metadata if completed")
    error: Optional[str] = Field(None, description="Error message if failed")
    created_at: Optional[str] = Field(None, description="When merge was initiated")
    completed_at: Optional[str] = Field(None, description="When merge completed")

    class Config:
        json_schema_extra = {
            "example": {
                "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
                "status": "completed",
                "progress": None,
                "merged_data": {"diagnosis": "..."},
                "merge_metadata": {
                    "source_count": 2,
                    "target_template_code": "OP_GENERAL"
                },
                "error": None,
                "created_at": "2025-12-09T10:30:00Z",
                "completed_at": "2025-12-09T10:31:00Z"
            }
        }


class SourceExtractionInfo(BaseModel):
    """
    Information about a source extraction in merge lineage.
    """
    source_extraction_id: str = Field(..., description="Source extraction UUID")
    consultation_type_code: str = Field(..., description="Consultation type of source")
    consultation_type_name: str = Field(..., description="Consultation type name")
    created_at: datetime = Field(..., description="Creation timestamp of source extraction")
    counsellor_name: Optional[str] = Field(None, description="Counsellor who created source extraction")
    merge_order: int = Field(..., description="Chronological order in merge (1=oldest, N=newest)")
    merge_strategy: str = Field(..., description="Strategy used for this source (e.g., 'ai_contextual')")


class MergeLineageResponse(BaseModel):
    """
    Response model for merge lineage information.
    """
    merged_extraction_id: str = Field(..., description="ID of the merged extraction")
    is_merged: bool = Field(..., description="Whether this is a merged extraction")
    source_extractions: List[SourceExtractionInfo] = Field(..., description="List of source extractions")
    merge_metadata: MergeMetadata = Field(..., description="Metadata about the merge")

    class Config:
        json_schema_extra = {
            "example": {
                "merged_extraction_id": "550e8400-e29b-41d4-a716-446655440003",
                "is_merged": True,
                "source_extractions": [
                    {
                        "source_extraction_id": "550e8400-e29b-41d4-a716-446655440001",
                        "consultation_type_code": "OP",
                        "consultation_type_name": "Outpatient Consultation",
                        "created_at": "2025-11-01T09:00:00Z",
                        "counsellor_name": "Dr. Smith",
                        "merge_order": 1,
                        "merge_strategy": "ai_contextual"
                    },
                    {
                        "source_extraction_id": "550e8400-e29b-41d4-a716-446655440002",
                        "consultation_type_code": "OP",
                        "consultation_type_name": "Outpatient Consultation",
                        "created_at": "2025-11-15T10:30:00Z",
                        "counsellor_name": "Dr. Smith",
                        "merge_order": 2,
                        "merge_strategy": "ai_contextual"
                    }
                ],
                "merge_metadata": {
                    "source_count": 2,
                    "target_template_code": "OP_GENERAL",
                    "merge_timestamp": "2025-11-19T10:30:00Z",
                    "doctor_confirmed": True,
                    "merge_notes": "Follow-up consolidation",
                    "conflict_count": 1,
                    "conflicts_resolved": ["diagnosis"],
                    "cross_type_scenario": "SAME_TYPE",
                    "consultation_types_merged": ["OP", "OP"]
                }
            }
        }


class StudentTimelineExtraction(BaseModel):
    """
    Information about an extraction in student timeline.
    """
    extraction_id: str = Field(..., description="Extraction UUID")
    consultation_type_code: str = Field(..., description="Consultation type code")
    consultation_type_name: str = Field(..., description="Consultation type name")
    created_at: datetime = Field(..., description="Creation timestamp")
    counsellor_name: Optional[str] = Field(None, description="Counsellor name")
    is_merged: bool = Field(False, description="Whether this is a merged extraction")
    source_count: int = Field(0, description="Number of source extractions (if merged)")
    segment_count: int = Field(..., description="Number of segments")


class StudentTimelineResponse(BaseModel):
    """
    Response model for student extraction timeline.
    """
    student_id: str = Field(..., description="Student UUID")
    extractions: List[StudentTimelineExtraction] = Field(..., description="List of extractions, chronologically ordered")
    total_count: int = Field(..., description="Total number of extractions")

    class Config:
        json_schema_extra = {
            "example": {
                "student_id": "550e8400-e29b-41d4-a716-446655440050",
                "extractions": [
                    {
                        "extraction_id": "550e8400-e29b-41d4-a716-446655440001",
                        "consultation_type_code": "OP",
                        "consultation_type_name": "Outpatient Consultation",
                        "created_at": "2025-11-01T09:00:00Z",
                        "counsellor_name": "Dr. Smith",
                        "is_merged": False,
                        "source_count": 0,
                        "segment_count": 12
                    },
                    {
                        "extraction_id": "550e8400-e29b-41d4-a716-446655440002",
                        "consultation_type_code": "OP",
                        "consultation_type_name": "Outpatient Consultation",
                        "created_at": "2025-11-15T10:30:00Z",
                        "counsellor_name": "Dr. Smith",
                        "is_merged": False,
                        "source_count": 0,
                        "segment_count": 12
                    },
                    {
                        "extraction_id": "550e8400-e29b-41d4-a716-446655440003",
                        "consultation_type_code": "OP",
                        "consultation_type_name": "Outpatient Consultation",
                        "created_at": "2025-11-19T10:30:00Z",
                        "counsellor_name": "Dr. Smith",
                        "is_merged": True,
                        "source_count": 2,
                        "segment_count": 12
                    }
                ],
                "total_count": 3
            }
        }
