"""
Edit classifier for POC metrics.

Classifies edits between an extraction's original AI output and the counsellor's
edited version into:
  - magnitude: "major" | "minor"
  - additive: whether a list-type segment gained new entries
  - word_change_pct: token-set symmetric-diff ratio

Rule (approved 2026-04-21):
  major = segment_code in {prescription, diagnosis, investigations, ...}
          OR word_change_pct > 0.50
  minor = everything else
  additive is orthogonal — set whenever edited list is longer than original
"""

import re
from typing import Any, Dict, Iterable, Optional, Tuple, Union

# Segments where ANY change is considered clinically major, regardless of size
SEGMENT_MAJOR = {
    "prescription",
    "diagnosis",
    "investigations",
    "prescriptionOp",
    "diagnosisOp",
    "diagnosisDischarge",
    "investigationsOp",
    "prescriptionDischarge",
}

# Known date-field paths whose changes count as "Dates error"
# (flat dotted-path; list items denoted by [*])
DATE_FIELD_PATHS = (
    "followUp.review_date",
    "investigations[*].date",
    "prescription[*].duration",
    "prescription[*].durationDays",
    "reportMetadata.date_of_consultation",
)


def _tokens(value: Any) -> set:
    """Flatten any JSON value to a set of whitespace-separated tokens (case-insensitive)."""
    if value is None:
        return set()
    # For dicts/lists, stringify then tokenize; order-insensitive because we set-ify
    return set(str(value).lower().split())


def _content_tokens(value: Any) -> set:
    """Content-word tokens with JSON punctuation/structural chars stripped.

    Used to detect pure reformat edits (e.g. list-of-strings → newline-joined
    string) where the *content* is identical but the *type* differs.
    """
    if value is None:
        return set()
    s = str(value).lower()
    s = re.sub(r'[\[\]\{\}"\',:]+', ' ', s)
    s = re.sub(r'[^\w\s.-]', ' ', s)
    return set(tok for tok in s.split() if tok)


_EMPTY_PLACEHOLDER_TOKENS = {"", "n/a", "na", "none", "nil", "-", "--"}


def is_empty_like(value: Any) -> bool:
    """True when the value carries no content.

    Catches the common artifact where the EHR edit flow drops untouched
    segments: original is [] / "" / {} and edited is None (or vice versa).
    Also treats common "no-value" placeholders ("N/A", "None", "nil", "-")
    as empty-like, so `N/A → ""` reformats aren't flagged as edits.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_PLACEHOLDER_TOKENS
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def strip_empties(value: Any) -> Any:
    """Recursively remove empty-like entries from dicts/lists.

    Produces a "content skeleton" suitable for semantic equality checks.
    `{a: "", b: "x"}` → `{b: "x"}`. `{a: "", b: ""}` → `{}`. Useful for
    suppressing missing-subkey noise inside a segment's structured value.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            sv = strip_empties(v)
            if not is_empty_like(sv):
                out[k] = sv
        return out
    if isinstance(value, list):
        stripped = [strip_empties(v) for v in value]
        return [v for v in stripped if not is_empty_like(v)]
    if isinstance(value, str):
        return value.strip()
    return value


def classify_edit(segment_code: str, original: Any, edited: Any) -> Dict[str, Any]:
    """Classify one segment's edit.

    Args:
        segment_code: e.g. "prescription", "summary"
        original: value from original_extraction_json for this segment
        edited:   value from edited_extraction_json for this segment

    Returns:
        {"changed": bool, "magnitude": "major"|"minor"|None,
         "additive": bool, "word_change_pct": float}
        When changed=False, magnitude=None and additive=False.
    """
    # Fast path: identical
    if original == edited:
        return {"changed": False, "magnitude": None, "additive": False, "word_change_pct": 0.0}

    # Both sides empty (e.g. [] vs None) — EHR edit flow drops untouched
    # segments, so this isn't a real edit.
    if is_empty_like(original) and is_empty_like(edited):
        return {"changed": False, "magnitude": None, "additive": False, "word_change_pct": 0.0}

    # Content-skeleton equality: ignore missing-subkey-as-empty noise and
    # whitespace-only differences. If the values are equal after recursively
    # dropping empty fields, it's not a real edit.
    stripped_orig = strip_empties(original)
    stripped_edit = strip_empties(edited)
    if stripped_orig == stripped_edit:
        return {"changed": False, "magnitude": None, "additive": False, "word_change_pct": 0.0}

    # Pure reformat (list ↔ string with identical content tokens):
    # e.g. ["Back pain", "Hip pain"] → "Back pain\nHip pain"
    if type(stripped_orig) is not type(stripped_edit) and _content_tokens(stripped_orig) == _content_tokens(stripped_edit):
        return {"changed": False, "magnitude": None, "additive": False, "word_change_pct": 0.0}

    additive = False
    if isinstance(original, list) and isinstance(edited, list):
        additive = len(edited) > len(original)
    # Treat None-vs-present as additive too if edited is a non-empty list
    if original in (None, "", []) and isinstance(edited, list) and len(edited) > 0:
        additive = True

    orig_tokens = _tokens(original)
    edit_tokens = _tokens(edited)
    if not orig_tokens and not edit_tokens:
        pct = 0.0
    else:
        union = orig_tokens | edit_tokens
        diff = orig_tokens.symmetric_difference(edit_tokens)
        pct = len(diff) / max(len(union), 1)

    is_major = (segment_code in SEGMENT_MAJOR) or (pct > 0.50)
    magnitude = "major" if is_major else "minor"

    return {
        "changed": True,
        "magnitude": magnitude,
        "additive": additive,
        "word_change_pct": round(pct, 4),
    }


def _get_by_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path with optional [*] list wildcards.

    Returns either the value at path (scalar) or a list of values (when [*] expands).
    Missing keys → None (for scalar path) or [] (for wildcard path).
    """
    parts = path.split(".")
    current: Any = obj
    has_wildcard = any("[*]" in p for p in parts)

    if not has_wildcard:
        for p in parts:
            if isinstance(current, dict) and p in current:
                current = current[p]
            else:
                return None
        return current

    # Wildcard: collect matching values
    results = [current]
    for p in parts:
        if p.endswith("[*]"):
            key = p[:-3]
            next_vals = []
            for item in results:
                if isinstance(item, dict) and isinstance(item.get(key), list):
                    next_vals.extend(item[key])
            results = next_vals
        else:
            next_vals = []
            for item in results:
                if isinstance(item, dict) and p in item:
                    next_vals.append(item[p])
            results = next_vals
    return results


# Date format patterns tried in order — first match wins
_DATE_PATTERNS = (
    # YYYY-MM-DD or YYYY/MM/DD
    (re.compile(r'^\s*(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})\s*$'), ("y", "m", "d")),
    # DD-MM-YYYY or DD/MM/YYYY or DD.MM.YYYY
    (re.compile(r'^\s*(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})\s*$'), ("d", "m", "y")),
    # DD-MM-YY (2-digit year assumed as 20YY)
    (re.compile(r'^\s*(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2})\s*$'), ("d", "m", "yy")),
)


def _normalize_value(v: Any) -> Union[Tuple[int, int, int], str, None]:
    """Normalize a value for relaxed equality comparison.

    - If the value parses as a date (several common formats), return a
      canonical (year, month, day) tuple so formats compare equal.
    - Otherwise return a stripped, lowercased string.
    - None and empty strings both map to None so they compare equal.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None

    for pattern, order in _DATE_PATTERNS:
        m = pattern.match(s)
        if m:
            parts = dict(zip(order, m.groups()))
            year = int(parts.get("y", parts.get("yy", 0)))
            if "yy" in parts:
                year = 2000 + int(parts["yy"])
            month = int(parts["m"])
            day = int(parts["d"])
            # Basic sanity check; fall back to string if ranges are bad
            if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                return (year, month, day)

    return s.lower()


def _values_match(a: Any, b: Any) -> bool:
    """Relaxed equality: date-format agnostic, case/whitespace insensitive."""
    return _normalize_value(a) == _normalize_value(b)


def count_date_errors(original: Dict[str, Any], edited: Dict[str, Any]) -> int:
    """Count genuine date/duration changes between original and edited.

    Rules:
      - Only fields in DATE_FIELD_PATHS are considered.
      - Date strings are normalized before compare (YYYY-MM-DD, DD-MM-YYYY,
        DD/MM/YYYY, DD-MM-YY all compare equal when they denote the same
        calendar date). Case/whitespace-insensitive for non-date values.
      - For list-valued paths (e.g. prescription[*].durationDays) only items
        present in BOTH lists are compared pairwise. Newly-added or deleted
        items are NOT counted as date errors — those are classified as
        additive/major edits elsewhere.
    """
    if not isinstance(original, dict) or not isinstance(edited, dict):
        return 0
    # Artifact guard: skip paths whose top-level segment exists in `original`
    # but is missing from `edited` (counsellor didn't touch that segment).
    artifact_top_keys = set(original.keys()) - set(edited.keys())
    count = 0
    for path in DATE_FIELD_PATHS:
        top = path.split(".", 1)[0].split("[", 1)[0]
        if top in artifact_top_keys:
            continue
        o = _get_by_path(original, path)
        e = _get_by_path(edited, path)
        if isinstance(o, list) or isinstance(e, list):
            o_list = o or []
            e_list = e or []
            # Only compare positions present in BOTH lists. Additions/deletions
            # are not date errors — they're list-level changes counted elsewhere.
            for idx in range(min(len(o_list), len(e_list))):
                if not _values_match(o_list[idx], e_list[idx]):
                    count += 1
        else:
            if not _values_match(o, e):
                count += 1
    return count


def classify_extraction_edits(
    original: Dict[str, Any],
    edited: Dict[str, Any],
    segment_codes: Iterable[str] = None,
) -> Dict[str, int]:
    """Walk an extraction JSON blob segment-by-segment and tally edit counts.

    Args:
        original: original_extraction_json dict
        edited:   edited_extraction_json dict (same shape)
        segment_codes: optional explicit list; defaults to the top-level keys
                       of `original` (union with `edited`).

    Returns:
        {"major": int, "minor": int, "additive": int, "dates": int}
    """
    if not isinstance(original, dict) or not isinstance(edited, dict):
        return {"major": 0, "minor": 0, "additive": 0, "dates": 0}

    if segment_codes is None:
        segment_codes = set((original or {}).keys()) | set((edited or {}).keys())

    major = minor = additive = 0
    for seg in segment_codes:
        # Artifact guard: the EHR edit flow drops untouched segments. If the
        # AI output had the key but the edit doesn't, the counsellor didn't touch
        # it — not a real edit. (A truly deleted segment would be present in
        # edit as [] or null, which still flows through classify_edit.)
        if seg in original and seg not in edited:
            continue
        o = original.get(seg)
        e = edited.get(seg)
        r = classify_edit(seg, o, e)
        if not r["changed"]:
            continue
        if r["magnitude"] == "major":
            major += 1
        else:
            minor += 1
        if r["additive"]:
            additive += 1

    dates = count_date_errors(original, edited)
    return {"major": major, "minor": minor, "additive": additive, "dates": dates}
