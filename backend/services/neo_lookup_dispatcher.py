"""
NEO Lookup Dispatcher

Unified entry point for applying template-specific Raster/Neopaed lookups
to extraction payloads. Routes to the correct lookup function based on
template code.

Called from:
- extraction_service.py (before initial DB save)
- extractions.py (before edit DB persist)
- ehr_routing_service.py (before API send, as safety net)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def apply_template_lookups(payload: Dict[str, Any], template_code: Optional[str]) -> Dict[str, Any]:
    """
    Apply template-specific lookups + sentence capitalization to a payload.

    Routes to the correct lookup function based on template code.
    Returns the payload unchanged if no matching template is found.

    Args:
        payload: The extraction payload dict
        template_code: Template code (e.g., NEO_DAILY, NEO_PROFORMA)

    Returns:
        Normalized payload
    """
    template_upper = (template_code or "").upper()

    try:
        if template_upper in ["NEO_DAILY", "NEONATAL_DAILY"]:
            from services.raster_lookups import apply_raster_lookups_to_neo_daily
            return apply_raster_lookups_to_neo_daily(payload)

        elif template_upper in ["NEO_PROFORMA", "NEONATAL_PROFORMA"]:
            from services.neo_proforma_lookups import apply_raster_lookups_to_neo_proforma
            return apply_raster_lookups_to_neo_proforma(payload)

        elif template_upper in ["NEO_OP", "NEONATAL_OP"]:
            from services.raster_lookups import apply_raster_lookups_to_neo_op
            return apply_raster_lookups_to_neo_op(payload)

        elif template_upper in ["NEO_ADMISSION", "NEONATAL_ADMISSION"]:
            from services.neo_admission_lookups import apply_raster_lookups_to_neo_admission
            return apply_raster_lookups_to_neo_admission(payload)

        elif template_upper in ["NEO_DISCHARGE", "NEONATAL_DISCHARGE"]:
            from services.neo_discharge_lookups import apply_raster_lookups_to_neo_discharge
            return apply_raster_lookups_to_neo_discharge(payload)

        elif template_upper == "NEO_PROFORMA_FREE":
            from services.neo_free_text_lookups import apply_lookups_neo_proforma_free
            return apply_lookups_neo_proforma_free(payload)

        elif template_upper == "NEO_DISCHARGE_FREE":
            from services.neo_free_text_lookups import apply_lookups_neo_discharge_free
            return apply_lookups_neo_discharge_free(payload)

        elif template_upper == "NEO_POSTNATAL_DAY_FREE":
            from services.neo_free_text_lookups import apply_lookups_neo_postnatal_day_free
            return apply_lookups_neo_postnatal_day_free(payload)

        elif template_upper == "NEO_POSTNATAL_DISCHARGE_FREE":
            from services.neo_free_text_lookups import apply_lookups_neo_postnatal_discharge_free
            return apply_lookups_neo_postnatal_discharge_free(payload)

    except Exception as e:
        logger.warning(f"[LOOKUP_DISPATCHER] Failed to apply lookups for {template_upper}: {e}")

    return payload
