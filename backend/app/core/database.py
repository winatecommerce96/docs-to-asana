"""
Database configuration and session management
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from loguru import logger

from app.core.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create declarative base for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency for getting async database session

    Usage in FastAPI routes:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database - create all tables"""
    try:
        async with engine.begin() as conn:
            # Import all models here to ensure they are registered
            from app.models.brief import Brief, BriefTask, ProjectConfig  # noqa

            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.warning("Application will start but database operations may fail")
        # Don't re-raise - allow app to start even if DB fails


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")
