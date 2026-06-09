"""
Counsellor Task (TODO) Router

REST API endpoints letting a counsellor create, list, edit and delete their to-do items.
A task is either assigned to a student (student_id set) or personal (student_id null).

Nested under the counsellor for ownership clarity, mirroring /counsellors/{id}/templates.
Auth follows the same Admin + Web + School pattern as the counsellors router: EHR/school
clients are restricted to their own school's counsellor via verify_counsellor_access.
"""

import os
import uuid
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from services.counsellor_task_service import (
    list_tasks,
    get_task,
    create_task,
    update_task,
    soft_delete_task,
)

# Conditional EHR auth (mirrors routers/counsellors.py and counsellor_templates.py)
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
if AUTH_ENABLED:
    from dependencies.auth import EHRCounsellorAccessChecker, get_current_client

    _counsellor_checker = EHRCounsellorAccessChecker()

    async def verify_counsellor_access(request: Request, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        """Verify the authenticated client may act on this counsellor's data."""
        counsellor_uuid = uuid.UUID(counsellor_id) if counsellor_id else None
        client = get_current_client(request)
        return await _counsellor_checker(request, counsellor_uuid, client)
else:
    async def verify_counsellor_access(request: Request = None, counsellor_id: Optional[str] = None):  # type: ignore[misc]
        return None


router = APIRouter(prefix="/api/v1/counsellors", tags=["Counsellor Tasks"])


# ============================================================================
# Request models
# ============================================================================

class TaskCreateRequest(BaseModel):
    """Create a counsellor task. student_id null = personal to-do."""
    task_name: str = Field(..., min_length=1, max_length=300)
    student_id: Optional[str] = Field(None, description="Assignee student UUID; null for a personal to-do")
    source_extraction_id: Optional[str] = Field(None, description="Extraction this task was seeded from")
    task_details: Optional[str] = None
    task_type: str = Field("Once", pattern="^(Once|Daily|Weekly|Monthly)$")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    bucket_id: Optional[int] = None
    duration_in_minutes: Optional[int] = Field(None, ge=0)
    task_category: Optional[str] = Field(None, max_length=200)
    task_file_resource: Optional[str] = Field(None, max_length=500)
    requires_approval: bool = False
    status: str = Field("open", pattern="^(open|in_progress|done|cancelled)$")
    external_id: Optional[int] = None


class TaskUpdateRequest(BaseModel):
    """Update a counsellor task. Only provided fields are changed."""
    task_name: Optional[str] = Field(None, min_length=1, max_length=300)
    student_id: Optional[str] = None
    source_extraction_id: Optional[str] = None
    task_details: Optional[str] = None
    task_type: Optional[str] = Field(None, pattern="^(Once|Daily|Weekly|Monthly)$")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bucket_id: Optional[int] = None
    duration_in_minutes: Optional[int] = Field(None, ge=0)
    task_category: Optional[str] = Field(None, max_length=200)
    task_file_resource: Optional[str] = Field(None, max_length=500)
    requires_approval: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(open|in_progress|done|cancelled)$")
    external_id: Optional[int] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{counsellor_id}/tasks")
async def list_counsellor_tasks(
    request: Request,
    counsellor_id: str,
    student_id: Optional[str] = Query(
        None, description="Filter by student UUID, or 'personal' for only personal to-dos"
    ),
    status: Optional[str] = Query(None, description="open | in_progress | done | cancelled"),
    active_only: bool = Query(True, description="Exclude soft-deleted tasks"),
    _auth=Depends(verify_counsellor_access),
) -> Dict[str, Any]:
    """List a counsellor's tasks (newest first)."""
    try:
        tasks = list_tasks(
            counsellor_id=counsellor_id,
            student_id=student_id,
            status=status,
            active_only=active_only,
        )
        return {"success": True, "tasks": tasks, "count": len(tasks)}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to fetch tasks")


@router.post("/{counsellor_id}/tasks")
async def create_counsellor_task(
    request: Request,
    counsellor_id: str,
    body: TaskCreateRequest,
    _auth=Depends(verify_counsellor_access),
) -> Dict[str, Any]:
    """Create a task for a counsellor (per-student or personal)."""
    try:
        task = create_task(counsellor_id, body.model_dump(exclude_unset=True))
        return {"success": True, "task": task, "message": "Task created"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to create task")


@router.get("/{counsellor_id}/tasks/{task_id}")
async def get_counsellor_task(
    request: Request,
    counsellor_id: str,
    task_id: str,
    _auth=Depends(verify_counsellor_access),
) -> Dict[str, Any]:
    """Get a single task owned by the counsellor."""
    task = get_task(counsellor_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task}


@router.put("/{counsellor_id}/tasks/{task_id}")
async def update_counsellor_task(
    request: Request,
    counsellor_id: str,
    task_id: str,
    body: TaskUpdateRequest,
    _auth=Depends(verify_counsellor_access),
) -> Dict[str, Any]:
    """Edit a task. Only provided fields change."""
    try:
        task = update_task(counsellor_id, task_id, body.model_dump(exclude_unset=True))
        return {"success": True, "task": task, "message": "Task updated"}
    except ValueError as e:
        # "not found" -> 404, validation -> 400
        detail = str(e)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update task")


@router.delete("/{counsellor_id}/tasks/{task_id}")
async def delete_counsellor_task(
    request: Request,
    counsellor_id: str,
    task_id: str,
    _auth=Depends(verify_counsellor_access),
) -> Dict[str, Any]:
    """Soft-delete a task (is_active = false)."""
    try:
        soft_delete_task(counsellor_id, task_id)
        return {"success": True, "message": "Task deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete task")
