"""
API routes for brief processing
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from loguru import logger

from app.core.config import settings
from app.services.task_creation_service import TaskCreationService
from app.services.brief_parser import BriefParserService


router = APIRouter(prefix="/api/briefs", tags=["briefs"])


# Request/Response models
class BriefRequest(BaseModel):
    """Request to process a brief"""
    google_doc_url: str = Field(..., description="Google Doc URL")
    project_gid: str = Field(..., description="Asana project GID")
    section_gid: Optional[str] = Field(None, description="Asana section GID (optional)")
    dry_run: bool = Field(False, description="Preview only, don't create tasks")


class TaskResult(BaseModel):
    """Result of a single task creation"""
    task_number: int
    task_name: str
    success: bool
    asana_task_gid: Optional[str] = None
    asana_task_url: Optional[str] = None
    error: Optional[str] = None


class BriefResponse(BaseModel):
    """Response from brief processing"""
    campaign_name: str
    total_tasks: int
    tasks_created: int
    tasks_failed: int
    results: List[TaskResult]
    errors: List[str] = []
    preview: Optional[bool] = False


class PreviewResponse(BaseModel):
    """Preview of what tasks would be created"""
    campaign_name: str
    campaign_description: str
    total_tasks: int
    tasks_summary: List[Dict[str, Any]]


@router.post("/process", response_model=BriefResponse)
async def process_brief(request: BriefRequest):
    """
    Parse a Google Doc brief and create Asana tasks

    This endpoint:
    1. Fetches the Google Doc
    2. Uses Claude AI to parse and extract tasks
    3. Maps custom fields using AI-powered fuzzy matching
    4. Creates all tasks in the specified Asana project/section

    If dry_run=true, returns a preview without creating tasks.
    """
    logger.info(f"Processing brief: {request.google_doc_url}")
    logger.info(f"Target: project={request.project_gid}, section={request.section_gid}, dry_run={request.dry_run}")

    service = TaskCreationService()

    try:
        results = await service.create_tasks_from_brief(
            doc_url=request.google_doc_url,
            project_gid=request.project_gid,
            section_gid=request.section_gid,
            dry_run=request.dry_run
        )

        return BriefResponse(**results)

    except Exception as e:
        logger.error(f"Error processing brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview", response_model=PreviewResponse)
async def preview_brief(
    google_doc_url: str = Query(..., description="Google Doc URL")
):
    """
    Preview what tasks would be created from a brief without actually creating them

    Useful for validating the brief structure before committing to task creation
    """
    logger.info(f"Previewing brief: {google_doc_url}")

    parser = BriefParserService()

    try:
        preview = await parser.preview_brief(google_doc_url)
        return PreviewResponse(**preview)

    except Exception as e:
        logger.error(f"Error previewing brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
async def verify_project_and_section(
    project_gid: str = Query(..., description="Asana project GID"),
    section_gid: Optional[str] = Query(None, description="Asana section GID")
):
    """
    Verify that a project and section exist and are accessible

    Returns information about the project including available custom fields
    """
    logger.info(f"Verifying project={project_gid}, section={section_gid}")

    service = TaskCreationService()

    try:
        verification = await service.verify_project_and_section(
            project_gid=project_gid,
            section_gid=section_gid
        )

        if not verification["project_exists"]:
            raise HTTPException(
                status_code=404,
                detail=f"Project {project_gid} not found or not accessible"
            )

        if section_gid and not verification["section_exists"]:
            raise HTTPException(
                status_code=404,
                detail=f"Section {section_gid} not found in project {project_gid}"
            )

        return verification

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying project/section: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "service": "asana-brief-creation",
        "version": "1.0.0"
    }
