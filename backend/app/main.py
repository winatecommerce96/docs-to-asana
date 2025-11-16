"""
FastAPI application for Asana Brief Creation
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
import sys
from pathlib import Path

from app.core.config import settings
from app.api.routes import briefs, admin

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Create FastAPI app
app = FastAPI(
    title="Asana Brief Creation API",
    description="AI-powered service to create Asana tasks from Google Doc campaign briefs",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(briefs.router)
app.include_router(admin.router)

# Mount static files at root (will serve index.html)
static_path = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Starting Asana Brief Creation service")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"AI Model: {settings.AI_MODEL}")
    logger.info(f"AI Provider: {settings.AI_PROVIDER}")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Asana Brief Creation service")
