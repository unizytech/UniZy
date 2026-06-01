"""
Multi-Provider Embedding Service

Generates text embeddings using multiple providers:
- Cohere (embed-v4) - Healthcare fine-tuned, default
- OpenAI (text-embedding-3) - High accuracy
- Gemini - Already integrated

Features:
- Provider abstraction via ABC
- Per-school model configuration
- TTL caching for embeddings
- LLM usage tracking
"""

import os
import json
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timezone
from cachetools import TTLCache

logger = logging.getLogger(__name__)


# ============================================================================
# Base Provider ABC
# ============================================================================

class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding providers"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider name"""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return embedding dimensions"""
        pass

    @abstractmethod
    async def generate_embeddings(
        self,
        texts: List[str],
        input_type: str = "search_document"
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            input_type: Type hint for embedding (search_document, search_query)

        Returns:
            Tuple of (embeddings list, usage metadata dict)
        """
        pass


# ============================================================================
# Cohere Provider
# ============================================================================

class CohereProvider(BaseEmbeddingProvider):
    """Cohere embedding provider using embed-english-v3.0"""

    def __init__(self):
        self._client = None
        self._model = "embed-english-v3.0"
        self._dimensions = 1024  # Cohere v3 models output 1024 dimensions

    @property
    def provider_name(self) -> str:
        return "cohere"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self):
        """Lazy load Cohere client"""
        if self._client is None:
            try:
                import cohere
                api_key = os.getenv("COHERE_API_KEY")
                if not api_key:
                    raise ValueError("COHERE_API_KEY environment variable not set")
                self._client = cohere.AsyncClient(api_key=api_key)
            except ImportError:
                raise ImportError("cohere package not installed. Run: pip install cohere")
        return self._client

    async def generate_embeddings(
        self,
        texts: List[str],
        input_type: str = "search_document"
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Generate embeddings using Cohere embed-v4"""
        client = self._get_client()

        # Map input_type to Cohere's expected values
        cohere_input_type = "search_document" if input_type == "search_document" else "search_query"

        start_time = datetime.now(timezone.utc)

        response = await client.embed(
            texts=texts,
            model=self._model,
            input_type=cohere_input_type,
            embedding_types=["float"]
        )

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract embeddings
        embeddings = response.embeddings.float

        # Build usage metadata
        usage = {
            "provider": self.provider_name,
            "model": self._model,
            "input_type": cohere_input_type,
            "text_count": len(texts),
            "dimensions": self._dimensions,
            "duration_ms": duration_ms,
            "billed_units": getattr(response.meta, "billed_units", None) if hasattr(response, "meta") else None,
        }

        return embeddings, usage


# ============================================================================
# OpenAI Provider
# ============================================================================

class OpenAIProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider using text-embedding-3"""

    def __init__(self, model: str = "text-embedding-3-large"):
        self._client = None
        self._model = model
        self._dimensions = 3072 if "large" in model else 1536

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self):
        """Lazy load OpenAI client"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                self._client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")
        return self._client

    async def generate_embeddings(
        self,
        texts: List[str],
        input_type: str = "search_document"
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Generate embeddings using OpenAI text-embedding-3"""
        client = self._get_client()

        start_time = datetime.now(timezone.utc)

        response = await client.embeddings.create(
            input=texts,
            model=self._model
        )

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Extract embeddings
        embeddings = [item.embedding for item in response.data]

        # Build usage metadata
        usage = {
            "provider": self.provider_name,
            "model": self._model,
            "input_type": input_type,
            "text_count": len(texts),
            "dimensions": self._dimensions,
            "duration_ms": duration_ms,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
            "total_tokens": response.usage.total_tokens if response.usage else None,
        }

        return embeddings, usage


# ============================================================================
# Gemini Provider
# ============================================================================

class GeminiProvider(BaseEmbeddingProvider):
    """Gemini embedding provider"""

    def __init__(self):
        self._client = None
        self._model = "gemini-embedding-001"
        self._dimensions = 768

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self):
        """Lazy load Gemini client"""
        if self._client is None:
            try:
                from google import genai
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_API_KEY environment variable not set")
                self._client = genai.Client(api_key=api_key)
            except ImportError:
                raise ImportError("google-genai package not installed")
        return self._client

    async def generate_embeddings(
        self,
        texts: List[str],
        input_type: str = "search_document"
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Generate embeddings using Gemini"""
        client = self._get_client()

        # Gemini's task type mapping
        task_type = "RETRIEVAL_DOCUMENT" if input_type == "search_document" else "RETRIEVAL_QUERY"

        start_time = datetime.now(timezone.utc)

        embeddings = []
        for text in texts:
            response = client.models.embed_content(
                model=self._model,
                contents=text,
                config={"task_type": task_type, "output_dimensionality": self._dimensions}
            )
            embeddings.append(response.embeddings[0].values)

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Build usage metadata
        usage = {
            "provider": self.provider_name,
            "model": self._model,
            "input_type": input_type,
            "text_count": len(texts),
            "dimensions": self._dimensions,
            "duration_ms": duration_ms,
        }

        return embeddings, usage


# ============================================================================
# Embedding Service
# ============================================================================

class EmbeddingService:
    """
    Multi-provider embedding service with caching and LLM tracking.

    Usage:
        service = EmbeddingService()

        # Generate embedding for a query
        embedding, usage = await service.generate_embedding(
            texts=["What are the common diagnoses?"],
            input_type="search_query",
            school_id=school_uuid
        )

        # Embed a full extraction
        await service.embed_extraction(extraction_id)
    """

    # Provider instances (lazy loaded)
    _providers: Dict[str, BaseEmbeddingProvider] = {}

    # Cache for model configs (school_id -> model_config)
    _model_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)  # 1 hour TTL

    # Cache for embeddings (content_hash -> embedding)
    _embedding_cache: TTLCache = TTLCache(maxsize=1000, ttl=3600)  # 1 hour TTL

    def __init__(self):
        pass

    def _get_provider(self, provider_name: str, model_code: str = None) -> BaseEmbeddingProvider:
        """Get or create a provider instance"""
        cache_key = f"{provider_name}_{model_code or 'default'}"

        if cache_key not in self._providers:
            if provider_name == "cohere":
                self._providers[cache_key] = CohereProvider()
            elif provider_name == "openai":
                if model_code == "openai_small":
                    self._providers[cache_key] = OpenAIProvider(model="text-embedding-3-small")
                else:
                    self._providers[cache_key] = OpenAIProvider(model="text-embedding-3-large")
            elif provider_name == "gemini":
                self._providers[cache_key] = GeminiProvider()
            else:
                raise ValueError(f"Unknown provider: {provider_name}")

        return self._providers[cache_key]

    async def get_active_model(self, school_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Get the active embedding model for a school.
        Falls back to default model if no school-specific config.

        Returns dict with: model_code, model_name, provider, dimensions
        """
        from services.supabase_service import supabase

        cache_key = str(school_id) if school_id else "default"

        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        # Try school-specific setting first
        if school_id:
            settings_result = supabase.table("qa_engine_settings")\
                .select("embedding_model_id, embedding_models(*)")\
                .eq("school_id", str(school_id))\
                .limit(1)\
                .execute()

            if settings_result.data and settings_result.data[0].get("embedding_models"):
                model = settings_result.data[0]["embedding_models"]
                config = {
                    "id": model["id"],
                    "model_code": model["model_code"],
                    "model_name": model["model_name"],
                    "provider": model["provider"],
                    "dimensions": model["dimensions"],
                }
                self._model_cache[cache_key] = config
                return config

        # Fall back to default model
        default_result = supabase.table("embedding_models")\
            .select("*")\
            .eq("is_default", True)\
            .eq("is_active", True)\
            .limit(1)\
            .execute()

        if default_result.data:
            model = default_result.data[0]
            config = {
                "id": model["id"],
                "model_code": model["model_code"],
                "model_name": model["model_name"],
                "provider": model["provider"],
                "dimensions": model["dimensions"],
            }
            self._model_cache[cache_key] = config
            return config

        # Ultimate fallback to cohere
        return {
            "id": None,
            "model_code": "cohere_v4",
            "model_name": "Cohere Embed v4",
            "provider": "cohere",
            "dimensions": 1536,
        }

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash for content change detection"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def generate_embedding(
        self,
        texts: List[str],
        input_type: str = "search_document",
        school_id: Optional[UUID] = None,
        use_cache: bool = True
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """
        Generate embeddings for texts using the configured model.

        Args:
            texts: List of texts to embed
            input_type: "search_document" for indexing, "search_query" for queries
            school_id: School ID for model lookup
            use_cache: Whether to use cached embeddings

        Returns:
            Tuple of (embeddings list, usage metadata)
        """
        # Get active model config
        model_config = await self.get_active_model(school_id)

        # Check cache for single text
        if use_cache and len(texts) == 1:
            cache_key = f"{model_config['model_code']}:{self._compute_content_hash(texts[0])}"
            if cache_key in self._embedding_cache:
                logger.debug(f"Cache hit for embedding: {cache_key[:32]}...")
                return [self._embedding_cache[cache_key]], {"cache_hit": True}

        # Get provider and generate embeddings
        provider = self._get_provider(model_config["provider"], model_config["model_code"])
        embeddings, usage = await provider.generate_embeddings(texts, input_type)

        # Cache single text embeddings
        if use_cache and len(texts) == 1:
            cache_key = f"{model_config['model_code']}:{self._compute_content_hash(texts[0])}"
            self._embedding_cache[cache_key] = embeddings[0]

        # Add model config to usage
        usage["model_code"] = model_config["model_code"]
        usage["model_name"] = model_config["model_name"]

        return embeddings, usage

    def _prepare_extraction_content(
        self,
        transcript: str,
        extraction_data: Dict[str, Any]
    ) -> str:
        """
        Prepare content for embedding by combining transcript and extraction data.

        Format: [TRANSCRIPT]\n{transcript}\n\n[SEGMENTS]\n{serialized segments}
        """
        parts = []

        # Add transcript
        if transcript:
            parts.append(f"[TRANSCRIPT]\n{transcript}")

        # Add segment values
        segment_parts = []
        for key, value in extraction_data.items():
            if isinstance(value, dict):
                # Serialize nested objects
                segment_parts.append(f"[{key}]\n{json.dumps(value, ensure_ascii=False, indent=2)}")
            elif isinstance(value, list):
                segment_parts.append(f"[{key}]\n{json.dumps(value, ensure_ascii=False, indent=2)}")
            elif value:
                segment_parts.append(f"[{key}]\n{value}")

        if segment_parts:
            parts.append(f"[SEGMENTS]\n" + "\n\n".join(segment_parts))

        return "\n\n".join(parts)

    async def embed_extraction(
        self,
        extraction_id: UUID,
        force: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Generate and store embeddings for an extraction.

        Creates both document-level and segment-level embeddings.

        Args:
            extraction_id: The extraction UUID
            force: If True, re-embed even if hash hasn't changed

        Returns:
            Dict with embedding stats or None if failed
        """
        from services.supabase_service import supabase

        try:
            # Fetch extraction data with counsellor's school_id
            ext_result = supabase.table("extractions")\
                .select(
                    "id, counsellor_id, student_id, consultation_type_id, "
                    "transcript_text, original_extraction_json, edited_extraction_json, "
                    "counsellors(school_id)"
                )\
                .eq("id", str(extraction_id))\
                .limit(1)\
                .execute()

            if not ext_result.data:
                logger.warning(f"Extraction not found: {extraction_id}")
                return None

            ext = ext_result.data[0]
            # Get school_id from the joined counsellors table
            school_id = None
            if ext.get("counsellors") and ext["counsellors"].get("school_id"):
                school_id = UUID(ext["counsellors"]["school_id"])

            # Use edited data if available, otherwise original
            extraction_data = ext.get("edited_extraction_json") or ext.get("original_extraction_json") or {}
            transcript = ext.get("transcript_text") or ""

            # Prepare content for document-level embedding
            doc_content = self._prepare_extraction_content(transcript, extraction_data)
            content_hash = self._compute_content_hash(doc_content)

            # Get active model
            model_config = await self.get_active_model(school_id)

            # Check if embedding exists and is unchanged
            if not force:
                existing = supabase.table("extraction_embeddings")\
                    .select("id, content_hash")\
                    .eq("extraction_id", str(extraction_id))\
                    .eq("model_id", model_config["id"])\
                    .limit(1)\
                    .execute()

                if existing.data and existing.data[0].get("content_hash") == content_hash:
                    logger.debug(f"Extraction {extraction_id} embedding unchanged, skipping")
                    return {"skipped": True, "reason": "content_unchanged"}

            # Generate document embedding
            embeddings, usage = await self.generate_embedding(
                texts=[doc_content],
                input_type="search_document",
                school_id=school_id,
                use_cache=False  # Don't cache for storage operations
            )

            # Pad embedding to 1536 dimensions if needed (max supported by HNSW index)
            embedding = embeddings[0]
            if len(embedding) < 1536:
                embedding = embedding + [0.0] * (1536 - len(embedding))

            # Upsert document embedding
            doc_embedding_data = {
                "extraction_id": str(extraction_id),
                "model_id": model_config["id"],
                "embedding": embedding,
                "embedded_content": doc_content[:10000],  # Truncate for storage
                "content_hash": content_hash,
                "school_id": str(school_id) if school_id else None,
                "counsellor_id": ext.get("counsellor_id"),
                "student_id": ext.get("student_id"),
                "consultation_type_id": ext.get("consultation_type_id"),
                "token_count": usage.get("total_tokens") or len(doc_content.split()),
            }

            supabase.table("extraction_embeddings")\
                .upsert(doc_embedding_data, on_conflict="extraction_id,model_id")\
                .execute()

            # Generate segment-level embeddings
            segment_count = 0
            for segment_code, segment_value in extraction_data.items():
                if not segment_value:
                    continue

                # Prepare segment content
                if isinstance(segment_value, (dict, list)):
                    segment_content = json.dumps(segment_value, ensure_ascii=False, indent=2)
                else:
                    segment_content = str(segment_value)

                if len(segment_content) < 20:  # Skip very short segments
                    continue

                # Generate segment embedding
                seg_embeddings, seg_usage = await self.generate_embedding(
                    texts=[segment_content],
                    input_type="search_document",
                    school_id=school_id,
                    use_cache=False
                )

                seg_embedding = seg_embeddings[0]
                if len(seg_embedding) < 1536:
                    seg_embedding = seg_embedding + [0.0] * (1536 - len(seg_embedding))

                seg_content_hash = self._compute_content_hash(segment_content)

                seg_embedding_data = {
                    "extraction_id": str(extraction_id),
                    "segment_code": segment_code,
                    "model_id": model_config["id"],
                    "embedding": seg_embedding,
                    "embedded_content": segment_content[:5000],
                    "content_hash": seg_content_hash,
                    "school_id": str(school_id) if school_id else None,
                    "counsellor_id": ext.get("counsellor_id"),
                    "student_id": ext.get("student_id"),
                    "token_count": seg_usage.get("total_tokens") or len(segment_content.split()),
                }

                supabase.table("segment_embeddings")\
                    .upsert(seg_embedding_data, on_conflict="extraction_id,segment_code,model_id")\
                    .execute()

                segment_count += 1

            logger.info(f"Embedded extraction {extraction_id}: 1 document + {segment_count} segments")

            return {
                "extraction_id": str(extraction_id),
                "model_code": model_config["model_code"],
                "document_embedded": True,
                "segment_count": segment_count,
                "duration_ms": usage.get("duration_ms"),
            }

        except Exception as e:
            logger.error(f"Failed to embed extraction {extraction_id}: {e}", exc_info=True)
            return {"error": str(e)}


# Singleton instance
embedding_service = EmbeddingService()
