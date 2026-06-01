"""
Accuracy Metrics Service

Computes WER (Word Error Rate) and entity error metrics by comparing
AI-generated extraction vs counsellor's edited version.

Key design decisions:
- Modified WER: Only counts AI errors, NOT counsellor additions of new information
- Uses transcript as source-of-truth to distinguish AI errors from counsellor enhancements
- Fire-and-forget: Called via asyncio.create_task() to avoid pipeline latency
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Segments where deletions count as AI errors when the deleted word is absent
# from transcript. Narrative / template-driven segments (examination, history,
# HPI, protocol, etc.) frequently contain stock clinical phrasing the counsellor
# never verbalizes ("CVS Normal", "non-tender") — those get trimmed from the
# final note but it's a template limitation, not an AI hallucination. So we
# only gate deletions on the clinically-structured list segments.
DELETION_GATED_SEGMENTS = {
    "prescription", "diagnosis", "investigations", "chiefComplaints",
    "prescriptionOp", "diagnosisOp", "diagnosisDischarge",
    "investigationsOp", "prescriptionDischarge",
}

# Segments where the counsellor's data source is NOT the audio — typically assistant-
# measured vitals or chart-reviewed lab orders entered manually. For these,
# every insertion is treated as a counsellor_addition even if the added token
# coincidentally matches a transcript word. Otherwise short tokens like "3"
# or "100" register as AI errors when the counsellor enters a vitals number that
# happens to appear elsewhere in the conversation. Symmetric in spirit to
# DELETION_GATED_SEGMENTS.
INSERTION_GATED_SEGMENTS = {
    "vitals", "investigations", "investigationsOp",
}


def _coerce_json(value: Any) -> Any:
    """Defensive re-parse for values stored as JSON-encoded strings.

    The EHR iframe's edit flow sometimes saves list/object segments as
    JSON-encoded strings (e.g. diagnosis stored as '[{"code":…}]' instead
    of a real array). Detect that shape and parse it back so downstream
    comparisons see structured data.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not (s.startswith("[") or s.startswith("{")):
        return value
    import json
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return value


def _tokenize(text: str) -> List[str]:
    """Normalize and tokenize text for comparison."""
    if not text or not isinstance(text, str):
        return []
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.split()


# ── Fuzzy transcript matching (stem + number normalization) ───────────
# Medical narratives routinely paraphrase ("inhale" ↔ "inhalation",
# "resolved" ↔ "resolve", "two months" ↔ "2 months"). A pure literal
# token match flags these as AI hallucinations even when the content
# matches. These helpers extend transcript matching with:
#   (A) a tiny Porter-like stemmer that folds common English suffixes
#   (B) number-word ↔ digit normalization (one ↔ 1, ninety ↔ 90, etc.)

_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16",
    "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000",
}
_DIGIT_TO_WORDS = {v: k for k, v in _NUMBER_WORDS.items()}

# Longest-first suffixes stripped by the tiny stemmer; applied iteratively
# so "constipation" → "constipat" (strip "ion") → "constip" (strip "at").
_STEM_SUFFIXES = (
    "ational", "ization", "ations",
    "ation", "fully", "ingly", "ously", "iness", "ments",
    "ness", "ings", "ied", "ies", "ing", "ive", "ize",
    "ise", "ity", "ion", "ful", "ous", "ate", "ment",
    "al", "at", "ed", "es", "ly", "er", "e", "s",
)


def _simple_stem(token: str) -> str:
    """Tiny Porter-like stemmer — strips common English suffixes iteratively.

    Keeps a 3-char root floor so words like "walk", "sit", "ask" aren't
    over-stemmed. Handles the medical-narrative paraphrases that drive
    most WER noise: inhale/inhalation, resolve/resolved,
    walk/walking, constipate/constipation, breath/breathing.
    """
    if len(token) < 4:
        return token
    prev: Optional[str] = None
    while token != prev:
        prev = token
        for suffix in _STEM_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                token = token[: -len(suffix)]
                break
    return token


def _token_variants(token: str) -> set:
    """All equivalent forms of a token for fuzzy transcript matching."""
    out = {token}
    stem = _simple_stem(token)
    if stem != token and len(stem) >= 3:
        out.add(stem)
    if token in _NUMBER_WORDS:
        out.add(_NUMBER_WORDS[token])
    if token in _DIGIT_TO_WORDS:
        out.add(_DIGIT_TO_WORDS[token])
    return out


def _build_transcript_lookup(transcript_text: str) -> set:
    """Expanded token set for fuzzy membership checks — includes the raw
    tokens, their stems, and number-word ↔ digit pairs."""
    out: set = set()
    for tok in _tokenize(transcript_text):
        out |= _token_variants(tok)
    return out


def _in_transcript(token: str, transcript_lookup: set) -> bool:
    """True if any variant of `token` appears in the pre-built lookup."""
    return any(v in transcript_lookup for v in _token_variants(token))


# Clinical terms the AI routinely uses when the student/counsellor uttered a
# lay equivalent. Value = set of lay-synonym tokens that, if present in the
# transcript lookup, re-classify the flagged word from "real AI error" to
# "paraphrase". Empty set = always treat as paraphrase (interpretive /
# meta-wording AI adds by default: "attributed", "capacity", units, etc.).
CLINICAL_PARAPHRASES: Dict[str, set] = {
    # Clinical nouns ↔ student-spoken lay words
    "hypoglycemia": {"sugar", "low"},
    "hyperglycemia": {"sugar", "high"},
    "constipation": {"motion", "bowel", "stool"},
    "dysentery": {"loose", "motion"},
    "diarrhea": {"loose", "motion"},
    "diarrhoea": {"loose", "motion"},
    "oral": {"tablet", "syrup", "pill", "capsule"},
    "ambulation": {"walk"},
    "pruritus": {"itch"},
    "dyspnoea": {"breath", "breathless"},
    "dyspnea": {"breath", "breathless"},
    "emesis": {"vomit"},
    "pyrexia": {"fever"},
    "edema": {"swell", "swollen"},
    "oedema": {"swell", "swollen"},
    "hematuria": {"blood", "urine"},
    # Interpretive / meta vocabulary AI adds when summarizing speech.
    # Empty set = always paraphrase (no lay synonym required).
    "attributed": set(),
    "approximately": set(),
    "limited": set(),
    "unable": set(),
    "capacity": set(),
    "exercises": set(),
    "position": set(),
    "context": set(),
    # Common units AI adds that aren't spoken
    "mg": set(), "dl": set(), "kg": set(), "cm": set(), "mm": set(),
    # Intensity adjectives with many forms — stemmer doesn't always unify
    "mild": {"slight"},
    "slight": {"mild"},
}


def _is_clinical_paraphrase(word: str, transcript_lookup: set) -> bool:
    """True when `word` is a clinical/interpretive term whose meaning is
    represented in the transcript by a lay synonym (or the word is a
    stock AI-summary term we always treat as paraphrase)."""
    synonyms = CLINICAL_PARAPHRASES.get(word)
    if synonyms is None:
        return False
    if not synonyms:
        return True
    return any(syn in transcript_lookup for syn in synonyms)


def _flatten_segment_to_text(segment_data: Any) -> str:
    """Flatten a segment value (string, dict, list) to plain text.

    Canonical-order flattening: dict values are emitted in sorted-key order
    so that two dicts with the same content but different JSON key order
    (a common EHR save-flow reformat) flatten to the same token sequence.
    This prevents Levenshtein from counting reordering-only artifacts as
    word-level substitutions/insertions.
    """
    def _dict_values_sorted(d: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for k in sorted(d.keys()):
            val = d[k]
            if val in (None, "", [], {}):
                continue
            if isinstance(val, str):
                out.append(val)
            elif isinstance(val, (int, float, bool)):
                out.append(str(val))
            elif isinstance(val, dict):
                out.extend(_dict_values_sorted(val))
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, (int, float, bool)):
                        out.append(str(item))
                    elif isinstance(item, dict):
                        out.extend(_dict_values_sorted(item))
        return out

    if isinstance(segment_data, str):
        return segment_data
    if isinstance(segment_data, dict):
        return ' '.join(_dict_values_sorted(segment_data))
    if isinstance(segment_data, list):
        parts: List[str] = []
        for item in segment_data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, (int, float, bool)):
                parts.append(str(item))
            elif isinstance(item, dict):
                parts.extend(_dict_values_sorted(item))
        return ' '.join(parts)
    return str(segment_data) if segment_data else ''


def _levenshtein_aligned(
    source: List[str], target: List[str]
) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """Word-level edit alignment via DP + backtrace.

    Returns a forward-ordered list of (op, src_word, tgt_word) tuples where
    op ∈ {"match", "sub", "del", "ins"}. For "del", tgt_word is None;
    for "ins", src_word is None.
    """
    m, n = len(source), len(target)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if source[i - 1] == target[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    ops: List[Tuple[str, Optional[str], Optional[str]]] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and source[i - 1] == target[j - 1]:
            ops.append(("match", source[i - 1], target[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(("sub", source[i - 1], target[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", source[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, target[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def compute_modified_wer(
    ai_text: str,
    counsellor_text: str,
    transcript_text: str,
    segment_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Transcript-gated WER. An op counts as an AI error only when AI's output
    contradicts the transcript:
      - Substitution (X→Y): error iff AI's word X is NOT in transcript.
      - Deletion    (X→_): error iff AI's word X is NOT in transcript,
                           AND segment is in DELETION_GATED_SEGMENTS.
                           Narrative segments (examination, history, HPI,
                           protocol, treatmentPlan, …) are template-driven,
                           so we treat all their deletions as physician trims.
      - Insertion   (_→Y): error iff counsellor's word Y IS in transcript.

    WER = (subs_ai_error + dels_ai_error + ins_ai_error) / ai_word_count.
    """
    # Gate deletions only for clinically-structured list segments
    gate_deletions = segment_code in DELETION_GATED_SEGMENTS
    # Gate insertions for assistant-collected segments (vitals/investigations) where
    # the counsellor's source isn't audio.
    gate_insertions = segment_code in INSERTION_GATED_SEGMENTS
    ai_tokens = _tokenize(ai_text)
    counsellor_tokens = _tokenize(counsellor_text)
    # Fuzzy transcript lookup: raw tokens + stems + number-word pairs,
    # so "inhale" ↔ "inhalation" and "two" ↔ "2" don't falsely flag.
    transcript_lookup = _build_transcript_lookup(transcript_text)

    if not ai_tokens and not counsellor_tokens:
        return {
            "wer": 0.0, "wer_adjusted": 0.0, "wer_adjusted_descriptions": 0.0,
            "substitutions": 0, "deletions": 0, "insertions": 0,
            "substitutions_ai_error": 0, "deletions_ai_error": 0, "insertions_ai_error": 0,
            "paraphrase_count": 0,
            "doctor_rephrasing": 0, "doctor_trims": 0, "doctor_additions": 0,
            "ai_word_count": 0, "doctor_word_count": 0,
        }

    ops = _levenshtein_aligned(ai_tokens, counsellor_tokens)

    subs = dels = ins = 0
    subs_ai_error = dels_ai_error = ins_ai_error = 0
    paraphrase_count = 0
    doctor_rephrasing = doctor_trims = doctor_additions = 0

    for op, s, t in ops:
        if op == "sub":
            subs += 1
            if not _in_transcript(s, transcript_lookup):
                subs_ai_error += 1
                if _is_clinical_paraphrase(s, transcript_lookup):
                    paraphrase_count += 1  # real-error − paraphrase at aggregate time
            else:
                doctor_rephrasing += 1
        elif op == "del":
            dels += 1
            if gate_deletions and not _in_transcript(s, transcript_lookup):
                dels_ai_error += 1
                if _is_clinical_paraphrase(s, transcript_lookup):
                    paraphrase_count += 1
            else:
                doctor_trims += 1
        elif op == "ins":
            ins += 1
            if not gate_insertions and _in_transcript(t, transcript_lookup):
                ins_ai_error += 1
                # Insertions are words the counsellor *added* — paraphrase check
                # runs on the added word's lay form vs AI terminology.
                if _is_clinical_paraphrase(t, transcript_lookup):
                    paraphrase_count += 1
            else:
                doctor_additions += 1

    ai_word_count = len(ai_tokens)
    error_count = subs_ai_error + dels_ai_error + ins_ai_error
    modified_wer = error_count / max(ai_word_count, 1)
    # Adjusted-for-paraphrasing: subtract clinical-paraphrase matches.
    adjusted_errors = max(error_count - paraphrase_count, 0)
    adjusted_wer = adjusted_errors / max(ai_word_count, 1)
    # Adjusted-for-description-editing: also subtract deletion errors.
    # Deletions on chiefComplaints/description fields are typically the
    # counsellor trimming verbose AI prose, not true STT errors.
    adjusted_desc_errors = max(error_count - paraphrase_count - dels_ai_error, 0)
    adjusted_wer_descriptions = adjusted_desc_errors / max(ai_word_count, 1)

    return {
        "wer": round(min(modified_wer, 1.0), 4),
        "wer_adjusted": round(min(adjusted_wer, 1.0), 4),
        "wer_adjusted_descriptions": round(min(adjusted_wer_descriptions, 1.0), 4),
        "substitutions": subs, "deletions": dels, "insertions": ins,
        "substitutions_ai_error": subs_ai_error,
        "deletions_ai_error": dels_ai_error,
        "insertions_ai_error": ins_ai_error,
        "paraphrase_count": paraphrase_count,
        "doctor_rephrasing": doctor_rephrasing,
        "doctor_trims": doctor_trims,
        "doctor_additions": doctor_additions,
        "ai_word_count": ai_word_count,
        "doctor_word_count": len(counsellor_tokens),
    }


def _key_in_transcript(name: Optional[str], transcript_lookup: set) -> bool:
    """Entity key is 'in transcript' if any content-bearing token (length ≥ 3)
    from the name/code has a variant (raw / stem / number form) present in
    the pre-built transcript lookup. Permissive on purpose — medical names
    are distinctive enough that a single fuzzy-matching token is a strong
    signal; the length floor skips stopwords.
    """
    if not name:
        return False
    for tok in _tokenize(str(name)):
        if len(tok) >= 3 and _in_transcript(tok, transcript_lookup):
            return True
    return False


def _match_items(
    ai_items: List[Any],
    doc_items: List[Any],
    key_fn,
) -> Tuple[List[Tuple[Any, Any]], List[Any], List[Any]]:
    """Set-based match by canonical key (order-insensitive).

    Returns (matched_pairs, ai_only, doc_only). Items without a resolvable key
    are appended to their respective "only" list so they aren't silently
    dropped. Duplicates with the same key are paired in iteration order;
    extras on either side fall through to the matching "only" list.
    """
    ai_by_key: Dict[str, List[Any]] = {}
    for item in ai_items:
        k = key_fn(item)
        if k:
            ai_by_key.setdefault(k, []).append(item)
    doc_by_key: Dict[str, List[Any]] = {}
    for item in doc_items:
        k = key_fn(item)
        if k:
            doc_by_key.setdefault(k, []).append(item)

    matched_pairs: List[Tuple[Any, Any]] = []
    ai_only: List[Any] = [i for i in ai_items if not key_fn(i)]
    doc_only: List[Any] = [i for i in doc_items if not key_fn(i)]

    for k, ai_list in ai_by_key.items():
        doc_list = doc_by_key.get(k, [])
        n = min(len(ai_list), len(doc_list))
        for idx in range(n):
            matched_pairs.append((ai_list[idx], doc_list[idx]))
        if len(ai_list) > n:
            ai_only.extend(ai_list[n:])
        if len(doc_list) > n:
            doc_only.extend(doc_list[n:])
    for k, doc_list in doc_by_key.items():
        if k not in ai_by_key:
            doc_only.extend(doc_list)
    return matched_pairs, ai_only, doc_only


def _drug_name(item: Any) -> Optional[str]:
    if isinstance(item, dict):
        name = str(item.get("drug", item.get("medicine", item.get("name", "")))).strip().lower()
        return name or None
    return None


def _inv_name(item: Any) -> Optional[str]:
    if isinstance(item, dict):
        name = str(item.get("name", item.get("test", ""))).strip().lower()
        return name or None
    s = str(item).strip().lower()
    return s or None


def _dx_key(item: Any) -> Optional[str]:
    """Canonical key for diagnosis: prefer ICD code, fall back to name."""
    if isinstance(item, dict):
        code = str(item.get("code", "")).strip().upper()
        if code:
            return f"CODE:{code}"
        name = str(item.get("name", "")).strip().lower()
        return f"NAME:{name}" if name else None
    s = str(item).strip().lower()
    return f"NAME:{s}" if s else None


def _dx_display_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name", "")) or str(item.get("code", ""))
    return str(item)


def _compute_entity_errors(
    ai_json: Dict[str, Any],
    counsellor_json: Dict[str, Any],
    transcript_text: str
) -> Dict[str, Any]:
    """
    Transcript-gated, set-based entity error metrics.

    For each structured list (prescription / investigations / diagnosis):
      - Matched pair by canonical key → correct (reorders don't inflate errors).
      - AI-only item (counsellor removed) → error iff AI's key NOT in transcript.
      - Counsellor-only item (counsellor added) → error iff counsellor's key IS in transcript.
    """
    transcript_lookup = _build_transcript_lookup(transcript_text)
    transcript_tokens = transcript_lookup  # alias so downstream arg name still reads sensibly

    entity_categories = {
        "drug": 0, "dose": 0, "diagnosis": 0,
        "lab_value": 0, "duration": 0,
    }
    total_entities = 0
    incorrect_entities = 0   # matched but other field differs (e.g. dose) AND AI's value not in transcript
    missing_entities = 0     # AI had, counsellor removed, and AI's value not in transcript
    missed_entities = 0      # counsellor added, value is in transcript → AI missed
    correct_entities = 0

    # ---- Prescription ----
    for key in ("prescription", "medications", "drugs", "rx"):
        if key in ai_json and key not in counsellor_json:
            continue  # artifact
        ai_items = _coerce_json(ai_json.get(key, []))
        doc_items = _coerce_json(counsellor_json.get(key, []))
        if not isinstance(ai_items, list) or not isinstance(doc_items, list):
            continue
        matched, ai_only, doc_only = _match_items(ai_items, doc_items, _drug_name)
        for ai_i, doc_i in matched:
            total_entities += 1
            correct_entities += 1
            ai_dose = str(ai_i.get("dose", ai_i.get("dosage", ""))).strip().lower() if isinstance(ai_i, dict) else ""
            doc_dose = str(doc_i.get("dose", doc_i.get("dosage", ""))).strip().lower() if isinstance(doc_i, dict) else ""
            if ai_dose and doc_dose and ai_dose != doc_dose and not _key_in_transcript(ai_dose, transcript_tokens):
                entity_categories["dose"] += 1
        for ai_i in ai_only:
            total_entities += 1
            if not _key_in_transcript(_drug_name(ai_i), transcript_tokens):
                missing_entities += 1
                entity_categories["drug"] += 1
        for doc_i in doc_only:
            if _key_in_transcript(_drug_name(doc_i), transcript_tokens):
                total_entities += 1
                missed_entities += 1
                entity_categories["drug"] += 1

    # ---- Investigations ----
    for key in ("investigations", "lab_tests", "diagnostics"):
        if key in ai_json and key not in counsellor_json:
            continue
        ai_items = _coerce_json(ai_json.get(key, []))
        doc_items = _coerce_json(counsellor_json.get(key, []))
        if not isinstance(ai_items, list) or not isinstance(doc_items, list):
            continue
        matched, ai_only, doc_only = _match_items(ai_items, doc_items, _inv_name)
        for _ai, _doc in matched:
            total_entities += 1
            correct_entities += 1
        for ai_i in ai_only:
            total_entities += 1
            if not _key_in_transcript(_inv_name(ai_i), transcript_tokens):
                missing_entities += 1
                entity_categories["lab_value"] += 1
        for doc_i in doc_only:
            if _key_in_transcript(_inv_name(doc_i), transcript_tokens):
                total_entities += 1
                missed_entities += 1
                entity_categories["lab_value"] += 1

    # ---- Diagnosis ----
    for key in ("diagnosis", "diagnoses", "provisional_diagnosis", "final_diagnosis"):
        if key in ai_json and key not in counsellor_json:
            continue
        ai_val = _coerce_json(ai_json.get(key))
        doc_val = _coerce_json(counsellor_json.get(key))
        if ai_val is None and doc_val is None:
            continue
        if isinstance(ai_val, list) and isinstance(doc_val, list):
            matched, ai_only, doc_only = _match_items(ai_val, doc_val, _dx_key)
            for _ai, _doc in matched:
                total_entities += 1
                correct_entities += 1
            for ai_i in ai_only:
                total_entities += 1
                name = _dx_display_name(ai_i)
                if not _key_in_transcript(name, transcript_tokens):
                    missing_entities += 1
                    entity_categories["diagnosis"] += 1
            for doc_i in doc_only:
                name = _dx_display_name(doc_i)
                if _key_in_transcript(name, transcript_tokens):
                    total_entities += 1
                    missed_entities += 1
                    entity_categories["diagnosis"] += 1
        elif ai_val and doc_val:
            total_entities += 1
            a_str = str(ai_val).strip().lower()
            d_str = str(doc_val).strip().lower()
            if a_str == d_str:
                correct_entities += 1
            elif not _key_in_transcript(a_str, transcript_tokens):
                incorrect_entities += 1
                entity_categories["diagnosis"] += 1

    total_errors = incorrect_entities + missing_entities + missed_entities
    entity_error_rate = (total_errors / max(total_entities, 1)) * 100

    return {
        "total": total_entities,
        "correct": correct_entities,
        "incorrect": incorrect_entities,
        "missing": missing_entities,
        "missed": missed_entities,
        "entity_error_rate": round(entity_error_rate, 4),
        "by_type": entity_categories,
    }


async def compute_and_save_accuracy_metrics(
    extraction_id: uuid.UUID,
    original_json: Dict[str, Any],
    edited_json: Dict[str, Any],
    counsellor_id: Optional[str],
    transcript_text: Optional[str] = None,
):
    """
    Compute accuracy metrics and save to extraction_accuracy_metrics table.

    This is designed to be called as a fire-and-forget background task:
        asyncio.create_task(compute_and_save_accuracy_metrics(...))
    """
    try:
        # Type guard: both must be dicts
        if not isinstance(original_json, dict) or not isinstance(edited_json, dict):
            logger.warning(f"[ACCURACY] Skipping metrics for {extraction_id}: "
                           f"original={type(original_json).__name__}, edited={type(edited_json).__name__}")
            return

        from services.supabase_service import supabase

        # If transcript not provided, fetch it
        if transcript_text is None:
            try:
                result = supabase.table("extractions")\
                    .select("transcript_text")\
                    .eq("id", str(extraction_id))\
                    .execute()
                if result.data:
                    transcript_text = result.data[0].get("transcript_text") or ""
                else:
                    transcript_text = ""
            except Exception:
                transcript_text = ""

        # Per-segment WER computation
        segment_metrics = []
        total_ai_words = 0
        total_doc_words = 0
        total_counsellor_additions = 0
        segments_unchanged = 0
        segments_modified = 0
        all_keys = set(list(original_json.keys()) + list(edited_json.keys()))
        # Skip pass-through metadata segments — these are copied from
        # recording_metadata / EHR context (uhid, opid, ipid, student name,
        # admission date, etc.) rather than extracted from the transcript,
        # so they shouldn't contribute to WER.
        skip_keys = {
            # generic session / template metadata
            "metadata", "template_code", "consultation_type", "counsellor_name",
            "patient_info", "session_info",
            # extraction-JSON segments populated from EHR metadata / KP API inputs
            "reportMetadata", "patientInformation", "emergencyContact",
            "referralDetails",
        }

        from services.edit_classifier import is_empty_like

        def _count_ai_words(val: Any) -> int:
            """Tokens in an AI segment value — used to grow the WER denominator
            even for segments the counsellor didn't touch."""
            if is_empty_like(val):
                return 0
            return len(_tokenize(_flatten_segment_to_text(val)))

        for key in sorted(all_keys):
            if key in skip_keys:
                continue
            # Skip segments that only exist in edited (new segments added by counsellor)
            if key not in original_json:
                continue
            # Artifact guard: the EHR edit flow drops untouched segments, so a
            # key in original but missing from edited means the counsellor didn't
            # touch it — not a real edit.
            if key not in edited_json:
                segments_unchanged += 1
                # Unchanged segments contribute 0 errors but their full AI
                # word count to the denominator — otherwise unedited records
                # contribute nothing and the aggregate WER is biased upward.
                total_ai_words += _count_ai_words(_coerce_json(original_json.get(key)))
                continue

            # Coerce JSON-encoded strings back to lists/dicts — the EHR
            # save flow stringifies list segments, and comparing a proper
            # list against that stringified form inflates Levenshtein ops.
            ai_val = _coerce_json(original_json.get(key))
            doc_val = _coerce_json(edited_json.get(key))

            if ai_val == doc_val:
                segments_unchanged += 1
                total_ai_words += _count_ai_words(ai_val)
                continue

            # Both empty (e.g. [] vs None) — belt-and-braces for the case
            # where edited_json stores an explicit null for the key.
            if is_empty_like(ai_val) and is_empty_like(doc_val):
                segments_unchanged += 1
                continue

            segments_modified += 1

            ai_text = _flatten_segment_to_text(ai_val)
            doc_text = _flatten_segment_to_text(doc_val)

            wer_result = compute_modified_wer(
                ai_text, doc_text, transcript_text or "", segment_code=key,
            )

            total_ai_words += wer_result["ai_word_count"]
            total_doc_words += wer_result["doctor_word_count"]
            total_counsellor_additions += wer_result["doctor_additions"]

            segment_metrics.append({
                "segment_code": key,
                "wer": wer_result["wer"],
                "wer_adjusted": wer_result["wer_adjusted"],
                "wer_adjusted_descriptions": wer_result["wer_adjusted_descriptions"],
                "substitutions": wer_result["substitutions"],
                "deletions": wer_result["deletions"],
                "insertions": wer_result["insertions"],
                "substitutions_ai_error": wer_result["substitutions_ai_error"],
                "deletions_ai_error": wer_result["deletions_ai_error"],
                "insertions_ai_error": wer_result["insertions_ai_error"],
                "paraphrase_count": wer_result["paraphrase_count"],
                "doctor_rephrasing": wer_result["doctor_rephrasing"],
                "doctor_trims": wer_result["doctor_trims"],
                "doctor_additions": wer_result["doctor_additions"],
                "ai_word_count": wer_result["ai_word_count"],
            })

        segments_total = segments_unchanged + segments_modified

        # Pooled WER: transcript-gated (subs + dels + ins) / AI words.
        total_errors = sum(
            s["substitutions_ai_error"] + s["deletions_ai_error"] + s["insertions_ai_error"]
            for s in segment_metrics
        )
        total_paraphrases = sum(s.get("paraphrase_count", 0) for s in segment_metrics)
        total_deletion_errors = sum(s.get("deletions_ai_error", 0) for s in segment_metrics)
        overall_wer = total_errors / max(total_ai_words, 1)
        overall_wer_adjusted = max(total_errors - total_paraphrases, 0) / max(total_ai_words, 1)
        # "Adjusted for description editing": also subtract deletion errors,
        # which are typically counsellor trims of verbose AI prose in description-
        # style free-text fields (e.g. chiefComplaints[*].description).
        overall_wer_adjusted_descriptions = (
            max(total_errors - total_paraphrases - total_deletion_errors, 0)
            / max(total_ai_words, 1)
        )

        # Entity error computation
        entity_result = _compute_entity_errors(original_json, edited_json, transcript_text or "")

        # Save to DB
        metrics_row = {
            "extraction_id": str(extraction_id),
            "counsellor_id": counsellor_id,
            "overall_wer": round(min(overall_wer, 1.0), 4),
            "overall_wer_adjusted": round(min(overall_wer_adjusted, 1.0), 4),
            "overall_wer_adjusted_descriptions": round(min(overall_wer_adjusted_descriptions, 1.0), 4),
            "segment_metrics": segment_metrics,
            "entity_error_rate": entity_result["entity_error_rate"],
            "entity_errors": entity_result,
            "total_words_ai_original": total_ai_words,
            "total_words_counsellor_edit": total_doc_words,
            "counsellor_additions_count": total_counsellor_additions,
            "segments_unchanged": segments_unchanged,
            "segments_modified": segments_modified,
            "segments_total": segments_total,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Upsert (unique on extraction_id)
        supabase.table("extraction_accuracy_metrics")\
            .upsert(metrics_row, on_conflict="extraction_id")\
            .execute()

        logger.info(
            f"[ACCURACY] Computed metrics for extraction {extraction_id}: "
            f"WER={overall_wer:.4f}, entity_err={entity_result['entity_error_rate']:.2f}%, "
            f"segments={segments_modified}/{segments_total} modified"
        )

    except Exception as e:
        logger.warning(f"[ACCURACY] Failed to compute/save accuracy metrics for {extraction_id}: {e}")
