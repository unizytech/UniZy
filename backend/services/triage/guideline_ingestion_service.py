"""
Clinical Guideline Ingestion Service

Phase 3 of Triage Engine Multi-Layer system.
Handles ingestion, chunking, and embedding of clinical guidelines:
- PDF text extraction
- Intelligent chunking (800-1000 tokens with overlap)
- Embedding generation using existing EmbeddingService
- Database storage

Note: This is the ingestion PIPELINE only. Actual guidelines will be added later.
"""

import os
import re
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class GuidelineMetadata:
    """Metadata for a clinical guideline document."""
    source_name: str  # "ICMR STG", "IAP Guidelines"
    source_organization: str  # "ICMR", "IAP", "NNF"
    document_title: str
    specialty: str  # general_medicine, pediatrics, etc.

    # Optional metadata
    source_url: Optional[str] = None
    publication_year: Optional[int] = None
    version: Optional[str] = None
    evidence_level: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    presentations: List[str] = field(default_factory=list)
    icd_codes: List[str] = field(default_factory=list)


@dataclass
class ChunkResult:
    """Result of text chunking."""
    chunk_text: str
    chunk_index: int
    token_count: int
    start_char: int
    end_char: int


@dataclass
class IngestionResult:
    """Result of guideline ingestion job."""
    job_id: str
    file_name: str
    status: str  # pending, processing, completed, failed
    total_chunks: int = 0
    processed_chunks: int = 0
    embedded_chunks: int = 0
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None


class GuidelineIngestionService:
    """
    Service for ingesting and embedding clinical guidelines.

    Pipeline:
    1. Extract text from PDF (using pdfplumber or PyPDF2)
    2. Clean and normalize text
    3. Chunk text into optimal segments (800-1000 tokens with overlap)
    4. Generate embeddings using EmbeddingService
    5. Store in clinical_guidelines and clinical_guideline_embeddings tables

    Usage:
        service = GuidelineIngestionService()

        # Ingest from PDF file
        result = await service.ingest_pdf(
            pdf_path="/path/to/guideline.pdf",
            metadata=GuidelineMetadata(
                source_name="ICMR STG",
                source_organization="ICMR",
                document_title="Fever Guidelines",
                specialty="general_medicine",
                topics=["fever", "infection"]
            )
        )

        # Ingest from text
        result = await service.ingest_text(
            text="...",
            metadata=metadata
        )
    """

    def __init__(self, supabase_client=None):
        """Initialize with optional Supabase client."""
        self.supabase = supabase_client
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            from services.qa.embedding_service import EmbeddingService
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from a PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text string

        Note: Requires pdfplumber package. Fallback to PyPDF2 if not available.
        """
        try:
            import pdfplumber

            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

            return "\n\n".join(text_parts)

        except ImportError:
            logger.warning("pdfplumber not installed, trying PyPDF2...")
            try:
                import PyPDF2

                text_parts = []
                with open(pdf_path, "rb") as file:
                    reader = PyPDF2.PdfReader(file)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)

                return "\n\n".join(text_parts)

            except ImportError:
                raise ImportError("Neither pdfplumber nor PyPDF2 is installed. Run: pip install pdfplumber")

    def clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text.

        - Remove excessive whitespace
        - Normalize line breaks
        - Remove page numbers and headers
        - Fix common OCR issues
        """
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)

        # Normalize line breaks
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove common header patterns
        text = re.sub(r'Page \d+ of \d+', '', text)
        text = re.sub(r'\d+\s*\|\s*Page', '', text)

        # Fix common OCR issues
        text = text.replace('ﬁ', 'fi').replace('ﬂ', 'fl')
        text = text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')

        return text.strip()

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 800,
        overlap: int = 100,
        min_chunk_size: int = 100
    ) -> List[ChunkResult]:
        """
        Chunk text into optimal segments for embedding.

        Strategy:
        1. Try to split on paragraph boundaries
        2. If paragraph too long, split on sentence boundaries
        3. If sentence too long, split on word boundaries
        4. Add overlap to preserve context

        Args:
            text: Text to chunk
            chunk_size: Target chunk size in tokens (words approximation)
            overlap: Overlap between chunks in tokens
            min_chunk_size: Minimum chunk size (discard smaller)

        Returns:
            List of ChunkResult objects
        """
        chunks = []

        # Split into paragraphs
        paragraphs = text.split('\n\n')

        current_chunk = ""
        current_start = 0
        char_pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                char_pos += 2  # For the \n\n
                continue

            para_tokens = len(para.split())

            # If paragraph alone exceeds chunk size, split by sentences
            if para_tokens > chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    sentence_tokens = len(sentence.split())

                    # If adding sentence exceeds limit, save current chunk
                    if current_chunk and len(current_chunk.split()) + sentence_tokens > chunk_size:
                        if len(current_chunk.split()) >= min_chunk_size:
                            chunks.append(ChunkResult(
                                chunk_text=current_chunk.strip(),
                                chunk_index=len(chunks),
                                token_count=len(current_chunk.split()),
                                start_char=current_start,
                                end_char=char_pos
                            ))

                        # Start new chunk with overlap
                        overlap_text = self._get_overlap_text(current_chunk, overlap)
                        current_chunk = overlap_text + " " + sentence if overlap_text else sentence
                        current_start = char_pos - len(overlap_text)
                    else:
                        current_chunk = (current_chunk + " " + sentence).strip() if current_chunk else sentence

                    char_pos += len(sentence) + 1
            else:
                # Add paragraph to current chunk
                if current_chunk and len(current_chunk.split()) + para_tokens > chunk_size:
                    if len(current_chunk.split()) >= min_chunk_size:
                        chunks.append(ChunkResult(
                            chunk_text=current_chunk.strip(),
                            chunk_index=len(chunks),
                            token_count=len(current_chunk.split()),
                            start_char=current_start,
                            end_char=char_pos
                        ))

                    # Start new chunk with overlap
                    overlap_text = self._get_overlap_text(current_chunk, overlap)
                    current_chunk = overlap_text + " " + para if overlap_text else para
                    current_start = char_pos - len(overlap_text)
                else:
                    current_chunk = (current_chunk + " " + para).strip() if current_chunk else para

            char_pos += len(para) + 2

        # Add final chunk
        if current_chunk and len(current_chunk.split()) >= min_chunk_size:
            chunks.append(ChunkResult(
                chunk_text=current_chunk.strip(),
                chunk_index=len(chunks),
                token_count=len(current_chunk.split()),
                start_char=current_start,
                end_char=char_pos
            ))

        return chunks

    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """Get the last N tokens of text for overlap."""
        words = text.split()
        if len(words) <= overlap_tokens:
            return text
        return " ".join(words[-overlap_tokens:])

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash for content change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def ingest_text(
        self,
        text: str,
        metadata: GuidelineMetadata,
        supabase_client=None
    ) -> IngestionResult:
        """
        Ingest text content as a guideline.

        Args:
            text: Full guideline text
            metadata: GuidelineMetadata with source info
            supabase_client: Supabase client for DB operations

        Returns:
            IngestionResult with job status
        """
        client = supabase_client or self.supabase
        if not client:
            raise ValueError("Supabase client required for ingestion")

        start_time = datetime.now(timezone.utc)

        # Create ingestion job record
        job_data = {
            "file_name": f"{metadata.document_title[:50]}.txt",
            "source_name": metadata.source_name,
            "source_organization": metadata.source_organization,
            "specialty": metadata.specialty,
            "status": "processing",
            "started_at": start_time.isoformat(),
        }

        job_result = client.table("guideline_ingestion_jobs").insert(job_data).execute()
        job_id = job_result.data[0]["id"] if job_result.data else None

        try:
            # Clean and chunk text
            cleaned_text = self.clean_text(text)
            chunks = self.chunk_text(cleaned_text)

            # Update job with chunk count
            client.table("guideline_ingestion_jobs").update({
                "total_chunks": len(chunks)
            }).eq("id", job_id).execute()

            guideline_ids = []
            embedded_count = 0

            for chunk in chunks:
                # Insert guideline chunk
                guideline_data = {
                    "source_name": metadata.source_name,
                    "source_organization": metadata.source_organization,
                    "source_url": metadata.source_url,
                    "document_title": metadata.document_title,
                    "specialty": metadata.specialty,
                    "topics": metadata.topics or [],
                    "presentations": metadata.presentations or [],
                    "icd_codes": metadata.icd_codes or [],
                    "full_text": None,  # Only store in first chunk
                    "chunk_text": chunk.chunk_text,
                    "chunk_index": chunk.chunk_index,
                    "publication_year": metadata.publication_year,
                    "version": metadata.version,
                    "evidence_level": metadata.evidence_level,
                    "is_active": True,
                    "is_verified": False,
                }

                # Store full text only in first chunk
                if chunk.chunk_index == 0:
                    guideline_data["full_text"] = cleaned_text

                gl_result = client.table("clinical_guidelines").insert(guideline_data).execute()
                guideline_id = gl_result.data[0]["id"] if gl_result.data else None
                guideline_ids.append(guideline_id)

                # Generate embedding
                if guideline_id:
                    try:
                        embeddings, usage = await self.embedding_service.generate_embedding(
                            texts=[chunk.chunk_text],
                            input_type="search_document",
                            use_cache=False
                        )

                        # Pad embedding to 1536 dimensions if needed
                        embedding = embeddings[0]
                        if len(embedding) < 1536:
                            embedding = embedding + [0.0] * (1536 - len(embedding))

                        content_hash = self._compute_content_hash(chunk.chunk_text)

                        embedding_data = {
                            "guideline_id": guideline_id,
                            "embedding": embedding,
                            "embedding_model": usage.get("model_name", "cohere-embed-english-v3.0"),
                            "content_hash": content_hash,
                            "token_count": chunk.token_count,
                        }

                        client.table("clinical_guideline_embeddings").insert(embedding_data).execute()
                        embedded_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to embed chunk {chunk.chunk_index}: {e}")

                # Update progress
                client.table("guideline_ingestion_jobs").update({
                    "processed_chunks": chunk.chunk_index + 1,
                    "embedded_chunks": embedded_count,
                }).eq("id", job_id).execute()

            # Mark job complete
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            client.table("guideline_ingestion_jobs").update({
                "status": "completed",
                "completed_at": end_time.isoformat(),
                "processed_chunks": len(chunks),
                "embedded_chunks": embedded_count,
            }).eq("id", job_id).execute()

            return IngestionResult(
                job_id=job_id,
                file_name=job_data["file_name"],
                status="completed",
                total_chunks=len(chunks),
                processed_chunks=len(chunks),
                embedded_chunks=embedded_count,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Ingestion failed: {e}", exc_info=True)

            # Mark job failed
            if job_id:
                client.table("guideline_ingestion_jobs").update({
                    "status": "failed",
                    "error_message": str(e),
                }).eq("id", job_id).execute()

            return IngestionResult(
                job_id=job_id,
                file_name=job_data["file_name"],
                status="failed",
                error_message=str(e),
            )

    async def ingest_pdf(
        self,
        pdf_path: str,
        metadata: GuidelineMetadata,
        supabase_client=None
    ) -> IngestionResult:
        """
        Ingest a PDF file as a guideline.

        Args:
            pdf_path: Path to PDF file
            metadata: GuidelineMetadata with source info
            supabase_client: Supabase client for DB operations

        Returns:
            IngestionResult with job status
        """
        client = supabase_client or self.supabase

        # Create ingestion job record
        file_name = os.path.basename(pdf_path)

        job_data = {
            "file_name": file_name,
            "file_path": pdf_path,
            "source_name": metadata.source_name,
            "source_organization": metadata.source_organization,
            "specialty": metadata.specialty,
            "status": "processing",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        job_result = client.table("guideline_ingestion_jobs").insert(job_data).execute()
        job_id = job_result.data[0]["id"] if job_result.data else None

        try:
            # Extract text from PDF
            text = self.extract_text_from_pdf(pdf_path)

            # Use text ingestion pipeline
            result = await self.ingest_text(text, metadata, supabase_client)

            # Update job record
            result.job_id = job_id
            result.file_name = file_name

            return result

        except Exception as e:
            logger.error(f"PDF ingestion failed: {e}", exc_info=True)

            if job_id:
                client.table("guideline_ingestion_jobs").update({
                    "status": "failed",
                    "error_message": str(e),
                }).eq("id", job_id).execute()

            return IngestionResult(
                job_id=job_id,
                file_name=file_name,
                status="failed",
                error_message=str(e),
            )

    async def ingest_all_guidelines(
        self,
        data_dir: str,
        supabase_client=None
    ) -> Dict[str, Any]:
        """
        Batch ingest all PDF guidelines from a directory.

        Expects a metadata.json file in the directory with guideline info.

        Args:
            data_dir: Directory containing PDFs and metadata.json
            supabase_client: Supabase client for DB operations

        Returns:
            Batch ingestion report
        """
        import json

        metadata_path = os.path.join(data_dir, "metadata.json")
        if not os.path.exists(metadata_path):
            return {"error": "metadata.json not found in data directory"}

        with open(metadata_path, "r") as f:
            metadata_list = json.load(f)

        results = []
        success_count = 0
        failure_count = 0

        for item in metadata_list:
            pdf_file = item.get("file")
            if not pdf_file:
                continue

            pdf_path = os.path.join(data_dir, pdf_file)
            if not os.path.exists(pdf_path):
                logger.warning(f"PDF not found: {pdf_path}")
                failure_count += 1
                continue

            metadata = GuidelineMetadata(
                source_name=item.get("source_name", "Unknown"),
                source_organization=item.get("source_organization", "Unknown"),
                document_title=item.get("document_title", pdf_file),
                specialty=item.get("specialty", "general_medicine"),
                source_url=item.get("source_url"),
                publication_year=item.get("publication_year"),
                version=item.get("version"),
                evidence_level=item.get("evidence_level"),
                topics=item.get("topics", []),
                presentations=item.get("presentations", []),
            )

            result = await self.ingest_pdf(pdf_path, metadata, supabase_client)
            results.append({
                "file": pdf_file,
                "status": result.status,
                "chunks": result.total_chunks,
                "embedded": result.embedded_chunks,
            })

            if result.status == "completed":
                success_count += 1
            else:
                failure_count += 1

        return {
            "success": True,
            "total_files": len(metadata_list),
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results,
        }


# Singleton instance
_ingestion_service = None


def get_guideline_ingestion_service() -> GuidelineIngestionService:
    """Get singleton GuidelineIngestionService instance."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = GuidelineIngestionService()
    return _ingestion_service
