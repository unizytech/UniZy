"""Build the reference media-object envelope from a keyed-insights extraction.

The extraction pipeline produces (and stores) insights as a *keyed object*:

    { "participants": {...}, "keyFacts": [...], "studentContext": {...}, ... }

The downstream consumer (web app) expects the reference format in
``references/updated_meeting_response_structure.json`` — a *media object* whose
insights live in a ``customBusinessInsights`` array, each item self-describing
(``key``/``label``/``ordinal``/``valueType`` + the dual ``value``/``parsedValue``
representation), wrapped in media-level fields + array-form ``metadata`` +
``transcription``.

This module performs ONLY that envelope transform. It does not change the insight
content — the per-segment field shapes are already conformed upstream by
``extraction_output_formatter.complete_to_schema``. Keep the two separate:

    raw insights --(complete_to_schema)--> conformed insights --(this)--> reference envelope

Pure Python. The optional ``segment_meta`` map (label / ordinal / valueType per
output key) is what makes the output match the reference *exactly*; without it the
builder infers sensible defaults from the values themselves. Fetch that map from
``segment_definitions`` via :func:`fetch_segment_meta` (a DB call — only call it from
fire-and-forget paths, never the critical path).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template gate
# ---------------------------------------------------------------------------
# The reference media-object envelope is the contract for the career-counselling
# web app ONLY. Every other template keeps emitting the keyed-insights shape on
# all channels (DB / webhook / realtime). Gate on a CAREER prefix so the current
# 'CAREER_DISCUSSION' template and any future 'career_*' variants are covered.
REFERENCE_ENVELOPE_TEMPLATE_PREFIX = "CAREER"


def applies_to_template(template_code: Optional[str]) -> bool:
    """True iff this template should receive the reference envelope (career_* only)."""
    return bool(template_code) and str(template_code).upper().startswith(
        REFERENCE_ENVELOPE_TEMPLATE_PREFIX
    )


# ---------------------------------------------------------------------------
# valueType inference / value-field construction
# ---------------------------------------------------------------------------

def _infer_value_type(value: Any) -> str:
    """Infer the reference ``valueType`` tag from a Python value.

    Mirrors the tags used in the reference: OBJECT, OBJECT_ARRAY, STRING_ARRAY,
    STRING, LONG, BOOLEAN. A caller-supplied segment_meta value type always wins
    over this (so e.g. an empty ``tasks`` list still reports OBJECT_ARRAY).
    """
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, (int, float)):
        return "LONG"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, dict):
        return "OBJECT"
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            return "OBJECT_ARRAY"
        return "STRING_ARRAY"
    return "STRING"  # None / unknown


def _build_value_field(value: Any, value_type: str) -> List[str]:
    """Build the reference ``value`` array (the stringified representation).

    Reference conventions:
      * OBJECT / OBJECT_ARRAY -> single-element array holding the JSON string
      * STRING_ARRAY          -> the list of strings as-is (scalars stringified)
      * STRING                -> single-element array holding the plain string
      * LONG / BOOLEAN        -> single-element array holding the JSON scalar
    """
    if value_type in ("OBJECT", "OBJECT_ARRAY"):
        return [json.dumps(value if value is not None else ({} if value_type == "OBJECT" else []),
                           ensure_ascii=False)]
    if value_type == "STRING_ARRAY":
        return [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
                for x in (value or [])]
    if value_type == "STRING":
        if value is None:
            return [""]
        return [value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)]
    # LONG / BOOLEAN / unknown
    if value is None:
        return []
    return [json.dumps(value, ensure_ascii=False)]


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_custom_business_insights(
    insights: Dict[str, Any],
    media_id: str,
    segment_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> List[Dict[str, Any]]:
    """Turn the keyed ``insights`` dict into a ``customBusinessInsights`` array.

    Each output item carries id / mediaId / key / label / ordinal / valueType /
    value / parsedValue / enabled, matching the reference item shape.

    Args:
        insights: keyed insights ({output_key: content}).
        media_id: the media object's id (becomes each item's ``mediaId``).
        segment_meta: optional {output_key: {"label", "ordinal", "valueType"}}.
            Any field present overrides the inferred default; missing keys fall
            back to inference (label = Title-cased key, ordinal = position*10,
            valueType = inferred from the value).
        id_factory: returns a fresh id per item (injectable for deterministic tests).

    Items are returned sorted by ordinal, then by original insertion order.
    """
    segment_meta = segment_meta or {}
    items: List[Dict[str, Any]] = []

    for position, (key, value) in enumerate(insights.items()):
        meta = segment_meta.get(key, {})
        value_type = meta.get("valueType") or _infer_value_type(value)
        label = meta.get("label") or _default_label(key)
        ordinal = meta.get("ordinal")
        if ordinal is None:
            ordinal = position * 10

        items.append({
            "id": id_factory(),
            "mediaId": media_id,
            "key": key,
            "label": label,
            "ordinal": ordinal,
            "valueType": value_type,
            "value": _build_value_field(value, value_type),
            "parsedValue": value,
            "enabled": True,
            "_position": position,  # tie-breaker, stripped below
        })

    items.sort(key=lambda it: (it["ordinal"], it["_position"]))
    for it in items:
        it.pop("_position", None)
    return items


def envelope_to_keyed(payload: Any) -> Any:
    """Reverse transform: a reference media object -> keyed insights ({key: content}).

    Idempotent and shape-tolerant: if ``payload`` is already keyed (i.e. has no
    ``customBusinessInsights`` array) it is returned unchanged. Used at the edit
    boundary so the web app may POST *either* the envelope or raw keyed insights,
    while internal storage (``edited_extraction_json`` + its many consumers) stays
    keyed. Each item's ``parsedValue`` is the native content; we fall back to
    decoding the stringified ``value`` only if ``parsedValue`` is absent.
    """
    if not isinstance(payload, dict):
        return payload
    cbi = payload.get("customBusinessInsights")
    if not isinstance(cbi, list):
        return payload  # already keyed / not an envelope
    keyed: Dict[str, Any] = {}
    for item in cbi:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key:
            continue
        if item.get("parsedValue") is not None:
            keyed[key] = item["parsedValue"]
        else:
            keyed[key] = _decode_value_field(item.get("value"), item.get("valueType"))
    return keyed


def _decode_value_field(value: Any, value_type: Optional[str]) -> Any:
    """Best-effort inverse of :func:`_build_value_field` (used only when parsedValue is missing)."""
    if value_type in ("OBJECT", "OBJECT_ARRAY"):
        if isinstance(value, list) and value and isinstance(value[0], str):
            try:
                return json.loads(value[0])
            except Exception:
                return {} if value_type == "OBJECT" else []
        return {} if value_type == "OBJECT" else []
    if value_type == "STRING_ARRAY":
        return value if isinstance(value, list) else []
    if value_type == "STRING":
        return value[0] if isinstance(value, list) and value else ""
    # LONG / BOOLEAN / unknown
    if isinstance(value, list) and value:
        try:
            return json.loads(value[0]) if isinstance(value[0], str) else value[0]
        except Exception:
            return value[0]
    return None


def build_reference_envelope(
    insights: Dict[str, Any],
    *,
    transcript: Optional[str] = None,
    segment_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    media_info: Optional[Dict[str, Any]] = None,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> Dict[str, Any]:
    """Build the full reference media object from keyed insights.

    Args:
        insights: keyed insights ({output_key: content}).
        transcript: full transcription text (-> transcription.originalTranscription).
        segment_meta: per-key label/ordinal/valueType overrides (see
            :func:`build_custom_business_insights`).
        media_info: optional media-level fields. Recognised keys (all optional):
            id, name, mediaType, mediaFormat, mediaSize, storagePath, status,
            mediaDuration, transcriptionId. Anything absent gets a reference-shaped
            default.
        id_factory: id generator (injectable for tests).

    Returns:
        A dict matching ``references/updated_meeting_response_structure.json``.
    """
    media_info = media_info or {}
    media_id = str(media_info.get("id") or id_factory())

    # Array-form metadata (mediaDuration is the documented entry).
    metadata: List[Dict[str, Any]] = []
    media_duration = media_info.get("mediaDuration")
    if media_duration is not None:
        metadata.append({
            "id": id_factory(),
            "key": "mediaDuration",
            "value": str(media_duration),
            "valueType": "LONG",
        })

    transcription = {
        "id": str(media_info.get("transcriptionId") or id_factory()),
        "mediaId": media_id,
        "originalTranscription": transcript or "",
        "editedTranscription": None,
        "originalTimestampedTranscription": None,
        "editedTimestampedTranscription": None,
    }

    return {
        "id": media_id,
        "name": media_info.get("name", ""),
        "mediaType": media_info.get("mediaType", "AUDIO"),
        "mediaFormat": media_info.get("mediaFormat", ""),
        "mediaSize": media_info.get("mediaSize", 0),
        "storagePath": media_info.get("storagePath", ""),
        "status": media_info.get("status", "FE_COMPLETED"),
        "metadata": metadata,
        "transcription": transcription,
        "customBusinessInsights": build_custom_business_insights(
            insights, media_id, segment_meta=segment_meta, id_factory=id_factory,
        ),
    }


def _default_label(output_key: str) -> str:
    """camelCase / snake_case output key -> Title Case label ('studentContext' -> 'Student Context')."""
    out: List[str] = []
    for i, ch in enumerate(output_key.replace("_", " ")):
        if ch.isupper() and i > 0 and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
    return "".join(out).strip().title()


# ---------------------------------------------------------------------------
# Optional DB-backed segment metadata (fire-and-forget paths only)
# ---------------------------------------------------------------------------

def fetch_segment_meta(output_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    """Look up label/ordinal/valueType for the given output keys from segment_definitions.

    Returns {output_key: {"label", "ordinal", "valueType"}}. Output key is
    camelCase(segment_code); we match by deriving the same camelCase from each
    definition's segment_code. ``valueType`` is mapped from the schema's top-level
    JSON type. Best-effort: any lookup failure returns {} (builder falls back to
    inference). Performs a DB read — do NOT call from the critical path.
    """
    try:
        from services.supabase_service import supabase
        wanted = set(output_keys)
        rows = (
            supabase.table("segment_definitions")
            .select("segment_code, segment_name, display_order, schema_definition_json")
            .eq("is_active", True)
            .execute()
        ).data or []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[REF_ENVELOPE] segment_meta lookup failed: {e}")
        return {}

    meta: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        code = row.get("segment_code") or ""
        out_key = _to_camel(code)
        if out_key not in wanted or out_key in meta:
            continue
        meta[out_key] = {
            "label": row.get("segment_name") or _default_label(out_key),
            "ordinal": row.get("display_order"),
            "valueType": _value_type_from_schema(row.get("schema_definition_json")),
        }
    return meta


# Module-level cache of the full segment_code -> meta map. segment_definitions
# changes very rarely; this avoids a DB read on every webhook / realtime publish.
_SEGMENT_META_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def get_segment_meta_cached(output_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    """Cached wrapper over :func:`fetch_segment_meta` (loads the full map once).

    Returns the subset for ``output_keys``. Falls back to a fresh fetch for any
    key not in the cache (e.g. a newly added segment), so a stale cache degrades
    to "missing keys get inferred", never to wrong data.
    """
    global _SEGMENT_META_CACHE
    if _SEGMENT_META_CACHE is None:
        _SEGMENT_META_CACHE = fetch_segment_meta_all()
    result = {k: _SEGMENT_META_CACHE[k] for k in output_keys if k in _SEGMENT_META_CACHE}
    missing = [k for k in output_keys if k not in result]
    if missing:
        result.update(fetch_segment_meta(missing))
    return result


def fetch_segment_meta_all() -> Dict[str, Dict[str, Any]]:
    """Fetch label/ordinal/valueType for ALL active segments (used to seed the cache)."""
    try:
        from services.supabase_service import supabase
        rows = (
            supabase.table("segment_definitions")
            .select("segment_code, segment_name, display_order, schema_definition_json")
            .eq("is_active", True)
            .execute()
        ).data or []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[REF_ENVELOPE] segment_meta (all) lookup failed: {e}")
        return {}
    meta: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        out_key = _to_camel(row.get("segment_code") or "")
        if out_key and out_key not in meta:
            meta[out_key] = {
                "label": row.get("segment_name") or _default_label(out_key),
                "ordinal": row.get("display_order"),
                "valueType": _value_type_from_schema(row.get("schema_definition_json")),
            }
    return meta


def _format_from_mime(value: Optional[str]) -> str:
    """Normalise a mime type or format hint to the reference's mediaFormat tag (e.g. 'MP3').

    'audio/mpeg' -> 'MP3', 'audio/webm' -> 'WEBM', 'audio/wav' -> 'WAV', 'mp3' -> 'MP3'.
    """
    if not value:
        return ""
    v = str(value).strip().lower()
    if "/" in v:  # a mime type like 'audio/mpeg;codecs=...'
        v = v.split("/", 1)[1].split(";")[0].strip()
    return {
        "mpeg": "MP3", "mp3": "MP3", "webm": "WEBM", "wav": "WAV", "x-wav": "WAV",
        "mp4": "MP4", "m4a": "M4A", "x-m4a": "M4A", "ogg": "OGG", "flac": "FLAC",
    }.get(v, v.upper())


def build_envelope_for_extraction(
    insights: Dict[str, Any],
    *,
    media_id: str,
    transcript: Optional[str] = None,
    recording_metadata: Optional[Dict[str, Any]] = None,
    media_format: Optional[str] = None,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> Dict[str, Any]:
    """Single entry point used by every exit channel (DB store, webhook, realtime).

    Centralising this guarantees the three channels emit an identical envelope
    shape — the structure can only change in one place, and the contract test
    pins that place to the reference file.

    Args:
        insights: the conformed keyed insights.
        media_id: stable id for the media object (use the extraction_id).
        transcript: full transcript (-> transcription.originalTranscription).
        recording_metadata: session recording metadata; media-level fields are
            read from it best-effort (duration / size / storage path / name).
    """
    rm = recording_metadata or {}
    media_info = {
        "id": media_id,
        "name": rm.get("media_name") or rm.get("file_name") or rm.get("filename") or "",
        "mediaType": rm.get("media_type") or "AUDIO",
        "mediaFormat": _format_from_mime(media_format or rm.get("media_format") or rm.get("audio_format")),
        "mediaSize": rm.get("media_size") or rm.get("file_size") or 0,
        "storagePath": rm.get("storage_path") or rm.get("audio_url") or "",
        "status": "FE_COMPLETED",
        "mediaDuration": rm.get("media_duration") or rm.get("duration") or rm.get("audio_duration"),
    }
    segment_meta = get_segment_meta_cached(list(insights.keys()))
    return build_reference_envelope(
        insights,
        transcript=transcript,
        segment_meta=segment_meta,
        media_info=media_info,
        id_factory=id_factory,
    )


def _to_camel(segment_code: str) -> str:
    """UPPER_SNAKE_CASE segment_code -> camelCase output key ('STUDENT_CONTEXT' -> 'studentContext')."""
    parts = segment_code.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:]) if parts else segment_code


def _value_type_from_schema(schema: Any) -> Optional[str]:
    """Map a segment's JSON-schema top-level type to a reference valueType tag."""
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except Exception:
            return None
    if not isinstance(schema, dict):
        return None
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t == "object":
        return "OBJECT"
    if t == "array":
        items = schema.get("items")
        if isinstance(items, dict) and items.get("type") == "object":
            return "OBJECT_ARRAY"
        return "STRING_ARRAY"
    if t == "string":
        return "STRING"
    if t in ("number", "integer"):
        return "LONG"
    if t == "boolean":
        return "BOOLEAN"
    return None
