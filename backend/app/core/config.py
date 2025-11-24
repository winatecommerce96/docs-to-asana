"""
Application configuration and settings
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    APP_NAME: str = "Asana Brief Creation"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./asana_briefs.db"  # Default to SQLite for resilience
    DB_PASSWORD: str = ""

    # Redis (optional, for Celery)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Asana Configuration
    ASANA_ACCESS_TOKEN: str
    ASANA_WORKSPACE_ID: str
    ASANA_REDIRECT_URI: str = ""

    # Asana OAuth Configuration
    ASANA_CLIENT_ID: str = ""
    ASANA_CLIENT_SECRET: str = ""
    ASANA_OAUTH_REDIRECT_URI: str = ""  # OAuth callback URL (e.g., https://api.emailpilot.ai/auth/callback)

    # Brief Creation Target Configuration
    ASANA_TARGET_PROJECT_GID: str = ""  # Default project for task creation
    ASANA_TARGET_SECTION_GID: str = ""  # Default section for task creation

    # AI Provider Configuration
    AI_PROVIDER: str = "anthropic"  # "anthropic" or "openai"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    AI_MODEL: str = "claude-3-5-sonnet-20241022"  # or "gpt-4", etc.
    AI_REVIEW_PROMPT: str = ""  # Custom prompt template (optional)

    # Google Docs API
    GOOGLE_DOCS_CREDENTIALS_PATH: str = ""
    GOOGLE_DOCS_TOKEN_PATH: str = ""

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Build DATABASE_URL with password if DB_PASSWORD is set
        if self.DB_PASSWORD and "postgresql" in self.DATABASE_URL:
            # Parse the URL and inject the password
            import re
            # Replace user@ with user:password@
            self.DATABASE_URL = re.sub(
                r'://([^@:]+)@',
                f'://\\1:{self.DB_PASSWORD}@',
                self.DATABASE_URL
            )

    # Frontend
    FRONTEND_URL: str = "http://localhost:3001"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3001"

    # Notifications (optional)
    SLACK_WEBHOOK_URL: str = ""
    SLACK_BOT_TOKEN: str = ""
    SLACK_NOTIFICATIONS_ENABLED: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS into a list - supports both comma and semicolon separators"""
        # Try semicolon first (used in Cloud Run), fallback to comma
        separator = ";" if ";" in self.ALLOWED_ORIGINS else ","
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(separator)]

    @property
    def copy_review_projects_list(self) -> List[str]:
        """Parse COPY_REVIEW_PROJECTS into a list - supports both comma and semicolon separators"""
        if not self.COPY_REVIEW_PROJECTS:
            return []
        # Try semicolon first (used in Cloud Run), fallback to comma
        separator = ";" if ";" in self.COPY_REVIEW_PROJECTS else ","
        return [proj.strip() for proj in self.COPY_REVIEW_PROJECTS.split(separator) if proj.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
