"""
Clinical Condition Ingestion Service

Enhanced ingestion pipeline for structured clinical guidelines:
1. Validate JSON against Pydantic schema
2. Store master condition record
3. Extract semantic chunks using ClinicalChunkingService
4. Generate embeddings for each chunk
5. Store chunks with embeddings

Supports all 3 document types:
- narrative_guideline (e.g., Hypertension)
- visual_workflow (e.g., Rhinosinusitis)
- step_protocol (e.g., Epistaxis)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from .clinical_condition_models import (
    ClinicalGuidelineDocument,
    ClinicalCondition,
    DocumentType,
    validate_guideline_json,
    get_validation_errors,
)
from .clinical_chunking_service import (
    ClinicalChunkingService,
    ClinicalChunk,
    get_clinical_chunking_service,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of a clinical condition ingestion job."""
    job_id: Optional[str] = None
    status: str = "pending"  # pending, validating, processing, embedding, completed, failed
    file_name: Optional[str] = None

    # Counts
    total_conditions: int = 0
    processed_conditions: int = 0
    total_chunks: int = 0
    embedded_chunks: int = 0

    # Details
    condition_ids: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    validation_errors: Optional[List[Dict[str, Any]]] = None
    duration_seconds: Optional[float] = None


@dataclass
class ConditionIngestionResult:
    """Result of ingesting a single condition."""
    condition_id: str
    condition_db_id: Optional[str] = None
    status: str = "success"
    chunks_created: int = 0
    chunks_embedded: int = 0
    error_message: Optional[str] = None


class ClinicalConditionIngestionService:
    """
    Service for ingesting structured clinical condition JSON into the database.

    Pipeline:
    1. Validate JSON against schema
    2. Create ingestion job record
    3. For each condition:
       a. Store in clinical_conditions table
       b. Extract semantic chunks
       c. Generate embeddings
       d. Store chunks and embeddings
    4. Update job status

    Usage:
        service = ClinicalConditionIngestionService()

        # From JSON file
        result = await service.ingest_from_file(
            file_path="/path/to/hypertension.json",
            supabase_client=supabase
        )

        # From JSON data
        result = await service.ingest_from_json(
            json_data={...},
            file_name="hypertension.json",
            supabase_client=supabase
        )
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client
        self._embedding_service = None
        self._chunking_service = None

    @property
    def embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            from services.qa.embedding_service import EmbeddingService
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    @property
    def chunking_service(self) -> ClinicalChunkingService:
        """Lazy load chunking service."""
        if self._chunking_service is None:
            self._chunking_service = get_clinical_chunking_service()
        return self._chunking_service

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash for content change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def ingest_from_file(
        self,
        file_path: str,
        supabase_client=None
    ) -> IngestionResult:
        """
        Ingest clinical conditions from a JSON file.

        Args:
            file_path: Path to JSON file
            supabase_client: Supabase client for DB operations

        Returns:
            IngestionResult with job status
        """
        import os
        file_name = os.path.basename(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except Exception as e:
            return IngestionResult(
                status="failed",
                file_name=file_name,
                error_message=f"Failed to read file: {e}"
            )

        return await self.ingest_from_json(
            json_data=json_data,
            file_name=file_name,
            supabase_client=supabase_client
        )

    async def ingest_from_json(
        self,
        json_data: Dict[str, Any],
        file_name: str = "unknown.json",
        supabase_client=None
    ) -> IngestionResult:
        """
        Ingest clinical conditions from JSON data.

        Args:
            json_data: Parsed JSON data
            file_name: Source file name for tracking
            supabase_client: Supabase client for DB operations

        Returns:
            IngestionResult with job status
        """
        client = supabase_client or self.supabase
        if not client:
            return IngestionResult(
                status="failed",
                file_name=file_name,
                error_message="Supabase client required for ingestion"
            )

        start_time = datetime.now(timezone.utc)
        result = IngestionResult(file_name=file_name)

        # Step 1: Validate JSON
        result.status = "validating"
        validation_errors = get_validation_errors(json_data)
        if validation_errors:
            result.status = "failed"
            result.validation_errors = validation_errors
            result.error_message = f"Validation failed with {len(validation_errors)} errors"
            return result

        # Parse validated document
        try:
            document = validate_guideline_json(json_data)
        except Exception as e:
            result.status = "failed"
            result.error_message = f"Validation error: {e}"
            return result

        # Extract metadata
        meta = document.document_meta
        document_type = meta.document_type or self._infer_document_type(document)

        # Step 2: Create ingestion job record
        job_data = {
            "file_name": file_name,
            "source_name": meta.source,
            "specialty": meta.specialty,
            "document_type": document_type.value if isinstance(document_type, DocumentType) else document_type,
            "status": "processing",
            "total_conditions": len(document.conditions),
            "started_at": start_time.isoformat(),
        }

        try:
            job_result = client.table("clinical_condition_ingestion_jobs").insert(job_data).execute()
            result.job_id = job_result.data[0]["id"] if job_result.data else None
        except Exception as e:
            logger.warning(f"Failed to create ingestion job record: {e}")

        result.status = "processing"
        result.total_conditions = len(document.conditions)

        # Step 3: Process each condition
        condition_results = []
        total_chunks = 0
        total_embedded = 0

        for condition in document.conditions:
            try:
                cond_result = await self._ingest_condition(
                    condition=condition,
                    document_meta=meta,
                    document_type=document_type,
                    supabase_client=client
                )
                condition_results.append(cond_result)
                result.condition_ids.append(condition.condition_id)
                total_chunks += cond_result.chunks_created
                total_embedded += cond_result.chunks_embedded
                result.processed_conditions += 1

                # Update job progress
                if result.job_id:
                    client.table("clinical_condition_ingestion_jobs").update({
                        "processed_conditions": result.processed_conditions,
                        "total_chunks": total_chunks,
                        "embedded_chunks": total_embedded,
                    }).eq("id", result.job_id).execute()

            except Exception as e:
                logger.error(f"Failed to ingest condition {condition.condition_id}: {e}", exc_info=True)
                condition_results.append(ConditionIngestionResult(
                    condition_id=condition.condition_id,
                    status="failed",
                    error_message=str(e)
                ))

        # Step 4: Finalize
        result.total_chunks = total_chunks
        result.embedded_chunks = total_embedded
        result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Check for failures
        failed_conditions = [r for r in condition_results if r.status == "failed"]
        if failed_conditions:
            if len(failed_conditions) == len(condition_results):
                result.status = "failed"
                result.error_message = f"All {len(failed_conditions)} conditions failed to ingest"
            else:
                result.status = "completed"
                result.error_message = f"{len(failed_conditions)} of {len(condition_results)} conditions failed"
        else:
            result.status = "completed"

        # Update job record
        if result.job_id:
            client.table("clinical_condition_ingestion_jobs").update({
                "status": result.status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "total_chunks": total_chunks,
                "embedded_chunks": total_embedded,
                "error_message": result.error_message,
            }).eq("id", result.job_id).execute()

        logger.info(
            f"[INGESTION] Completed: {result.processed_conditions}/{result.total_conditions} conditions, "
            f"{total_chunks} chunks, {total_embedded} embeddings in {result.duration_seconds:.1f}s"
        )

        return result

    async def _ingest_condition(
        self,
        condition: ClinicalCondition,
        document_meta,
        document_type: DocumentType,
        supabase_client
    ) -> ConditionIngestionResult:
        """
        Ingest a single clinical condition.

        Args:
            condition: Validated ClinicalCondition
            document_meta: Document metadata
            document_type: Type of source document
            supabase_client: Supabase client

        Returns:
            ConditionIngestionResult
        """
        result = ConditionIngestionResult(condition_id=condition.condition_id)

        # Step 1: Store master condition record
        condition_record = {
            "condition_id": condition.condition_id,
            "name": condition.name,
            "aliases": condition.aliases,
            "icd_codes": condition.icd_codes,
            "source_name": document_meta.source,
            "specialty": document_meta.specialty,
            "document_type": document_type.value if isinstance(document_type, DocumentType) else document_type,
            "version": document_meta.version,
            "language": document_meta.language,
            "classification": condition.classification.model_dump() if condition.classification else None,
            "triage_metadata": condition.triage_metadata.model_dump(),
            "clinical_presentation": condition.clinical_presentation.model_dump() if condition.clinical_presentation else None,
            "differential_diagnosis": [
                d.model_dump() if hasattr(d, 'model_dump') else {"condition": d}
                for d in condition.differential_diagnosis
            ] if condition.differential_diagnosis else None,
            "investigations": condition.investigations.model_dump() if condition.investigations else None,
            "treatment_by_care_level": condition.treatment_by_care_level.model_dump() if condition.treatment_by_care_level else None,
            "comorbidity_pathways": [p.model_dump() for p in condition.comorbidity_pathways] if condition.comorbidity_pathways else None,
            "drug_formulary": [d.model_dump() for d in condition.drug_formulary] if condition.drug_formulary else None,
            "step_wise_management": condition.step_wise_management.model_dump() if condition.step_wise_management else None,
            "emergency_protocols": condition.emergency_protocols.model_dump() if condition.emergency_protocols else None,
            "follow_up": condition.follow_up.model_dump() if condition.follow_up else None,
            "student_education": condition.student_education.model_dump() if condition.student_education else None,
            "full_json": condition.model_dump(),
            "is_active": True,
            "is_verified": False,
        }

        # Check if condition already exists (upsert)
        existing = supabase_client.table("clinical_conditions").select("id").eq(
            "condition_id", condition.condition_id
        ).execute()

        if existing.data:
            # Update existing
            condition_db_id = existing.data[0]["id"]
            supabase_client.table("clinical_conditions").update(
                condition_record
            ).eq("id", condition_db_id).execute()
            logger.info(f"[INGESTION] Updated existing condition: {condition.condition_id}")

            # Delete old chunks (will cascade to embeddings)
            supabase_client.table("clinical_chunks").delete().eq(
                "condition_id", condition_db_id
            ).execute()
        else:
            # Insert new
            insert_result = supabase_client.table("clinical_conditions").insert(
                condition_record
            ).execute()
            condition_db_id = insert_result.data[0]["id"]
            logger.info(f"[INGESTION] Created new condition: {condition.condition_id}")

        result.condition_db_id = condition_db_id

        # Step 2: Extract semantic chunks
        chunks = self.chunking_service.chunk_condition(condition, document_type)
        result.chunks_created = len(chunks)

        # Step 3: Store chunks and generate embeddings
        for chunk in chunks:
            try:
                # Store chunk
                chunk_record = {
                    "condition_id": condition_db_id,
                    "chunk_type": chunk.chunk_type.value,
                    "chunk_index": chunk.chunk_index,
                    "content_json": chunk.content_json,
                    "content_text": chunk.content_text,
                    "urgency_default": chunk.urgency_default,
                    "has_emergency_triggers": chunk.has_emergency_triggers,
                    "has_red_flags": chunk.has_red_flags,
                    "care_levels": chunk.care_levels,
                    "comorbidity": chunk.comorbidity,
                    "numeric_thresholds": chunk.numeric_thresholds,
                    "drug_classes": chunk.drug_classes,
                    "drug_names": chunk.drug_names,
                    "contraindications": chunk.contraindications,
                    "source_section": chunk.source_section,
                }

                chunk_result = supabase_client.table("clinical_chunks").insert(
                    chunk_record
                ).execute()
                chunk_db_id = chunk_result.data[0]["id"]

                # Generate embedding
                try:
                    embeddings, usage = await self.embedding_service.generate_embedding(
                        texts=[chunk.content_text],
                        input_type="search_document",
                        use_cache=False
                    )

                    if embeddings:
                        # Pad to 1536 dimensions if needed
                        embedding = embeddings[0]
                        if len(embedding) < 1536:
                            embedding = embedding + [0.0] * (1536 - len(embedding))

                        content_hash = self._compute_content_hash(chunk.content_text)

                        embedding_record = {
                            "chunk_id": chunk_db_id,
                            "embedding": embedding,
                            "embedding_model": usage.get("model_name", "cohere-embed-english-v3.0"),
                            "content_hash": content_hash,
                        }

                        supabase_client.table("clinical_chunk_embeddings").insert(
                            embedding_record
                        ).execute()
                        result.chunks_embedded += 1

                except Exception as e:
                    logger.warning(f"Failed to embed chunk {chunk.chunk_type}: {e}")

            except Exception as e:
                logger.error(f"Failed to store chunk {chunk.chunk_type}: {e}")

        return result

    def _infer_document_type(self, document: ClinicalGuidelineDocument) -> DocumentType:
        """
        Infer document type from content structure.

        Args:
            document: Validated document

        Returns:
            Inferred DocumentType
        """
        if not document.conditions:
            return DocumentType.NARRATIVE_GUIDELINE

        condition = document.conditions[0]

        # Step protocol: has step_wise_management with ordered steps
        if condition.step_wise_management and condition.step_wise_management.steps:
            return DocumentType.STEP_PROTOCOL

        # Visual workflow: has when_to_suspect dict, clinical_scenarios, or red_flags_for_referral
        if condition.when_to_suspect or condition.clinical_scenarios:
            return DocumentType.VISUAL_WORKFLOW

        if condition.triage_metadata.red_flags_for_referral:
            return DocumentType.VISUAL_WORKFLOW

        # Narrative: has classification, comorbidity_pathways, or drug_formulary
        if condition.classification or condition.comorbidity_pathways or condition.drug_formulary:
            return DocumentType.NARRATIVE_GUIDELINE

        # Default
        return DocumentType.NARRATIVE_GUIDELINE


# Singleton instance
_ingestion_service = None


def get_clinical_condition_ingestion_service() -> ClinicalConditionIngestionService:
    """Get singleton ClinicalConditionIngestionService instance."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = ClinicalConditionIngestionService()
    return _ingestion_service
