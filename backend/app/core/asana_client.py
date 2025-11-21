"""
Asana API Client for Brief Creation

Extended client for:
- Fetching task details, attachments
- Posting comments
- Creating tasks with custom fields
- Managing project sections and custom fields
"""
import httpx
from typing import List, Dict, Any, Optional
from loguru import logger

from .config import settings


class AsanaClient:
    """
    Asana API client for copy review operations

    Provides methods for:
    - Getting task details
    - Fetching attachments
    - Posting comments
    """

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.ASANA_ACCESS_TOKEN
        self.base_url = "https://app.asana.com/api/1.0"

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }

    async def get_task_details(self, task_id: str, include_attachments: bool = True) -> Dict[str, Any]:
        """
        Get full details for a specific task

        Args:
            task_id: Asana task ID (GID)
            include_attachments: If True, fetch and include attachment URLs

        Returns:
            Dictionary with complete task data
        """
        url = f"{self.base_url}/tasks/{task_id}"

        params = {
            "opt_fields": "name,notes,completed_at,projects.name,projects.gid,custom_fields.name,custom_fields.text_value,custom_fields.enum_value.name,custom_fields.display_value,custom_fields.number_value,assignee.name,assignee.email"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                task_data = data.get("data", {})

                # Optionally fetch attachments
                if include_attachments:
                    attachments = await self.get_task_attachments(task_id)
                    task_data["attachments"] = attachments

                return task_data

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching task {task_id}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error fetching task {task_id}: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise

    async def get_task_attachments(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get all attachments for a specific task

        Args:
            task_id: Asana task ID (GID)

        Returns:
            List of attachment dictionaries with name, download_url, view_url, etc.
        """
        url = f"{self.base_url}/tasks/{task_id}/attachments"

        params = {
            "opt_fields": "name,resource_type,resource_subtype,view_url,download_url"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                attachments = data.get("data", [])

                logger.info(f"Found {len(attachments)} attachments for task {task_id}")
                return attachments

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching attachments for task {task_id}: {e.response.status_code} - {e.response.text}")
                return []
            except Exception as e:
                logger.error(f"Error fetching attachments for task {task_id}: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return []

    async def attach_external_resource(
        self,
        task_id: str,
        resource_url: str,
        name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Attach an external resource (like a Google Doc) to a task

        Automatically detects Google Drive/Docs URLs and uses the appropriate
        resource_subtype for better integration with Asana's Google Drive add-on.

        Args:
            task_id: Asana task ID (GID)
            resource_url: URL of the external resource
            name: Optional name for the attachment

        Returns:
            Attachment data if successful, None otherwise
        """
        url = f"{self.base_url}/attachments"

        # Detect if this is a Google Docs/Drive URL and use appropriate subtype
        resource_subtype = "external"
        if "docs.google.com" in resource_url or "drive.google.com" in resource_url:
            # Use "google" subtype for Google Drive integration
            resource_subtype = "google"
            logger.debug(f"Detected Google Drive URL, using resource_subtype='google'")

        payload = {
            "data": {
                "parent": task_id,
                "resource_subtype": resource_subtype,
                "url": resource_url
            }
        }

        if name:
            payload["data"]["name"] = name

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                attachment = data.get("data", {})

                logger.info(f"Attached {resource_subtype} resource to task {task_id}: {resource_url}")
                return attachment

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error attaching resource to task {task_id}: {e.response.status_code} - {e.response.text}")
                # If Google Drive subtype failed, try falling back to external
                if resource_subtype == "google":
                    logger.info(f"Retrying with resource_subtype='external'")
                    payload["data"]["resource_subtype"] = "external"
                    try:
                        response = await client.post(
                            url,
                            headers=self.headers,
                            json=payload
                        )
                        response.raise_for_status()
                        data = response.json()
                        attachment = data.get("data", {})
                        logger.info(f"Attached external resource to task {task_id}: {resource_url}")
                        return attachment
                    except Exception as fallback_error:
                        logger.error(f"Fallback also failed: {fallback_error}")
                        return None
                return None
            except Exception as e:
                logger.error(f"Error attaching resource to task {task_id}: {e}")
                return None

    async def post_comment_to_task(self, task_id: str, comment_text: str) -> Optional[str]:
        """
        Post a comment to an Asana task with proper HTML formatting

        Args:
            task_id: Asana task ID (GID)
            comment_text: Text of the comment to post (supports markdown)

        Returns:
            Comment GID if successful, None otherwise
        """
        url = f"{self.base_url}/tasks/{task_id}/stories"

        # Convert markdown to HTML for consistent rendering in Asana
        html_text = self._markdown_to_html(comment_text)

        payload = {
            "data": {
                "html_text": html_text
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                comment_gid = data.get("data", {}).get("gid")

                logger.info(f"Posted comment {comment_gid} to task {task_id}")
                return comment_gid

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error posting comment to task {task_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"Error posting comment to task {task_id}: {e}")
                return None

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convert markdown to HTML for Asana comments

        Only uses Asana-supported HTML tags for rich text:
        - <strong> for bold
        - <em> for italic
        - <a href=""> for links

        Preserves newlines as actual line breaks (not <br> tags)
        """
        import re

        # Convert markdown to HTML using only supported tags
        html = markdown_text

        # Bold: **text** -> <strong>text</strong>
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

        # Italic: *text* -> <em>text</em>
        html = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html)

        # Links: [text](url) -> <a href="url">text</a>
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)

        # Keep newlines as-is (don't convert to <br> or any other tag)
        # Asana's rich text handles newlines natively

        return f"<body>{html}</body>"

    async def get_workspace_projects(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all projects in a workspace

        Args:
            workspace_id: Asana workspace ID (optional)

        Returns:
            List of project dictionaries
        """
        workspace = workspace_id or settings.ASANA_WORKSPACE_ID
        url = f"{self.base_url}/workspaces/{workspace}/projects"

        params = {
            "opt_fields": "name,archived"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                return data.get("data", [])

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching projects: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching projects: {e}")
                raise

    async def get_workspace_users(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all users in a workspace

        Args:
            workspace_id: Asana workspace ID (optional)

        Returns:
            List of user dictionaries with gid, name, and email
        """
        workspace = workspace_id or settings.ASANA_WORKSPACE_ID
        url = f"{self.base_url}/workspaces/{workspace}/users"

        params = {
            "opt_fields": "name,email"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                return data.get("data", [])

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching workspace users: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching workspace users: {e}")
                raise

    async def get_project_sections(self, project_gid: str) -> List[Dict[str, Any]]:
        """
        Get all sections in a project

        Args:
            project_gid: Asana project GID

        Returns:
            List of section dictionaries with gid and name
        """
        url = f"{self.base_url}/projects/{project_gid}/sections"

        params = {
            "opt_fields": "name,gid"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                sections = data.get("data", [])

                logger.info(f"Found {len(sections)} sections in project {project_gid}")
                return sections

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching sections for project {project_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error fetching sections for project {project_gid}: {e}")
                raise

    async def get_project_custom_fields(self, project_gid: str) -> List[Dict[str, Any]]:
        """
        Get all custom fields configured for a project

        Args:
            project_gid: Asana project GID

        Returns:
            List of custom field definitions with gid, name, type, and enum_options
        """
        url = f"{self.base_url}/projects/{project_gid}/custom_field_settings"

        params = {
            "opt_fields": "custom_field.gid,custom_field.name,custom_field.type,custom_field.resource_subtype,custom_field.enum_options.gid,custom_field.enum_options.name,custom_field.enum_options.enabled,custom_field.enum_options.color,custom_field.precision"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()

                data = response.json()
                field_settings = data.get("data", [])

                # Extract just the custom_field from each setting
                custom_fields = [setting.get("custom_field", {}) for setting in field_settings]

                logger.info(f"Found {len(custom_fields)} custom fields for project {project_gid}")
                return custom_fields

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching custom fields for project {project_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error fetching custom fields for project {project_gid}: {e}")
                raise

    async def create_task(
        self,
        name: str,
        project_gid: str,
        section_gid: Optional[str] = None,
        notes: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
        assignee_gid: Optional[str] = None,
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        parent_task_gid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new task in Asana with custom fields

        Args:
            name: Task name/title
            project_gid: Project to add task to
            section_gid: Optional section within project
            notes: Task description/notes
            custom_fields: Dict mapping custom field GIDs to values
                          Example: {"1234567890": "High", "0987654321": "2024-12-25"}
            assignee_gid: User GID to assign task to
            due_date: Due date in YYYY-MM-DD format
            start_date: Start date in YYYY-MM-DD format
            parent_task_gid: Parent task GID (for subtasks)

        Returns:
            Created task data including gid
        """
        url = f"{self.base_url}/tasks"

        # Build task data payload
        task_data = {
            "name": name,
            "projects": [project_gid]
        }

        # Add optional fields
        if notes:
            task_data["notes"] = notes

        if assignee_gid:
            task_data["assignee"] = assignee_gid

        if due_date:
            task_data["due_on"] = due_date

        if start_date:
            task_data["start_on"] = start_date

        if parent_task_gid:
            task_data["parent"] = parent_task_gid

        # Add custom fields if provided
        if custom_fields:
            task_data["custom_fields"] = custom_fields

        # Add section membership if specified
        if section_gid:
            task_data["memberships"] = [
                {
                    "project": project_gid,
                    "section": section_gid
                }
            ]

        payload = {"data": task_data}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                created_task = data.get("data", {})

                logger.info(f"Created task {created_task.get('gid')} - {name}")
                return created_task

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error creating task '{name}': {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error creating task '{name}': {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise

    async def update_task(
        self,
        task_gid: str,
        custom_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update an existing task

        Args:
            task_gid: Task GID to update
            custom_fields: Dict mapping custom field GIDs to new values
            **kwargs: Other task fields to update (name, notes, assignee, etc.)

        Returns:
            Updated task data
        """
        url = f"{self.base_url}/tasks/{task_gid}"

        update_data = {}

        # Add custom fields if provided
        if custom_fields:
            update_data["custom_fields"] = custom_fields

        # Add any other provided fields
        update_data.update(kwargs)

        payload = {"data": update_data}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                updated_task = data.get("data", {})

                logger.info(f"Updated task {task_gid}")
                return updated_task

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error updating task {task_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error updating task {task_gid}: {e}")
                raise

    async def create_webhook(self, resource_gid: str, target_url: str, filters: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Create a webhook for a resource

        Args:
            resource_gid: Resource GID to create webhook for
            target_url: Target URL for webhook events
            filters: Optional filters for webhook events

        Returns:
            Webhook data including gid
        """
        url = f"{self.base_url}/webhooks"

        payload = {
            "data": {
                "resource": resource_gid,
                "target": target_url
            }
        }

        if filters:
            payload["data"]["filters"] = filters

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                webhook_data = data.get("data", {})

                # Note: The webhook secret is captured during the handshake POST that Asana sends
                # to our webhook endpoint, not in this API response. See webhooks.py handshake handler.

                logger.info(f"Created webhook {webhook_data.get('gid')} for resource {resource_gid}")
                return webhook_data

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error creating webhook for {resource_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error creating webhook for {resource_gid}: {e}")
                raise

    async def get_webhook(self, webhook_gid: str) -> Dict[str, Any]:
        """
        Get a webhook by GID (to verify it exists)

        Args:
            webhook_gid: Webhook GID to get

        Returns:
            Webhook data
        """
        url = f"{self.base_url}/webhooks/{webhook_gid}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

                data = response.json()
                return data.get("data", {})

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error getting webhook {webhook_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error getting webhook {webhook_gid}: {e}")
                raise

    async def delete_webhook(self, webhook_gid: str) -> bool:
        """
        Delete a webhook

        Args:
            webhook_gid: Webhook GID to delete

        Returns:
            True if successful
        """
        url = f"{self.base_url}/webhooks/{webhook_gid}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(url, headers=self.headers)
                response.raise_for_status()

                logger.info(f"Deleted webhook {webhook_gid}")
                return True

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error deleting webhook {webhook_gid}: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error deleting webhook {webhook_gid}: {e}")
                raise


# Singleton instance
_asana_client = None


def get_asana_client() -> AsanaClient:
    """Get or create AsanaClient singleton"""
    global _asana_client

    if _asana_client is None:
        _asana_client = AsanaClient()

    return _asana_client
