"""
Billing Service - Automated Bill Generation from Extraction Data

This module handles:
- OP bill generation from single extractions
- IP merged bill generation from merged extractions
- Line item creation from extraction JSON (prescriptions, investigations, procedures)
- Price lookups against hospital masters (medicine, investigation, procedure fee)
- Confidence scoring and billing action determination
- Bill supersession for merged workflows
"""

import uuid
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .supabase_service import supabase, get_doctor_hospital_id_cached

logger = logging.getLogger(__name__)

# IP consultation type codes (everything else is OP)
IP_CONSULTATION_TYPES = {"DISCHARGE", "NEO_DISCHARGE", "NEO_DAILY", "NEO_ADMISSION", "IP"}


def _get_match_confidence_lookup(extraction_id: Optional[str]) -> Dict[str, float]:
    """Fetch match confidence for medicines and investigations from audit logs.

    Returns a dict mapping lowercase item name → confidence score.
    """
    if not extraction_id:
        return {}

    lookup = {}
    try:
        # Medicine match confidence
        med_result = supabase.table('medicine_match_log').select(
            'matched_medicine_name, match_confidence'
        ).eq('extraction_id', extraction_id).execute()
        for row in (med_result.data or []):
            name = (row.get('matched_medicine_name') or '').lower().strip()
            if name:
                lookup[name] = row.get('match_confidence', 0) or 0

        # Investigation match confidence
        inv_result = supabase.table('investigation_match_log').select(
            'matched_investigation_name, match_confidence'
        ).eq('extraction_id', extraction_id).execute()
        for row in (inv_result.data or []):
            name = (row.get('matched_investigation_name') or '').lower().strip()
            if name:
                lookup[name] = row.get('match_confidence', 0) or 0
    except Exception as e:
        logger.warning(f"[Billing] Failed to fetch match confidence from logs: {e}")

    return lookup

# High-value threshold for auto-flagging
HIGH_VALUE_THRESHOLD = 5000.0


def generate_bill(
    extraction_id: Optional[str],
    hospital_id: str,
    doctor_id: Optional[str],
    patient_id: Optional[str],
    extraction_data: Dict[str, Any],
    consultation_type_code: Optional[str] = None,
    is_merged: bool = False,
    visit_id: Optional[str] = None,
    visit_date: Optional[str] = None,
    billed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a bill from extraction data.

    Args:
        extraction_id: UUID of the extraction (None for standalone bills)
        hospital_id: UUID of the hospital
        doctor_id: UUID of the doctor
        patient_id: UUID of the patient
        extraction_data: The extraction JSON data
        consultation_type_code: e.g. 'OP', 'DISCHARGE', etc.
        is_merged: Whether this is from a merged extraction
        visit_id: EHR visit ID from recording_metadata
        visit_date: Visit date from recording_metadata
        billed_by: Billed by user from recording_metadata

    Returns:
        Bill record with line items
    """
    # Determine bill type
    bill_type = "IP" if consultation_type_code and consultation_type_code.upper() in IP_CONSULTATION_TYPES else "OP"

    # Build match confidence lookup from audit logs
    confidence_lookup = _get_match_confidence_lookup(extraction_id)

    # Build line items
    line_items = _build_line_items(
        extraction_data=extraction_data,
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        bill_type=bill_type,
        confidence_lookup=confidence_lookup,
    )

    # Calculate totals
    total_amount = 0.0
    auto_billed_amount = 0.0
    pending_review_amount = 0.0
    flagged_amount = 0.0

    for item in line_items:
        item_total = float(item.get("total_price") or 0)
        total_amount += item_total
        action = item.get("billing_action", "pending_review")
        if action == "auto_billed":
            auto_billed_amount += item_total
        elif action == "pending_review":
            pending_review_amount += item_total
        elif action == "flagged_manual":
            flagged_amount += item_total

    # Create bill record
    bill_data = {
        "extraction_id": extraction_id,
        "hospital_id": hospital_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "bill_type": bill_type,
        "bill_status": "draft",
        "consultation_type_code": consultation_type_code,
        "is_merged_bill": is_merged,
        "total_amount": round(total_amount, 2),
        "auto_billed_amount": round(auto_billed_amount, 2),
        "pending_review_amount": round(pending_review_amount, 2),
        "flagged_amount": round(flagged_amount, 2),
        "generation_metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "line_item_count": len(line_items),
            "extraction_id": extraction_id,
        },
    }

    # Add visit tracking fields if provided
    if visit_id:
        bill_data["visit_id"] = visit_id
    if visit_date:
        bill_data["visit_date"] = visit_date
    if billed_by:
        bill_data["billed_by"] = billed_by

    bill_result = supabase.table("bills").insert(bill_data).execute()
    if not bill_result.data:
        raise Exception("Failed to create bill record")

    bill = bill_result.data[0]
    bill_id = bill["id"]

    # Insert line items
    if line_items:
        for item in line_items:
            item["bill_id"] = bill_id

        # Batch insert
        BATCH_SIZE = 100
        for i in range(0, len(line_items), BATCH_SIZE):
            batch = line_items[i:i + BATCH_SIZE]
            supabase.table("bill_line_items").insert(batch).execute()

    # Re-fetch bill with line items
    bill_with_items = supabase.table("bills").select("*").eq("id", bill_id).execute()
    items_result = supabase.table("bill_line_items").select("*").eq("bill_id", bill_id).order("created_at").execute()

    result = bill_with_items.data[0] if bill_with_items.data else bill
    result["line_items"] = items_result.data or []

    logger.info(
        f"[Billing] Generated {bill_type} bill {bill_id} for extraction {extraction_id}: "
        f"{len(line_items)} items, total={total_amount:.2f}, "
        f"auto={auto_billed_amount:.2f}, pending={pending_review_amount:.2f}, flagged={flagged_amount:.2f}"
    )

    return result


def generate_merged_bill(
    extraction_id: str,
    source_extraction_ids: List[str],
    hospital_id: str,
    doctor_id: Optional[str],
    patient_id: Optional[str],
    extraction_data: Dict[str, Any],
    consultation_type_code: Optional[str] = None,
    visit_id: Optional[str] = None,
    visit_date: Optional[str] = None,
    billed_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a bill from a merged extraction and supersede source bills.

    Args:
        extraction_id: UUID of the merged extraction
        source_extraction_ids: UUIDs of source extractions
        hospital_id: Hospital UUID
        doctor_id: Doctor UUID
        patient_id: Patient UUID
        extraction_data: Merged extraction JSON
        consultation_type_code: Consultation type code
        visit_id: EHR visit ID from recording_metadata
        visit_date: Visit date from recording_metadata
        billed_by: Billed by user from recording_metadata

    Returns:
        Merged bill with line items
    """
    # Generate the merged bill
    bill = generate_bill(
        extraction_id=extraction_id,
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        extraction_data=extraction_data,
        consultation_type_code=consultation_type_code,
        is_merged=True,
        visit_id=visit_id,
        visit_date=visit_date,
        billed_by=billed_by,
    )

    merged_bill_id = bill["id"]
    warnings = []

    # Supersede source bills
    if source_extraction_ids:
        source_bills = (
            supabase.table("bills")
            .select("id, bill_status, extraction_id")
            .in_("extraction_id", source_extraction_ids)
            .neq("bill_status", "superseded")
            .execute()
        )

        if source_bills.data:
            for source_bill in source_bills.data:
                if source_bill["bill_status"] == "confirmed":
                    warnings.append(
                        f"Source bill {source_bill['id']} (extraction {source_bill['extraction_id']}) "
                        f"was already confirmed — now superseded"
                    )

                supabase.table("bills").update({
                    "bill_status": "superseded",
                    "superseded_by_bill_id": merged_bill_id,
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("id", source_bill["id"]).execute()

            logger.info(f"[Billing] Superseded {len(source_bills.data)} source bills for merged bill {merged_bill_id}")

    # Update generation_metadata with warnings
    if warnings:
        metadata = bill.get("generation_metadata", {})
        metadata["warnings"] = warnings
        supabase.table("bills").update({
            "generation_metadata": metadata,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", merged_bill_id).execute()
        bill["generation_metadata"] = metadata

    return bill


def _build_line_items(
    extraction_data: Dict[str, Any],
    hospital_id: str,
    doctor_id: Optional[str],
    patient_id: Optional[str],
    bill_type: str,
    confidence_lookup: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Build all line items from extraction data."""
    line_items = []
    confidence_lookup = confidence_lookup or {}

    # 1. Registration/Admission fee
    line_items.extend(_add_registration_line_item(hospital_id, bill_type, patient_id))

    # 2. Consultation fee
    if doctor_id:
        line_items.extend(_add_consultation_line_item(doctor_id, bill_type))

    # 3. Pharmacy (prescriptions)
    line_items.extend(_add_pharmacy_line_items(extraction_data, hospital_id, confidence_lookup))

    # 4. Investigations (lab + radiology)
    line_items.extend(_add_investigation_line_items(extraction_data, hospital_id, confidence_lookup))

    # 5. Procedures
    line_items.extend(_add_procedure_line_items(extraction_data, hospital_id))

    # 6. Room charges (IP only)
    if bill_type == "IP" and patient_id:
        line_items.extend(_add_room_line_items(patient_id, hospital_id))

    return line_items


def _add_registration_line_item(hospital_id: str, bill_type: str, patient_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Add registration (OP) or admission (IP) fee from hospital settings.

    OP registration is only charged for first-time patients (no prior bills).
    IP admission is charged per admission.
    """
    try:
        result = supabase.table("hospitals").select(
            "op_registration_fee, ip_admission_fee"
        ).eq("id", hospital_id).limit(1).execute()

        if not result.data:
            return []

        hospital = result.data[0]

        if bill_type == "OP":
            fee = hospital.get("op_registration_fee")
            if fee is not None:
                # Only charge OP registration for first-time patients
                if patient_id:
                    existing_bills = (
                        supabase.table("bills")
                        .select("id")
                        .eq("patient_id", patient_id)
                        .eq("hospital_id", hospital_id)
                        .neq("bill_status", "superseded")
                        .limit(1)
                        .execute()
                    )
                    if existing_bills.data:
                        logger.info(f"[Billing] Skipping OP registration fee — patient {patient_id} has prior bills")
                        return []

                confidence, action = _determine_confidence("registration", float(fee), 1.0)
                return [{
                    "category": "registration",
                    "description": "OP Registration Fee",
                    "quantity": 1,
                    "unit_price": float(fee),
                    "total_price": float(fee),
                    "confidence": confidence,
                    "billing_action": action,
                    "source_segment": "registration",
                }]
        else:
            fee = hospital.get("ip_admission_fee")
            if fee is not None:
                confidence, action = _determine_confidence("admission", float(fee), 1.0)
                return [{
                    "category": "admission",
                    "description": "IP Admission Fee",
                    "quantity": 1,
                    "unit_price": float(fee),
                    "total_price": float(fee),
                    "confidence": confidence,
                    "billing_action": action,
                    "source_segment": "registration",
                }]
    except Exception as e:
        logger.warning(f"[Billing] Failed to fetch hospital fees: {e}")

    return []


def _add_consultation_line_item(doctor_id: str, bill_type: str) -> List[Dict[str, Any]]:
    """Add consultation fee from doctor record."""
    try:
        result = supabase.table("doctors").select(
            "full_name, op_consultation_fee, ip_primary_consultation_fee, ip_secondary_consultation_fee"
        ).eq("id", doctor_id).limit(1).execute()

        if not result.data:
            return []

        doctor = result.data[0]
        doctor_name = doctor.get("full_name", "Doctor")

        if bill_type == "OP":
            fee = doctor.get("op_consultation_fee")
        else:
            fee = doctor.get("ip_primary_consultation_fee")

        if fee is not None:
            confidence, action = _determine_confidence("consultation", float(fee), 1.0)
            return [{
                "category": "consultation",
                "description": f"Consultation Fee - {doctor_name}",
                "quantity": 1,
                "unit_price": float(fee),
                "total_price": float(fee),
                "confidence": confidence,
                "billing_action": action,
                "source_segment": "doctor_identity",
            }]
    except Exception as e:
        logger.warning(f"[Billing] Failed to fetch doctor fees: {e}")

    return []


def _add_pharmacy_line_items(extraction_data: Dict[str, Any], hospital_id: str, confidence_lookup: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Map prescription items to line items using hospital medicine list prices.

    Price lookup is strictly by _external_id (set during extraction post-processing).
    Hospital medicine lists must have external_id populated for billing to work.
    Match confidence is read from audit logs (confidence_lookup), not extraction JSON.
    """
    line_items = []
    confidence_lookup = confidence_lookup or {}

    prescriptions = _extract_prescriptions(extraction_data)
    if not prescriptions:
        return []

    # Build lookup: external_id → {id, unit_price}
    price_lookup = _get_medicine_price_lookup(hospital_id)

    for idx, med in enumerate(prescriptions):
        med_name = med.get("medicine_name") or med.get("name") or med.get("Medicine") or med.get("drug_name") or ""
        if not med_name:
            continue

        external_id = med.get("_external_id")
        match_conf = confidence_lookup.get(med_name.lower().strip(), 0)
        dosage = med.get("dosage") or med.get("Dosage") or ""
        quantity = _parse_quantity(med)

        # Price lookup by external_id only
        unit_price = None
        matched_master_id = None
        matched_table = None

        if external_id and str(external_id) in price_lookup:
            lookup = price_lookup[str(external_id)]
            unit_price = lookup.get("unit_price")
            matched_master_id = lookup.get("id")
            matched_table = "hospital_medicine_lists"

        # Build description
        description = med_name
        if dosage:
            description = f"{med_name} - {dosage}"

        total_price = round(unit_price * quantity, 2) if unit_price else None
        confidence, action = _determine_confidence("pharmacy", unit_price, match_conf)

        item = {
            "category": "pharmacy",
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "confidence": confidence,
            "billing_action": action,
            "source_segment": "prescription",
            "source_item_index": idx,
            "matched_master_id": matched_master_id,
            "matched_master_table": matched_table,
            "match_confidence": match_conf if match_conf else None,
        }

        if matched_master_id and not unit_price:
            item["notes"] = "No price configured in hospital medicine list"
        elif not external_id:
            item["notes"] = "Medicine not matched to hospital list"

        line_items.append(item)

    return line_items


def _add_investigation_line_items(extraction_data: Dict[str, Any], hospital_id: str, confidence_lookup: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Map investigation items to line items using hospital investigation list prices.

    Match confidence is read from audit logs (confidence_lookup), not extraction JSON.
    """
    line_items = []
    confidence_lookup = confidence_lookup or {}

    investigations = _extract_investigations(extraction_data)

    if not investigations:
        return []

    # Build price lookup
    price_lookup = _get_investigation_price_lookup(hospital_id)

    for idx, inv in enumerate(investigations):
        inv_name = inv.get("name") or inv.get("investigation_name") or inv.get("Test") or inv.get("test_name") or ""
        if not inv_name:
            continue

        external_id = inv.get("_external_id") or inv.get("Test_id")
        match_conf = confidence_lookup.get(inv_name.lower().strip(), 0)

        # Price lookup
        unit_price = None
        matched_master_id = None
        matched_table = None

        if external_id and str(external_id) in price_lookup:
            lookup = price_lookup[str(external_id)]
            unit_price = lookup.get("unit_price")
            matched_master_id = lookup.get("id")
            matched_table = "hospital_investigation_lists"

        total_price = float(unit_price) if unit_price else None
        confidence, action = _determine_confidence("lab", unit_price, match_conf)

        # Determine category (lab vs radiology)
        inv_type = inv.get("_investigation_type") or inv.get("type") or ""
        category = "radiology" if inv_type.lower() in ("imaging", "radiology") else "lab"

        item = {
            "category": category,
            "description": inv_name,
            "quantity": 1,
            "unit_price": float(unit_price) if unit_price else None,
            "total_price": total_price,
            "confidence": confidence,
            "billing_action": action,
            "source_segment": "investigations",
            "source_item_index": idx,
            "matched_master_id": matched_master_id,
            "matched_master_table": matched_table,
            "match_confidence": match_conf if match_conf else None,
        }

        if not unit_price:
            item["notes"] = "No price configured in hospital investigation list"
        if not external_id:
            item["notes"] = "Investigation not matched to hospital list"

        line_items.append(item)

    return line_items


def _add_procedure_line_items(extraction_data: Dict[str, Any], hospital_id: str) -> List[Dict[str, Any]]:
    """Map procedure mentions to line items via procedure_fee_master."""
    line_items = []

    procedures = _extract_procedures(extraction_data)

    if not procedures:
        return []

    # Build procedure fee lookup
    try:
        result = supabase.table("procedure_fee_master").select(
            "id, procedure_name, cpt_code, fee"
        ).eq("hospital_id", hospital_id).eq("is_active", True).execute()

        fee_lookup = {}
        name_lookup = {}
        if result.data:
            for proc in result.data:
                if proc.get("cpt_code"):
                    fee_lookup[proc["cpt_code"]] = proc
                name_lookup[proc["procedure_name"].lower()] = proc
    except Exception as e:
        logger.warning(f"[Billing] Failed to fetch procedure fees: {e}")
        fee_lookup = {}
        name_lookup = {}

    for idx, proc in enumerate(procedures):
        proc_name = proc.get("procedure_name") or proc.get("Procedure") or ""
        if not proc_name:
            continue

        cpt_code = proc.get("cpt_code") or proc.get("CPT_Code") or ""

        # Lookup by CPT code first, then by name
        matched = None
        if cpt_code and cpt_code in fee_lookup:
            matched = fee_lookup[cpt_code]
        elif proc_name.lower() in name_lookup:
            matched = name_lookup[proc_name.lower()]

        unit_price = float(matched["fee"]) if matched else None
        matched_master_id = matched["id"] if matched else None
        match_conf = 0.9 if matched else 0

        total_price = unit_price  # quantity = 1 for procedures
        confidence, action = _determine_confidence("procedure", unit_price, match_conf)

        item = {
            "category": "procedure",
            "description": proc_name,
            "item_code": cpt_code or None,
            "quantity": 1,
            "unit_price": unit_price,
            "total_price": total_price,
            "confidence": confidence,
            "billing_action": action,
            "source_segment": "procedures",
            "source_item_index": idx,
            "matched_master_id": matched_master_id,
            "matched_master_table": "procedure_fee_master" if matched else None,
            "match_confidence": match_conf if match_conf else None,
        }

        if not matched:
            item["notes"] = "Procedure not found in fee master"

        line_items.append(item)

    return line_items


def _add_room_line_items(patient_id: str, hospital_id: str) -> List[Dict[str, Any]]:
    """Add room charges for IP bills based on patient add_info."""
    try:
        # Get patient's room info from add_info
        patient_result = supabase.table("patients").select(
            "add_info"
        ).eq("id", patient_id).limit(1).execute()

        if not patient_result.data:
            return [{
                "category": "room",
                "description": "Room Charges",
                "quantity": 1,
                "unit_price": None,
                "total_price": None,
                "confidence": "low",
                "billing_action": "flagged_manual",
                "source_segment": "room",
                "notes": "Patient record not found",
            }]

        add_info = patient_result.data[0].get("add_info") or {}
        room_category = add_info.get("room_category")
        room_sub_category = add_info.get("room_sub_category")

        if not room_category:
            return [{
                "category": "room",
                "description": "Room Charges",
                "quantity": 1,
                "unit_price": None,
                "total_price": None,
                "confidence": "low",
                "billing_action": "flagged_manual",
                "source_segment": "room",
                "notes": "Room category not in patient record",
            }]

        # Lookup room rate
        query = (
            supabase.table("room_rate_master")
            .select("id, rate_per_day, room_category, room_sub_category")
            .eq("hospital_id", hospital_id)
            .eq("room_category", room_category)
            .eq("is_active", True)
        )

        if room_sub_category:
            query = query.eq("room_sub_category", room_sub_category)

        rate_result = query.limit(1).execute()

        if not rate_result.data:
            return [{
                "category": "room",
                "description": f"Room Charges - {room_category}" + (f" ({room_sub_category})" if room_sub_category else ""),
                "quantity": 1,
                "unit_price": None,
                "total_price": None,
                "confidence": "low",
                "billing_action": "flagged_manual",
                "source_segment": "room",
                "notes": f"No rate configured for room category '{room_category}'",
            }]

        rate = rate_result.data[0]
        rate_per_day = float(rate["rate_per_day"])

        # LOS: default to 1 day, flag for manual review
        los_days = 1
        room_number = add_info.get("room_number", "")
        bed_number = add_info.get("bed_number", "")

        description = f"Room Charges - {room_category}"
        if room_sub_category:
            description += f" ({room_sub_category})"
        if room_number:
            description += f" - Room {room_number}"
        if bed_number:
            description += f", Bed {bed_number}"

        return [{
            "category": "room",
            "description": description,
            "quantity": los_days,
            "unit_price": rate_per_day,
            "total_price": round(rate_per_day * los_days, 2),
            "confidence": "low",
            "billing_action": "flagged_manual",
            "source_segment": "room",
            "matched_master_id": rate["id"],
            "matched_master_table": "room_rate_master",
            "notes": "LOS defaulted to 1 day — update quantity with actual length of stay",
        }]

    except Exception as e:
        logger.warning(f"[Billing] Failed to fetch room info: {e}")
        return [{
            "category": "room",
            "description": "Room Charges",
            "quantity": 1,
            "unit_price": None,
            "total_price": None,
            "confidence": "low",
            "billing_action": "flagged_manual",
            "source_segment": "room",
            "notes": f"Error fetching room info: {str(e)}",
        }]


def _determine_confidence(
    category: str,
    unit_price: Optional[float],
    match_confidence: Optional[float],
) -> Tuple[str, str]:
    """
    Determine confidence level and billing action.

    Returns:
        Tuple of (confidence, billing_action)
    """
    # Registration/admission/consultation fees are always known
    if category in ("registration", "admission", "consultation"):
        if unit_price is not None:
            return ("high", "auto_billed")
        return ("low", "flagged_manual")

    # No price → flag
    if unit_price is None:
        return ("low", "flagged_manual")

    # High-value items → flag
    if unit_price > HIGH_VALUE_THRESHOLD:
        return ("low", "flagged_manual")

    # Check match confidence
    mc = float(match_confidence or 0)

    if mc >= 0.85:
        return ("medium", "pending_review")
    elif mc > 0:
        return ("low", "flagged_manual")
    else:
        # No match info but has price (e.g., procedure lookup)
        return ("medium", "pending_review")


# ============================================================================
# Extraction Data Helpers
# ============================================================================

def _extract_prescriptions(extraction_data: Dict[str, Any]) -> List[Dict]:
    """Extract prescription items from extraction JSON.

    OP_CORE format: extraction_data["prescription"] = [{name, morning_qty, ...}, ...]
    """
    for key in ["prescription", "Prescription", "prescriptions", "Prescriptions"]:
        val = extraction_data.get(key)
        if isinstance(val, list):
            return val

    return []


def _extract_investigations(extraction_data: Dict[str, Any]) -> List[Dict]:
    """Extract investigation items from extraction JSON.

    OP_CORE format: extraction_data["investigations"] = {
        "laboratory_tests": [{test_name, ...}, ...],
        "imaging_studies": [...],
        "other_tests": [...]
    }
    Also handles flat list format from other templates.
    """
    for key in ["investigations", "Investigations", "investigation", "Investigation"]:
        val = extraction_data.get(key)
        if val is None:
            continue

        # OP_CORE: nested object with sub-arrays
        if isinstance(val, dict):
            items = []
            for sub_key in ["laboratory_tests", "imaging_studies", "other_tests",
                            "Laboratory_Tests", "Imaging_Studies", "Other_Tests"]:
                sub_val = val.get(sub_key)
                if isinstance(sub_val, list):
                    items.extend(sub_val)
            return items

        # Flat list format
        if isinstance(val, list):
            return val

    return []


def _extract_procedures(extraction_data: Dict[str, Any]) -> List[Dict]:
    """Extract procedure items from extraction JSON."""
    for key in ["procedures", "Procedures", "procedure", "Procedure",
                 "surgical_procedures", "Surgical_Procedures"]:
        if key in extraction_data and isinstance(extraction_data[key], list):
            return extraction_data[key]

    for key, value in extraction_data.items():
        if isinstance(value, dict):
            for sub_key in ["procedures", "Procedures", "surgical_procedures"]:
                if sub_key in value and isinstance(value[sub_key], list):
                    return value[sub_key]

    return []


def _parse_duration_days(val) -> float:
    """Convert duration to days. Handles '30', '2 weeks', '1 month', etc."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    import re
    d = str(val).strip().lower()
    if not d or d in ("n/a", "na", "null", "none", "ongoing", "sos"):
        return 0.0
    match = re.match(r'(\d+)\s*(day|days|week|weeks|month|months|year|years)?', d)
    if match:
        num = float(match.group(1))
        unit = (match.group(2) or "day").lower()
        if unit.startswith("week"):
            return num * 7
        elif unit.startswith("month"):
            return num * 30
        elif unit.startswith("year"):
            return num * 365
        return num
    try:
        return float(d)
    except ValueError:
        return 0.0


def _parse_quantity(med: Dict[str, Any]) -> float:
    """Parse quantity from prescription item.

    OP_CORE format: morning_qty, noon_qty, evening_qty, night_qty, durationDays
    Total = (morning + noon + evening + night) × durationDays
    Falls back to explicit quantity fields, then defaults to 1.
    """
    # OP_CORE: per-dose quantities × duration
    morning = _safe_float(med.get("morning_qty"))
    noon = _safe_float(med.get("noon_qty"))
    evening = _safe_float(med.get("evening_qty"))
    night = _safe_float(med.get("night_qty"))
    duration = _parse_duration_days(med.get("durationDays"))

    per_day = morning + noon + evening + night
    if per_day > 0 and duration > 0:
        return per_day * duration

    # Explicit quantity field
    for key in ["quantity", "Quantity", "qty", "Qty", "total_quantity"]:
        val = med.get(key)
        if val is not None:
            try:
                return max(float(val), 1)
            except (ValueError, TypeError):
                pass

    return 1.0


def _safe_float(val) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _get_medicine_price_lookup(hospital_id: str) -> Dict[str, Dict]:
    """Build external_id → {id, unit_price} lookup from hospital medicine list."""
    try:
        result = supabase.table("hospital_medicine_lists").select(
            "id, external_id, unit_price"
        ).eq("hospital_id", hospital_id).eq("is_active", True).not_.is_("unit_price", "null").execute()

        lookup = {}
        if result.data:
            for med in result.data:
                ext_id = med.get("external_id")
                if ext_id:
                    lookup[str(ext_id)] = {
                        "id": med["id"],
                        "unit_price": float(med["unit_price"]),
                    }
        return lookup
    except Exception as e:
        logger.warning(f"[Billing] Failed to build medicine price lookup: {e}")
        return {}


def _get_investigation_price_lookup(hospital_id: str) -> Dict[str, Dict]:
    """Build external_id → {id, unit_price} lookup from hospital investigation list."""
    try:
        result = supabase.table("hospital_investigation_lists").select(
            "id, external_id, unit_price"
        ).eq("hospital_id", hospital_id).eq("is_active", True).not_.is_("unit_price", "null").execute()

        lookup = {}
        if result.data:
            for inv in result.data:
                ext_id = inv.get("external_id")
                if ext_id:
                    lookup[str(ext_id)] = {
                        "id": inv["id"],
                        "unit_price": float(inv["unit_price"]),
                    }
        return lookup
    except Exception as e:
        logger.warning(f"[Billing] Failed to build investigation price lookup: {e}")
        return {}
