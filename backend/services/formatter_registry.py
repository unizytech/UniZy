"""
Formatter Registry - Empty Payload Generators

Maps formatter_code (from templates.formatter_code) to a thin wrapper that
invokes the underlying EHR formatter with placeholder/empty context values.
Used by GET /api/v1/ehr/template-schema to return the empty formatted payload
shape a consumer should expect to POST to their EHR API.

The real formatters live in their respective EHR service modules; this file
only provides the invocation glue with empty context so the response shape
can be previewed without real student/counsellor/visit data.
"""

import logging
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


def _empty_aosta(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.aosta_service import format_for_aosta
    return format_for_aosta(
        extraction_insights=extraction,
        student_id="",
        counsellor_id="",
        school_code="",
        ip_id=None,
        op_id=None,
    )


def _empty_raster_op(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.raster_api_service import format_for_raster
    return format_for_raster(
        extraction_insights=extraction,
        uhid="",
        visit_number="",
        consultant_id=0,
        modified_user_id=0,
        created_user_id=0,
        sex=None,
    )


def _empty_raster_new_op(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.raster_api_service import format_for_raster_new_op
    return format_for_raster_new_op(
        extraction_insights=extraction,
        uhid="",
        visit_number="",
        consultant_id=0,
        modified_user_id=0,
        sex=None,
        template_id_raster=None,
    )


def _empty_kg_initial(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.kg_service import format_for_kg
    return format_for_kg(
        extraction_data=extraction,
        student_id="",
        counsellor_id="",
        extraction_id="",
        counsellor_name="",
        uhid="",
        visit_id="",
    )


def _empty_kg_reassess(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.kg_service import format_for_kg_reassess
    return format_for_kg_reassess(
        extraction_data=extraction,
        student_id="",
        counsellor_id="",
        extraction_id="",
        counsellor_name="",
        uhid="",
        visit_id="",
    )


def _empty_kg_nephro_initial(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.kg_nephro_service import format_for_kg_nephro
    return format_for_kg_nephro(
        extraction_data=extraction,
        student_id="",
        counsellor_id="",
        extraction_id="",
        counsellor_name="",
        uhid="",
        visit_id="",
    )


def _empty_kg_nephro_reassess(extraction: Dict[str, Any], template_code: str) -> Dict[str, Any]:
    from services.kg_nephro_service import format_for_kg_nephro_reassess
    return format_for_kg_nephro_reassess(
        extraction_data=extraction,
        student_id="",
        counsellor_id="",
        extraction_id="",
        counsellor_name="",
        uhid="",
        visit_id="",
    )


EMPTY_PAYLOAD_GENERATORS: Dict[str, Callable[[Dict[str, Any], str], Dict[str, Any]]] = {
    "aosta": _empty_aosta,
    "raster_op": _empty_raster_op,
    "raster_new_op": _empty_raster_new_op,
    "kg_initial": _empty_kg_initial,
    "kg_reassess": _empty_kg_reassess,
    "kg_nephro_initial": _empty_kg_nephro_initial,
    "kg_nephro_reassess": _empty_kg_nephro_reassess,
}


# Fields populated from recording metadata or formatter-hardcoded context (not
# from extraction data). Stripped from empty_formatted_payload responses so
# consumers see only extraction-derived shape. Supports dot-paths for nesting.
METADATA_FIELDS: Dict[str, list] = {
    "aosta": [
        "RegNumber", "Ipid", "Opid", "PractitionerId", "HospitalId",
    ],
    "raster_op": [
        "uhid", "visit_number", "consultant_id", "modified_user_id",
    ],
    "raster_new_op": [
        "patientDetail.uhid", "patientDetail.visit_number",
        "patientDetail.consultant_id", "patientDetail.modified_user_id",
        "patientDetail.sex", "patientDetail.template_id_raster",
    ],
    "kg_initial": [
        "student_id", "uhid", "visit_id", "role", "counsellor_id", "extraction_id",
        "form_type", "timestamp", "counsellor_name", "time", "vitals.date_time",
    ],
    "kg_reassess": [
        "student_id", "uhid", "visit_id", "role", "counsellor_id", "extraction_id",
        "form_type", "timestamp", "counsellor_name", "time", "vitals.date_time",
    ],
    "kg_nephro_initial": [
        "student_id", "uhid", "visit_id", "role", "counsellor_id", "extraction_id",
        "form_type", "timestamp", "counsellor_name", "time", "vitals.date_time",
    ],
    "kg_nephro_reassess": [
        "student_id", "uhid", "visit_id", "role", "counsellor_id", "extraction_id",
        "form_type", "timestamp", "counsellor_name", "time",
    ],
    "neopead": [],  # Neopead payload is extraction-driven; no fixed metadata fields
}


def _strip_metadata_fields(payload: Dict[str, Any], dot_paths: list) -> Dict[str, Any]:
    """Remove specified dot-path keys from the payload in-place and return it."""
    for path in dot_paths:
        parts = path.split(".")
        target = payload
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                target = None
                break
            target = target[part]
        if isinstance(target, dict):
            target.pop(parts[-1], None)
    return payload


def generate_empty_formatted_payload(
    formatter_code: str,
    empty_extraction: Dict[str, Any],
    template_code: str,
) -> Optional[Dict[str, Any]]:
    """
    Invoke the registered empty-payload generator for the given formatter_code
    and strip recording-metadata / formatter-context fields so the response
    shows only extraction-derived shape.

    Returns None if formatter_code is unknown or the generator raises.
    """
    generator = EMPTY_PAYLOAD_GENERATORS.get(formatter_code)
    if not generator:
        logger.info(f"[FORMATTER_REGISTRY] No generator registered for formatter_code='{formatter_code}'")
        return None

    try:
        payload = generator(empty_extraction, template_code)
        return _strip_metadata_fields(payload, METADATA_FIELDS.get(formatter_code, []))
    except Exception as e:
        logger.warning(
            f"[FORMATTER_REGISTRY] Empty payload generation failed for "
            f"formatter_code='{formatter_code}', template_code='{template_code}': {e}"
        )
        return None


# ──────────────────────────────────────────────────────────────────────
# Live KG payload formatters (used at extraction-completion time by
# ehr_routing_service._send_to_kg). Keyed by templates.formatter_code so
# adding a new KG-flavored formatter only requires registering once
# here — no need to touch the dispatch site downstream.
# ──────────────────────────────────────────────────────────────────────


def _live_kg_initial(**kwargs) -> Dict[str, Any]:
    from services.kg_service import format_for_kg
    return format_for_kg(**kwargs)


def _live_kg_reassess(**kwargs) -> Dict[str, Any]:
    from services.kg_service import format_for_kg_reassess
    return format_for_kg_reassess(**kwargs)


def _live_kg_nephro_initial(**kwargs) -> Dict[str, Any]:
    from services.kg_nephro_service import format_for_kg_nephro
    return format_for_kg_nephro(**kwargs)


def _live_kg_nephro_reassess(**kwargs) -> Dict[str, Any]:
    from services.kg_nephro_service import format_for_kg_nephro_reassess
    return format_for_kg_nephro_reassess(**kwargs)


KG_LIVE_FORMATTERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "kg_initial": _live_kg_initial,
    "kg_reassess": _live_kg_reassess,
    "kg_nephro_initial": _live_kg_nephro_initial,
    "kg_nephro_reassess": _live_kg_nephro_reassess,
}


def format_kg_payload(formatter_code: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Dispatch to the registered KG live formatter for this formatter_code.

    Returns None if formatter_code is not a KG-family formatter — caller
    treats this as "skip KG send" (likely a misconfig: template points at
    a non-KG formatter but the counsellor/school is routed to KG).
    """
    fmt = KG_LIVE_FORMATTERS.get(formatter_code)
    if not fmt:
        return None
    return fmt(**kwargs)
