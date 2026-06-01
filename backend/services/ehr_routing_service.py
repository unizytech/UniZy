"""
EHR Routing Service - Unified Counsellor-Based EHR Routing

This service provides unified routing logic for sending extractions to EHR systems
based on the counsellor's assigned EHR type (counsellor.ehr_type_id).

Key Features:
- Counsellor-based routing: Counsellor's ehr_type_id determines which EHR to send to
- School config: School's config provides the URL and credentials for that EHR type
- Unified triggers: Both extraction creation AND edit/save trigger EHR sync
- Fire-and-forget: All EHR sends are non-blocking (asyncio.create_task)
- Single query: Uses DB function for minimal latency impact

URL Construction:
- Base URL: school_ehr.api_url > ehr_types.default_api_url
- Suffix: template_ehr.url_suffix (looked up by template + counsellor's ehr_type)
- Final: base_url + (url_suffix or '')
"""

import asyncio
import logging
from typing import Dict, Any, Optional

import httpx

from services.supabase_service import supabase

logger = logging.getLogger(__name__)

# Shared httpx client for EHR API calls (avoids per-request TCP/TLS setup overhead)
_ehr_http_client: Optional[httpx.AsyncClient] = None


def _get_ehr_http_client() -> httpx.AsyncClient:
    global _ehr_http_client
    if _ehr_http_client is None or _ehr_http_client.is_closed:
        _ehr_http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _ehr_http_client


async def get_counsellor_ehr_config(counsellor_id: str, template_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get EHR routing configuration for a counsellor using single DB query.

    Uses the get_counsellor_ehr_config SQL function for minimal latency.

    Args:
        counsellor_id: Counsellor UUID as string
        template_code: Optional template code for URL suffix lookup (needed for Neopead)

    Returns:
        Dict with {ehr_code, school_id, api_url, api_key, url_suffix} or None if:
        - Counsellor has no ehr_type_id
        - School has no config for counsellor's EHR type
        - School EHR config has no api_url and ehr_types has no default_api_url
    """
    try:
        result = supabase.rpc("get_counsellor_ehr_config", {
            "p_counsellor_id": counsellor_id,
            "p_template_code": template_code
        }).execute()

        if result.data and len(result.data) > 0:
            config = result.data[0]
            logger.info(
                f"[EHR_ROUTING] Found EHR config for counsellor {counsellor_id}: "
                f"ehr_code={config.get('ehr_code')}, "
                f"has_url={bool(config.get('api_url'))}, "
                f"suffix={config.get('url_suffix')}"
            )
            return config

        logger.debug(f"[EHR_ROUTING] No EHR config for counsellor {counsellor_id}")
        return None

    except Exception as e:
        logger.warning(f"[EHR_ROUTING] Failed to get EHR config for counsellor {counsellor_id}: {e}")
        return None


async def route_to_ehr(
    counsellor_id: str,
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    template_code: Optional[str] = None,
    is_edit: bool = False,
    extraction_id: Optional[str] = None,
) -> bool:
    """
    Route extraction to EHR based on counsellor's ehr_type_id.

    Called on BOTH extraction creation AND edit/save.
    Uses single DB function for minimal latency.

    Args:
        counsellor_id: Counsellor UUID as string
        extraction_data: The extraction insights dict (original or edited)
        patient_info: Student info dict containing:
            - student_id: Student external ID (e.g., UHID)
            - school_code: School code for Aosta
            - ip_id/op_id: Visit IDs for Aosta
            - visit_number: Visit number for Raster
            - consultant_id: Consultant ID for Raster
            - modified_user_id: Modified user ID for Raster
            - (other fields as needed per EHR)
        template_code: Template code (needed for Neopead URL suffix + formatting)
        is_edit: True if this is an edit/save operation (vs creation)

    Returns:
        True if EHR sync was attempted, False if skipped (no EHR config)

    Note:
        This function does NOT raise exceptions. All errors are logged and
        the function returns False. The main extraction flow should continue
        even if EHR sync fails.
    """
    action = "edit" if is_edit else "creation"

    try:
        # Get EHR config using single DB query
        config = await get_counsellor_ehr_config(counsellor_id, template_code)

        if not config:
            logger.info(f"[EHR_ROUTING] No EHR config for counsellor {counsellor_id} - skipping EHR sync on {action}")
            return False

        ehr_code = config.get("ehr_code")
        base_url = config.get("api_url")
        api_key = config.get("api_key")
        url_suffix = config.get("url_suffix") or ""

        if not base_url:
            logger.info(f"[EHR_ROUTING] No API URL for counsellor {counsellor_id} EHR {ehr_code} - skipping")
            return False

        # Construct final URL (base + suffix for neopead templates)
        final_url = base_url + url_suffix

        logger.info(
            f"[EHR_ROUTING] Routing to {ehr_code} for counsellor {counsellor_id} on {action}: "
            f"url={final_url[:50]}..., template={template_code}"
        )

        # Route to appropriate formatter + sender
        if ehr_code == "aosta":
            await _send_to_aosta(
                extraction_data=extraction_data,
                patient_info=patient_info,
                api_url=final_url,
                api_key=api_key,
                extraction_id=extraction_id,
                template_code=template_code,
            )
        elif ehr_code == "raster":
            await _send_to_raster_emr(
                extraction_data=extraction_data,
                patient_info=patient_info,
                api_url=final_url,
                api_key=api_key,
                extraction_id=extraction_id,
                template_code=template_code,
            )
        elif ehr_code == "raster_new":
            await _send_to_raster_emr(
                extraction_data=extraction_data,
                patient_info=patient_info,
                api_url=final_url,
                api_key=api_key,
                extraction_id=extraction_id,
                template_code=template_code,
            )
        elif ehr_code == "kg_ehr":
            await _send_to_kg(
                extraction_data=extraction_data,
                patient_info=patient_info,
                template_code=template_code,
                api_url=final_url,
                api_key=api_key,
                extraction_id=extraction_id,
            )
        else:
            logger.warning(f"[EHR_ROUTING] Unknown EHR code '{ehr_code}' - skipping")
            return False

        return True

    except Exception as e:
        logger.error(f"[EHR_ROUTING] Failed to route to EHR for counsellor {counsellor_id}: {e}", exc_info=True)
        return False


async def _send_to_aosta(
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
    extraction_id: Optional[str] = None,
    template_code: Optional[str] = None,
) -> None:
    """
    Format and send extraction to Aosta EHR.

    Dispatches to template-specific formatters. Currently supports:
    - AOSTA_OP → format_for_aosta()
    - GEM_CASE_SHEET / GCC_REVIEW → _send_to_gem() (delegated)
    Unknown templates are skipped silently.

    Args:
        extraction_data: The extraction insights dict
        patient_info: Must contain: student_id, school_code, and optionally ip_id, op_id
        api_url: Aosta API URL
        api_key: Optional API key for authentication
        extraction_id: Extraction UUID for storing ehr_payload_json
        template_code: Template code for dispatch (e.g., AOSTA_OP)
    """
    from services.aosta_service import format_for_aosta, send_to_aosta

    template_upper = (template_code or "").upper()

    # GEM_CASE_SHEET, GCC_REVIEW, and GEM_BREAST_CENTRE hit the Aosta URL but use different payload shapes
    if template_upper in ("GEM_CASE_SHEET", "GCC_REVIEW", "GEM_BREAST_CENTRE"):
        await _send_to_gem(
            extraction_data=extraction_data,
            patient_info=patient_info,
            api_url=api_url,
            api_key=api_key,
            extraction_id=extraction_id,
            template_code=template_code,
        )
        return

    try:
        if template_upper != "AOSTA_OP":
            logger.info(
                f"[EHR_ROUTING:AOSTA] No Aosta formatter for template '{template_code}' — skipping"
            )
            return

        payload = format_for_aosta(
            extraction_insights=extraction_data,
            student_id=patient_info.get("student_id", ""),
            counsellor_id=patient_info.get("counsellor_id", ""),
            school_code=patient_info.get("school_code", ""),
            ip_id=patient_info.get("ip_id"),
            op_id=patient_info.get("op_id")
        )

        # Store the EXACT Aosta payload to ehr_payload_json
        if extraction_id:
            try:
                supabase.table("extractions")\
                    .update({"ehr_payload_json": payload})\
                    .eq("id", extraction_id).execute()
            except Exception as e:
                logger.warning(f"[EHR_ROUTING:AOSTA] Failed to store ehr_payload_json: {e}")

        # Send to Aosta
        result = await send_to_aosta(
            payload=payload,
            api_url=api_url,
            api_key=api_key
        )

        if result.get("success"):
            logger.info(f"[EHR_ROUTING:AOSTA] Successfully sent to Aosta")
        else:
            logger.warning(f"[EHR_ROUTING:AOSTA] Aosta returned error: {result}")

    except Exception as e:
        logger.error(f"[EHR_ROUTING:AOSTA] Failed to send to Aosta: {e}")


async def _send_to_gem(
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
    extraction_id: Optional[str] = None,
    template_code: Optional[str] = None,
) -> None:
    """Format and send GEM_CASE_SHEET / GCC_REVIEW extractions to the Aosta API URL.

    Both templates share the same Aosta identifiers + Medicines/Investigations
    builders but carry different content fields, and require Template_id /
    Template_Name from recording_metadata (plumbed via patient_info).
    """
    from services.aosta_service import (
        format_for_gem_case_sheet,
        format_for_gcc_review,
        format_for_aosta_gem_breast_centre,
        send_to_aosta,
    )

    template_upper = (template_code or "").upper()
    try:
        common_args = dict(
            extraction_insights=extraction_data,
            student_id=patient_info.get("student_id", ""),
            counsellor_id=patient_info.get("counsellor_id", ""),
            school_code=patient_info.get("school_code", ""),
            template_id=patient_info.get("template_id_aosta", ""),
            template_name=patient_info.get("template_name_aosta", ""),
            ip_id=patient_info.get("ip_id"),
            op_id=patient_info.get("op_id"),
        )

        if template_upper == "GEM_CASE_SHEET":
            payload = format_for_gem_case_sheet(**common_args)
        elif template_upper == "GCC_REVIEW":
            payload = format_for_gcc_review(**common_args)
        elif template_upper == "GEM_BREAST_CENTRE":
            payload = format_for_aosta_gem_breast_centre(**common_args)
        else:
            logger.info(f"[EHR_ROUTING:GEM] No GEM formatter for template '{template_code}' — skipping")
            return

        if extraction_id:
            try:
                supabase.table("extractions")\
                    .update({"ehr_payload_json": payload})\
                    .eq("id", extraction_id).execute()
            except Exception as e:
                logger.warning(f"[EHR_ROUTING:GEM] Failed to store ehr_payload_json: {e}")

        result = await send_to_aosta(payload=payload, api_url=api_url, api_key=api_key)

        if result.get("success"):
            logger.info(f"[EHR_ROUTING:GEM] Successfully sent {template_upper} to Aosta URL")
        else:
            logger.warning(f"[EHR_ROUTING:GEM] {template_upper} send returned error: {result}")

    except Exception as e:
        logger.error(f"[EHR_ROUTING:GEM] Failed to send {template_upper}: {e}")


async def _send_to_raster_emr(
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
    extraction_id: Optional[str] = None,
    template_code: Optional[str] = None,
) -> None:
    """
    Format and send extraction to Raster General EMR.

    Dispatches to template-specific formatters. Currently supports:
    - RASTER_OP → format_for_raster()
    Unknown templates are skipped silently.

    Args:
        extraction_data: The extraction insights dict
        patient_info: Must contain: student_id (uhid), visit_number, consultant_id, modified_user_id
        api_url: Raster EMR API URL
        api_key: Optional API key for authentication
        extraction_id: Extraction UUID for storing ehr_payload_json
        template_code: Template code for dispatch (e.g., RASTER_OP)
    """
    from services.raster_api_service import format_for_raster, format_for_raster_new_op, _sanitize_escaped_slashes

    try:
        # Template dispatch — only format+send for known templates
        template_upper = (template_code or "").upper()
        if template_upper not in ("RASTER_OP", "RASTER_NEW_OP"):
            logger.info(
                f"[EHR_ROUTING:RASTER] No Raster formatter for template '{template_code}' — skipping"
            )
            return

        # created_user_id is the primary user ID; modified_user_id defaults to same
        _created_user_id = patient_info.get("created_user_id") or patient_info.get("modified_user_id", 0)

        # Dispatch to template-specific formatter
        if template_upper == "RASTER_NEW_OP":
            payload = format_for_raster_new_op(
                extraction_insights=extraction_data,
                uhid=patient_info.get("student_id", ""),
                visit_number=patient_info.get("visit_number", ""),
                consultant_id=patient_info.get("consultant_id", 0),
                modified_user_id=_created_user_id,
                sex=patient_info.get("sex"),
                template_id_raster=patient_info.get("template_id_raster"),
            )
        elif template_upper == "RASTER_OP":
            payload = format_for_raster(
                extraction_insights=extraction_data,
                uhid=patient_info.get("student_id", ""),
                visit_number=patient_info.get("visit_number", ""),
                consultant_id=patient_info.get("consultant_id", 0),
                modified_user_id=_created_user_id,
                created_user_id=_created_user_id,
                sex=patient_info.get("sex"),
            )

        # Sanitize escaped slashes before sending
        payload = _sanitize_escaped_slashes(payload)

        # Store the EXACT Raster payload to ehr_payload_json
        if extraction_id:
            try:
                supabase.table("extractions")\
                    .update({"ehr_payload_json": payload})\
                    .eq("id", extraction_id).execute()
            except Exception as e:
                logger.warning(f"[EHR_ROUTING:RASTER] Failed to store ehr_payload_json: {e}")

        # Build headers
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Send to Raster EMR
        client = _get_ehr_http_client()
        response = await client.post(api_url, json=payload, headers=headers)

        if 200 <= response.status_code < 300:
            logger.info(f"[EHR_ROUTING:RASTER] Successfully sent to Raster EMR")
        else:
            logger.warning(f"[EHR_ROUTING:RASTER] Raster returned status {response.status_code}")

    except Exception as e:
        logger.error(f"[EHR_ROUTING:RASTER] Failed to send to Raster EMR: {e}")


async def _send_to_kg(
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    api_url: str,
    api_key: Optional[str] = None,
    extraction_id: Optional[str] = None,
    template_code: Optional[str] = None,
) -> None:
    """
    Format and send extraction to KG School EHR.

    Resolves the live formatter via templates.formatter_code (single source
    of truth, shared with the empty-preview path). Adding a new KG-flavored
    template is a DB + formatter_registry change only — no edits here.

    Args:
        extraction_data: The extraction insights dict
        patient_info: Must contain: student_id (UHID), counsellor_id, patient_uuid, visit_id
        api_url: KG School API URL
        api_key: Optional API key for authentication
        extraction_id: Extraction UUID for storing ehr_payload_json
        template_code: Template code used for the extraction (drives formatter lookup)
    """
    from services.kg_service import send_to_kg
    from services.formatter_registry import format_kg_payload

    try:
        if not template_code:
            logger.info("[EHR_ROUTING:KG] No template_code provided — skipping")
            return

        # Resolve formatter_code from templates (SSOT)
        try:
            tpl_result = supabase.table("templates")\
                .select("formatter_code")\
                .eq("template_code", template_code)\
                .limit(1).execute()
        except Exception as e:
            logger.warning(
                f"[EHR_ROUTING:KG] Failed to look up template '{template_code}': {e}"
            )
            return

        if not tpl_result.data:
            logger.info(
                f"[EHR_ROUTING:KG] Template '{template_code}' not found — skipping"
            )
            return

        formatter_code = (tpl_result.data[0].get("formatter_code") or "").strip()
        if not formatter_code:
            logger.info(
                f"[EHR_ROUTING:KG] Template '{template_code}' has no "
                f"formatter_code — skipping"
            )
            return

        # Counsellor name for payload
        counsellor_name = ""
        counsellor_id = patient_info.get("counsellor_id", "")
        if counsellor_id:
            try:
                doc_result = supabase.table("counsellors")\
                    .select("full_name").eq("id", counsellor_id).limit(1).execute()
                if doc_result.data:
                    counsellor_name = doc_result.data[0].get("full_name", "")
            except Exception as e:
                logger.warning(f"[EHR_ROUTING:KG] Failed to fetch counsellor name: {e}")

        formatter_args = dict(
            extraction_data=extraction_data,
            student_id=patient_info.get("patient_uuid", ""),
            counsellor_id=counsellor_id,
            extraction_id=extraction_id or "",
            counsellor_name=counsellor_name,
            uhid=patient_info.get("student_id", ""),
            visit_id=patient_info.get("visit_id", ""),
            role=patient_info.get("role", ""),
        )

        # Dispatch via the registry. None means formatter_code isn't a KG
        # formatter (misconfig: counsellor routed to KG with a non-KG template).
        payload = format_kg_payload(formatter_code, **formatter_args)
        if payload is None:
            logger.info(
                f"[EHR_ROUTING:KG] No KG formatter registered for "
                f"formatter_code='{formatter_code}' (template "
                f"'{template_code}') — skipping"
            )
            return

        # Persist EXACT payload sent to KG
        if extraction_id:
            try:
                supabase.table("extractions")\
                    .update({"ehr_payload_json": payload})\
                    .eq("id", extraction_id).execute()
            except Exception as e:
                logger.warning(
                    f"[EHR_ROUTING:KG] Failed to store ehr_payload_json: {e}"
                )

        # Send to KG School
        result = await send_to_kg(payload=payload, api_url=api_url, api_key=api_key)
        if result.get("success"):
            logger.info("[EHR_ROUTING:KG] Successfully sent to KG School EHR")
        else:
            logger.warning(f"[EHR_ROUTING:KG] KG School returned error: {result}")

    except Exception as e:
        logger.error(f"[EHR_ROUTING:KG] Failed to send to KG School: {e}")


def schedule_ehr_sync(
    counsellor_id: str,
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    template_code: Optional[str] = None,
    is_edit: bool = False,
    extraction_id: Optional[str] = None,
) -> bool:
    """
    Schedule EHR sync as a fire-and-forget background task.

    This is the main entry point for EHR routing. It wraps route_to_ehr()
    in asyncio.create_task() to ensure it doesn't block the main flow.

    Args:
        counsellor_id: Counsellor UUID as string
        extraction_data: The extraction insights dict
        patient_info: Student info dict (see route_to_ehr for required fields)
        template_code: Template code (needed for Neopead)
        is_edit: True if this is an edit/save operation

    Returns:
        True if task was scheduled, False if counsellor_id is missing
    """
    if not counsellor_id:
        logger.debug("[EHR_ROUTING] No counsellor_id provided - skipping EHR sync")
        return False

    action = "edit" if is_edit else "creation"

    try:
        asyncio.create_task(_route_to_ehr_safe(
            counsellor_id=counsellor_id,
            extraction_data=extraction_data,
            patient_info=patient_info,
            template_code=template_code,
            is_edit=is_edit,
            extraction_id=extraction_id,
        ))
        logger.info(f"[EHR_ROUTING] Scheduled EHR sync for counsellor {counsellor_id} on {action}")
        return True

    except Exception as e:
        logger.warning(f"[EHR_ROUTING] Failed to schedule EHR sync: {e}")
        return False


async def _route_to_ehr_safe(
    counsellor_id: str,
    extraction_data: Dict[str, Any],
    patient_info: Dict[str, Any],
    template_code: Optional[str] = None,
    is_edit: bool = False,
    extraction_id: Optional[str] = None,
) -> None:
    """
    Safe wrapper for route_to_ehr that catches all exceptions.

    This ensures the background task never raises unhandled exceptions.
    """
    try:
        await route_to_ehr(
            counsellor_id=counsellor_id,
            extraction_data=extraction_data,
            patient_info=patient_info,
            template_code=template_code,
            is_edit=is_edit,
            extraction_id=extraction_id,
        )
    except Exception as e:
        action = "edit" if is_edit else "creation"
        logger.error(f"[EHR_ROUTING] Unhandled error in EHR sync for counsellor {counsellor_id} on {action}: {e}")
