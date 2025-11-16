"""
Asana OAuth authentication routes
"""
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
import httpx
import secrets
from app.core.config import settings
from loguru import logger

router = APIRouter()


@router.get("/login")
async def login(request: Request):
    """Initiate Asana OAuth flow"""

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    # Build Asana OAuth URL
    asana_auth_url = (
        f"https://app.asana.com/-/oauth_authorize"
        f"?client_id={settings.ASANA_CLIENT_ID}"
        f"&redirect_uri={settings.ASANA_OAUTH_REDIRECT_URI}"
        f"&response_type=code"
        f"&state={state}"
        f"&scope=default"
    )

    return RedirectResponse(url=asana_auth_url)


@router.get("/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Asana OAuth callback"""

    # Check for errors
    if error:
        logger.error(f"OAuth error: {error}")
        return HTMLResponse(
            content=f"<html><body><h1>Authentication Error</h1><p>{error}</p></body></html>",
            status_code=400
        )

    # Verify state to prevent CSRF
    stored_state = request.session.get("oauth_state")
    if not state or not stored_state or state != stored_state:
        logger.error("OAuth state mismatch - potential CSRF attack")
        return HTMLResponse(
            content="<html><body><h1>Authentication Error</h1><p>Invalid state parameter</p></body></html>",
            status_code=400
        )

    if not code:
        return HTMLResponse(
            content="<html><body><h1>Authentication Error</h1><p>No authorization code received</p></body></html>",
            status_code=400
        )

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://app.asana.com/-/oauth_token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.ASANA_CLIENT_ID,
                    "client_secret": settings.ASANA_CLIENT_SECRET,
                    "redirect_uri": settings.ASANA_OAUTH_REDIRECT_URI,
                    "code": code
                }
            )
            response.raise_for_status()
            token_data = response.json()

            # Get user info to verify authentication
            user_response = await client.get(
                "https://app.asana.com/api/1.0/users/me",
                headers={"Authorization": f"Bearer {token_data['access_token']}"}
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            # Store user info in session
            request.session["authenticated"] = True
            request.session["user"] = {
                "gid": user_data["data"]["gid"],
                "name": user_data["data"]["name"],
                "email": user_data["data"]["email"]
            }
            request.session["access_token"] = token_data["access_token"]

            # Clear OAuth state
            request.session.pop("oauth_state", None)

            logger.info(f"User authenticated: {user_data['data']['email']}")

            # Redirect to admin page
            return RedirectResponse(url="/admin")

        except httpx.HTTPStatusError as e:
            logger.error(f"OAuth token exchange failed: {e.response.text}")
            return HTMLResponse(
                content=f"<html><body><h1>Authentication Error</h1><p>Failed to exchange authorization code</p></body></html>",
                status_code=500
            )
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            return HTMLResponse(
                content=f"<html><body><h1>Authentication Error</h1><p>An unexpected error occurred</p></body></html>",
                status_code=500
            )


@router.get("/logout")
async def logout(request: Request):
    """Log out and clear session"""
    request.session.clear()
    return RedirectResponse(url="/login")


@router.get("/me")
async def get_current_user(request: Request):
    """Get current authenticated user info"""
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "authenticated": True,
        "user": request.session.get("user")
    }
