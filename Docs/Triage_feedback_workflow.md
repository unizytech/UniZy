# Triage Feedback Learning Workflow

This document describes how the triage system learns from doctor feedback to personalize future suggestions.

## Overview

The triage system generates clinical suggestions (investigations, history questions, red flags) for each consultation. Doctors can provide feedback on these suggestions (accept/reject/modify), and the system learns from this feedback to improve future recommendations for each doctor.

## Database Schema

### Tables

#### `triage_suggestion_log`
Stores all generated triage suggestions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key (used for feedback reference) |
| `extraction_id` | UUID | Link to medical extraction |
| `doctor_id` | UUID | Doctor who received the suggestion |
| `suggestion_category` | TEXT | `critical_action`, `important_consideration`, `nice_to_have` |
| `suggestion_type` | TEXT | `investigation`, `red_flag`, `history`, etc. |
| `suggestion_text` | TEXT | The actual suggestion |
| `source_layer` | TEXT | `differential_tree`, `gemini_analysis`, `red_flag_match` |
| `confidence_score` | NUMERIC | AI confidence (0-1) |
| `priority_rank` | INT | Order priority |
| `rationale` | TEXT | Why this was suggested |
| `patient_context_applied` | JSONB | Patient context used |
| `created_at` | TIMESTAMPTZ | When generated |

#### `triage_feedback`
Stores doctor feedback on suggestions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `suggestion_id` | UUID | FK to `triage_suggestion_log.id` |
| `doctor_id` | UUID | Doctor providing feedback |
| `feedback_type` | TEXT | `accepted`, `rejected`, `maybe`, `modified` |
| `rejection_reason` | TEXT | Why rejected (optional) |
| `modified_text` | TEXT | New text if modified |
| `feedback_at` | TIMESTAMPTZ | When feedback was given |

#### `triage_doctor_stats` (View)
Aggregates feedback statistics per doctor.

| Column | Type | Description |
|--------|------|-------------|
| `doctor_id` | UUID | Doctor identifier |
| `full_name` | VARCHAR | Doctor's name |
| `total_suggestions` | BIGINT | How many suggestions shown |
| `total_feedback_given` | BIGINT | How many had feedback |
| `accepted_count` | BIGINT | Number accepted |
| `rejected_count` | BIGINT | Number rejected |
| `modified_count` | BIGINT | Number modified |
| `acceptance_rate_pct` | NUMERIC | Calculated acceptance rate |

### Database Functions

#### `get_doctor_feedback_patterns(p_doctor_id UUID)`
Returns full feedback history for a doctor with acceptance rates per suggestion.

```sql
SELECT * FROM get_doctor_feedback_patterns('doctor-uuid-here');
```

Returns: `suggestion_text`, `suggestion_type`, `source_layer`, `total_shown`, `accepted_count`, `rejected_count`, `modified_count`, `rejection_reasons[]`, `modified_versions[]`, `acceptance_rate`, `last_feedback_at`

#### `get_doctor_rejection_patterns(p_doctor_id UUID)`
Returns suggestions rejected 2+ times by a doctor (used for filtering).

```sql
SELECT * FROM get_doctor_rejection_patterns('doctor-uuid-here');
```

Returns: `suggestion_pattern`, `suggestion_type`, `rejection_count`, `common_reasons[]`

#### `get_doctor_preference_patterns(p_doctor_id UUID)`
Returns suggestions accepted 3+ times by a doctor (used for boosting).

```sql
SELECT * FROM get_doctor_preference_patterns('doctor-uuid-here');
```

Returns: `suggestion_pattern`, `suggestion_type`, `acceptance_count`, `avg_priority_rank`

## API Endpoints

### Submit Feedback

```
POST /api/v1/triage/feedback
```

**Request Body:**
```json
{
    "suggestion_id": "uuid-of-suggestion",
    "doctor_id": "uuid-of-doctor",
    "feedback_type": "accepted|rejected|maybe|modified",
    "rejection_reason": "optional reason if rejected",
    "modified_text": "new text if modified"
}
```

**Response:**
```json
{
    "success": true,
    "feedback_id": "uuid-of-feedback",
    "message": "Feedback 'accepted' recorded successfully"
}
```

### Get Doctor Stats

```
GET /api/v1/triage/feedback/stats/{doctor_id}
```

**Response:**
```json
{
    "doctor_id": "uuid",
    "total_suggestions": 150,
    "total_feedback_given": 120,
    "accepted_count": 95,
    "rejected_count": 15,
    "modified_count": 10,
    "acceptance_rate_pct": 79.2
}
```

## Learning System Architecture

### Data Flow

```
┌─────────────────────┐
│ Doctor provides     │
│ feedback on         │──────────────────────────────────────┐
│ suggestions         │                                      │
└─────────────────────┘                                      ▼
                                                   ┌─────────────────────┐
┌─────────────────────┐                            │ triage_feedback     │
│ Next triage request │                            │ table               │
│ (with doctor_id)    │                            └─────────────────────┘
└──────────┬──────────┘                                      │
           │                                                 ▼
           ▼                                      ┌─────────────────────┐
┌─────────────────────┐                           │ DB Functions        │
│ fetch_doctor_       │◀──────────────────────────│ - rejection_patterns│
│ preferences()       │                           │ - preference_patterns│
└──────────┬──────────┘                           └─────────────────────┘
           │
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│ Generate base       │────▶│ _apply_doctor_      │
│ suggestions         │     │ preferences()       │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │ Filtered & Boosted  │
                            │ Suggestions         │
                            └─────────────────────┘
```

### Python Components

#### `DoctorPreferences` Dataclass

Located in `services/triage/triage_engine.py`

```python
@dataclass
class DoctorPreferences:
    doctor_id: Optional[str] = None
    rejection_patterns: List[Dict[str, Any]]   # Suggestions to filter
    preference_patterns: List[Dict[str, Any]]  # Suggestions to boost
    feedback_history: List[Dict[str, Any]]     # Full history
    total_feedback_count: int = 0
    has_sufficient_data: bool = False          # True if 10+ entries

    def should_filter(self, suggestion_text: str) -> bool:
        """Returns True if suggestion matches a rejection pattern (3+ rejections)"""

    def get_boost_score(self, suggestion_text: str) -> int:
        """Returns 0-15 boost score based on acceptance history"""
```

#### `fetch_doctor_preferences()` Function

Async function that loads a doctor's learned preferences from the database.

```python
async def fetch_doctor_preferences(doctor_id: str, supabase_client) -> DoctorPreferences:
    """
    Calls database functions:
    - get_doctor_rejection_patterns
    - get_doctor_preference_patterns
    - get_doctor_feedback_patterns
    """
```

#### `_apply_doctor_preferences()` Method

Applies learned preferences to filter and prioritize suggestions.

```python
def _apply_doctor_preferences(
    self,
    suggestions: TriageSuggestions,
    preferences: DoctorPreferences
) -> TriageSuggestions:
    """
    1. FILTER: Remove suggestions rejected 3+ times
    2. BOOST: Add notes to frequently accepted suggestions
    3. PROMOTE: Move highly boosted suggestions to higher priority
    """
```

## Learning Rules

| Rule | Threshold | Action |
|------|-----------|--------|
| **Minimum Data** | 10+ feedback entries | Learning only activates after this threshold |
| **Filter** | Rejected 3+ times | Suggestion is removed from results |
| **Boost (small)** | Accepted 3-5 times | Note added to rationale (+5 score) |
| **Boost (medium)** | Accepted 6-10 times | Note added + priority influence (+10 score) |
| **Boost (strong)** | Accepted 10+ times | Promoted from "nice_to_have" to "important" (+15 score) |

### Pattern Matching

Suggestions are matched using normalized text (first 100 characters, lowercase). This allows the system to recognize similar suggestions even if wording varies slightly.

```python
# Example: These would match as the same pattern
"Consider ordering: CBC with differential"
"consider ordering: cbc with differential and platelets"
```

## Integration with Triage Generation

The learning is automatically applied in `generate_suggestions_v2()`:

```python
async def generate_suggestions_v2(
    self,
    extraction: Dict[str, Any],
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,  # Required for learning
    ...
) -> TriageSuggestions:
    # Step 0: Fetch doctor preferences (learned from feedback)
    doctor_preferences = None
    if doctor_id and supabase_client:
        doctor_preferences = await fetch_doctor_preferences(doctor_id, supabase_client)

    # ... generate base suggestions ...

    # Apply doctor preference learning (filter rejected, boost accepted)
    if doctor_preferences and doctor_preferences.has_sufficient_data:
        suggestions = self._apply_doctor_preferences(suggestions, doctor_preferences)
```

## Logging

The system logs learning actions for debugging:

```
[TRIAGE_LEARN] Loaded 5 rejection patterns for doctor abc123
[TRIAGE_LEARN] Loaded 12 preference patterns for doctor abc123
[TRIAGE_LEARN] Doctor abc123 has 45 feedback entries
[TRIAGE_LEARN] Filtered suggestion (frequently rejected): Consider ordering: Urine culture...
[TRIAGE_LEARN] Promoted suggestion (doctor preference): Order CBC with platelets...
[TRIAGE_LEARN] Applied preferences: filtered=2, boosted=5, promoted=1
```

## Future Enhancements

1. **Modified Text Learning**: Use `modified_text` from feedback to suggest the doctor's preferred wording
2. **Specialty-Specific Patterns**: Learn patterns per specialty, not just per doctor
3. **Confidence Decay**: Reduce confidence in old patterns over time
4. **Cross-Doctor Learning**: Identify patterns common across multiple doctors
5. **Rejection Reason Analysis**: Use `rejection_reason` text to understand why suggestions fail

## Files

| File | Description |
|------|-------------|
| `backend/supabase/migrations/20251228100000_add_doctor_feedback_patterns_functions.sql` | Database functions |
| `backend/services/triage/triage_engine.py` | `DoctorPreferences`, `fetch_doctor_preferences()`, `_apply_doctor_preferences()` |
| `backend/services/triage/__init__.py` | Exports `DoctorPreferences`, `fetch_doctor_preferences` |
| `backend/routers/triage.py` | API endpoints for feedback submission |
