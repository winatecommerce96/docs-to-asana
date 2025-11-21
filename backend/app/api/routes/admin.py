"""
Admin API routes for managing projects and submitting briefs
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.services.task_creation_service import TaskCreationService
from app.core.asana_client import AsanaClient
from app.core.database import get_db
from app.models.brief import ProjectConfig

router = APIRouter(prefix="/admin", tags=["admin"])


def error_response(status_code: int, error_code: str, detail: str, hint: str = ""):
    """Create a standardized error response with error code and hint"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "detail": detail,
            "hint": hint
        }
    )


# Models
class Project(BaseModel):
    """Project configuration"""
    id: str = Field(..., description="Unique ID for this project")
    name: str = Field(..., description="Project name")
    project_gid: str = Field(..., description="Asana project GID")
    section_gid: Optional[str] = Field(None, description="Default section GID (Copywriter)")
    resend_upcycle_section_gid: Optional[str] = Field(None, description="Section GID for RESEND/UPCYCLE tasks")


class SubmitBriefRequest(BaseModel):
    """Request to submit a brief for processing"""
    project_id: str = Field(..., description="Project ID to create tasks in")
    google_doc_url: str = Field(..., description="Google Doc URL")
    ai_model: Optional[str] = Field(None, description="Claude model to use for parsing (e.g., claude-sonnet-4-20250514)")


# Helper functions
async def load_projects(db: AsyncSession) -> List[Project]:
    """Load projects from database"""
    try:
        result = await db.execute(select(ProjectConfig))
        configs = result.scalars().all()
        return [Project(
            id=c.id,
            name=c.name,
            project_gid=c.project_gid,
            section_gid=c.section_gid,
            resend_upcycle_section_gid=c.resend_upcycle_section_gid
        ) for c in configs]
    except Exception as e:
        logger.error(f"Error loading projects: {e}")
        return []


async def save_project(db: AsyncSession, project: Project):
    """Save a project to database"""
    try:
        config = ProjectConfig(
            id=project.id,
            name=project.name,
            project_gid=project.project_gid,
            section_gid=project.section_gid,
            resend_upcycle_section_gid=project.resend_upcycle_section_gid
        )
        db.add(config)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving project: {e}")
        raise


# API Endpoints
@router.get("/projects", response_model=List[Project])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all configured projects"""
    return await load_projects(db)


@router.post("/projects", response_model=Project)
async def add_project(project: Project, db: AsyncSession = Depends(get_db)):
    """Add a new project configuration"""
    projects = await load_projects(db)

    # Check if project ID already exists
    if any(p.id == project.id for p in projects):
        return error_response(
            400,
            "DUPLICATE_PROJECT_ID",
            f"Project with ID '{project.id}' already exists",
            "Choose a different project name or delete the existing project first."
        )

    # Verify the project exists in Asana
    asana = AsanaClient()
    try:
        custom_fields = await asana.get_project_custom_fields(project.project_gid)
        logger.info(f"Verified project {project.project_gid} - found {len(custom_fields)} custom fields")
    except Exception as e:
        error_str = str(e)
        if "401" in error_str or "unauthorized" in error_str.lower():
            return error_response(
                400,
                "ASANA_AUTH_ERROR",
                "Failed to authenticate with Asana",
                "Check that your ASANA_ACCESS_TOKEN environment variable is valid and not expired."
            )
        elif "404" in error_str or "not found" in error_str.lower():
            return error_response(
                400,
                "ASANA_PROJECT_NOT_FOUND",
                f"Project GID '{project.project_gid}' not found in Asana",
                "Verify the project exists in your Asana workspace and you have access to it."
            )
        else:
            return error_response(
                400,
                "ASANA_VERIFICATION_FAILED",
                f"Failed to verify project in Asana: {error_str}",
                "Check your Asana connection and project permissions."
            )

    # Verify section if provided
    if project.section_gid:
        try:
            sections = await asana.get_project_sections(project.project_gid)
            if not any(s.get("gid") == project.section_gid for s in sections):
                return error_response(
                    400,
                    "SECTION_NOT_FOUND",
                    f"Section {project.section_gid} not found in project",
                    "Make sure you selected a valid section from the dropdown."
                )
        except Exception as e:
            return error_response(
                400,
                "SECTION_VERIFICATION_FAILED",
                f"Failed to verify section: {str(e)}",
                "Check that the section exists and you have access to it."
            )

    # Add project to database
    try:
        await save_project(db, project)
    except Exception as e:
        error_str = str(e)
        if "duplicate" in error_str.lower() or "unique" in error_str.lower():
            return error_response(
                500,
                "DATABASE_DUPLICATE_ERROR",
                "Project already exists in database",
                "Try refreshing the page and check if the project was already added."
            )
        else:
            return error_response(
                500,
                "DATABASE_SAVE_ERROR",
                f"Failed to save project to database: {error_str}",
                "Check database connection. The DATABASE_URL environment variable must be correctly configured."
            )

    logger.info(f"Added project: {project.name} ({project.id})")
    return project


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a project configuration"""
    await db.execute(delete(ProjectConfig).where(ProjectConfig.id == project_id))
    await db.commit()

    logger.info(f"Deleted project: {project_id}")
    return {"status": "deleted", "project_id": project_id}


@router.post("/submit")
async def submit_brief(request: SubmitBriefRequest, db: AsyncSession = Depends(get_db)):
    """
    Submit a brief for processing

    This will create tasks in the specified project using the configured section
    """
    # Load projects
    projects = await load_projects(db)

    # Find the project
    project = next((p for p in projects if p.id == request.project_id), None)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{request.project_id}' not found"
        )

    logger.info(f"Submitting brief to project {project.name}")
    logger.info(f"Google Doc: {request.google_doc_url}")
    if request.ai_model:
        logger.info(f"Using AI model: {request.ai_model}")

    # Create tasks using TaskCreationService
    service = TaskCreationService()

    try:
        results = await service.create_tasks_from_brief(
            doc_url=request.google_doc_url,
            project_gid=project.project_gid,
            section_gid=project.section_gid,
            resend_upcycle_section_gid=project.resend_upcycle_section_gid,
            ai_model=request.ai_model,
            dry_run=False
        )

        logger.info(f"Created {results['tasks_created']} tasks successfully")
        return results

    except Exception as e:
        logger.error(f"Error creating tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sections/{project_gid}")
async def get_project_sections(project_gid: str):
    """Get all sections for a project (useful for UI)"""
    asana = AsanaClient()

    try:
        sections = await asana.get_project_sections(project_gid)
        return sections
    except Exception as e:
        logger.error(f"Error fetching sections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/asana-projects")
async def list_asana_projects():
    """Get all Asana projects from the workspace"""
    asana = AsanaClient()

    try:
        projects = await asana.get_workspace_projects()
        # Filter out archived projects
        active_projects = [p for p in projects if not p.get("archived", False)]
        return active_projects
    except Exception as e:
        logger.error(f"Error fetching Asana projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
