"""
Admin API routes for managing projects and submitting briefs
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from loguru import logger
import json
import os
from pathlib import Path

from app.services.task_creation_service import TaskCreationService
from app.core.asana_client import AsanaClient

router = APIRouter(prefix="/admin", tags=["admin"])

# Path to projects configuration file
PROJECTS_FILE = Path(__file__).parent.parent.parent.parent / "projects.json"


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
def load_projects() -> List[Project]:
    """Load projects from JSON file"""
    if not PROJECTS_FILE.exists():
        return []

    try:
        with open(PROJECTS_FILE, 'r') as f:
            data = json.load(f)
            return [Project(**p) for p in data]
    except Exception as e:
        logger.error(f"Error loading projects: {e}")
        return []


def save_projects(projects: List[Project]):
    """Save projects to JSON file"""
    try:
        with open(PROJECTS_FILE, 'w') as f:
            json.dump([p.model_dump() for p in projects], f, indent=2)
    except Exception as e:
        logger.error(f"Error saving projects: {e}")
        raise


# API Endpoints
@router.get("/projects", response_model=List[Project])
async def list_projects():
    """List all configured projects"""
    return load_projects()


@router.post("/projects", response_model=Project)
async def add_project(project: Project):
    """Add a new project configuration"""
    projects = load_projects()

    # Check if project ID already exists
    if any(p.id == project.id for p in projects):
        raise HTTPException(
            status_code=400,
            detail=f"Project with ID '{project.id}' already exists"
        )

    # Verify the project exists in Asana
    asana = AsanaClient()
    try:
        custom_fields = await asana.get_project_custom_fields(project.project_gid)
        logger.info(f"Verified project {project.project_gid} - found {len(custom_fields)} custom fields")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to verify project in Asana: {str(e)}"
        )

    # Verify section if provided
    if project.section_gid:
        try:
            sections = await asana.get_project_sections(project.project_gid)
            if not any(s.get("gid") == project.section_gid for s in sections):
                raise HTTPException(
                    status_code=400,
                    detail=f"Section {project.section_gid} not found in project"
                )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to verify section: {str(e)}"
            )

    # Add project
    projects.append(project)
    save_projects(projects)

    logger.info(f"Added project: {project.name} ({project.id})")
    return project


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project configuration"""
    projects = load_projects()

    # Find and remove project
    projects = [p for p in projects if p.id != project_id]
    save_projects(projects)

    logger.info(f"Deleted project: {project_id}")
    return {"status": "deleted", "project_id": project_id}


@router.post("/submit")
async def submit_brief(request: SubmitBriefRequest):
    """
    Submit a brief for processing

    This will create tasks in the specified project using the configured section
    """
    # Load projects
    projects = load_projects()

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
