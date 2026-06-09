"""
Counsellor Task (TODO) Service

CRUD operations for the `counsellor_tasks` table — the to-do items a counsellor manages.

A task is either:
  * Per-student   -> student_id is set (assigned to a specific student)
  * Personal      -> student_id is None (the counsellor's own private item)

Fields mirror the TASKS extraction segment so tasks can later be seeded from an extraction.
Deletes are soft (is_active = False), matching how counsellors/templates are removed.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .supabase_service import supabase

# Columns persisted on create/update (kept here so insert/update stay in sync).
_TASK_FIELDS = (
    "student_id",
    "source_extraction_id",
    "task_name",
    "task_details",
    "task_type",
    "start_date",
    "end_date",
    "bucket_id",
    "duration_in_minutes",
    "task_category",
    "task_file_resource",
    "requires_approval",
    "status",
    "external_id",
)


def _validate_student(student_id: str, counsellor_id: str) -> Dict[str, Any]:
    """
    Ensure a student exists and is linked to this counsellor.

    Returns the student record. Raises ValueError if the student does not exist or
    is not associated with the counsellor (counsellors.id is held in students.counsellor_ids).
    """
    response = (
        supabase.table("students")
        .select("id, counsellor_ids, school_id")
        .eq("id", student_id)
        .execute()
    )

    if not response.data:
        raise ValueError(f"Student with ID '{student_id}' not found")

    student = response.data[0]
    counsellor_ids = student.get("counsellor_ids") or []
    if counsellor_id not in counsellor_ids:
        raise ValueError("Student is not assigned to this counsellor")

    return student


def list_tasks(
    counsellor_id: str,
    student_id: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    List a counsellor's tasks, newest first.

    Args:
        counsellor_id: Owner counsellor UUID
        student_id: Filter to a specific student (pass "personal" to get only personal todos)
        status: Filter by status (open / in_progress / done / cancelled)
        active_only: Exclude soft-deleted tasks (default True)
    """
    query = supabase.table("counsellor_tasks").select("*").eq("counsellor_id", counsellor_id)

    if active_only:
        query = query.eq("is_active", True)
    if status:
        query = query.eq("status", status)
    if student_id == "personal":
        query = query.is_("student_id", "null")
    elif student_id:
        query = query.eq("student_id", student_id)

    response = query.order("created_at", desc=True).execute()
    return response.data if response.data else []


def get_task(counsellor_id: str, task_id: str) -> Optional[Dict[str, Any]]:
    """Get a single task scoped to its owner counsellor. Returns None if not found."""
    response = (
        supabase.table("counsellor_tasks")
        .select("*")
        .eq("id", task_id)
        .eq("counsellor_id", counsellor_id)
        .execute()
    )
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def create_task(counsellor_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a task for a counsellor.

    Args:
        counsellor_id: Owner counsellor UUID
        fields: Task attributes (subset of _TASK_FIELDS). student_id may be None (personal todo).

    Raises:
        ValueError: If a provided student_id is invalid / not assigned to the counsellor.
    """
    student_id = fields.get("student_id")
    if student_id:
        _validate_student(student_id, counsellor_id)

    now = datetime.utcnow().isoformat()
    task_data: Dict[str, Any] = {"counsellor_id": counsellor_id, "created_at": now, "updated_at": now}
    for key in _TASK_FIELDS:
        if key in fields and fields[key] is not None:
            task_data[key] = fields[key]

    response = supabase.table("counsellor_tasks").insert(task_data).execute()
    if not response.data or len(response.data) == 0:
        raise Exception("Failed to create task")

    return response.data[0]


def update_task(counsellor_id: str, task_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing task. Only provided (non-None) fields are changed.

    Raises:
        ValueError: If the task is not found, or a new student_id is invalid.
    """
    existing = get_task(counsellor_id, task_id)
    if not existing:
        raise ValueError(f"Task with ID '{task_id}' not found")

    if fields.get("student_id"):
        _validate_student(fields["student_id"], counsellor_id)

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
    for key in _TASK_FIELDS:
        if key in fields and fields[key] is not None:
            update_data[key] = fields[key]

    response = (
        supabase.table("counsellor_tasks")
        .update(update_data)
        .eq("id", task_id)
        .eq("counsellor_id", counsellor_id)
        .execute()
    )
    if not response.data or len(response.data) == 0:
        raise Exception("Failed to update task")

    return response.data[0]


def soft_delete_task(counsellor_id: str, task_id: str) -> Dict[str, Any]:
    """
    Soft-delete a task (is_active = False). Raises ValueError if not found.
    """
    existing = get_task(counsellor_id, task_id)
    if not existing:
        raise ValueError(f"Task with ID '{task_id}' not found")

    response = (
        supabase.table("counsellor_tasks")
        .update({"is_active": False, "updated_at": datetime.utcnow().isoformat()})
        .eq("id", task_id)
        .eq("counsellor_id", counsellor_id)
        .execute()
    )
    if not response.data or len(response.data) == 0:
        raise Exception("Failed to delete task")

    return response.data[0]
