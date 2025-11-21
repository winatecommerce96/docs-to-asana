"""
Task Creation Service

Orchestrates the end-to-end process of creating Asana tasks from campaign briefs
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
from loguru import logger

from app.core.asana_client import AsanaClient
from app.services.brief_parser import BriefParserService
from app.services.custom_field_mapper import CustomFieldMapper
from app.services.google_docs import GoogleDocsService


def calculate_business_days_from_today(days: int) -> str:
    """
    Calculate a date N business days from today (excluding weekends)

    Args:
        days: Number of business days to add

    Returns:
        Date string in YYYY-MM-DD format
    """
    current_date = date.today()
    days_added = 0

    while days_added < days:
        current_date += timedelta(days=1)
        # Skip weekends (Saturday=5, Sunday=6)
        if current_date.weekday() < 5:
            days_added += 1

    return current_date.strftime("%Y-%m-%d")


class TaskCreationService:
    """
    Main orchestrator for creating Asana tasks from Google Doc briefs

    Workflow:
    1. Parse Google Doc brief → extract tasks
    2. Map custom fields using AI → convert names to GIDs
    3. Create tasks in Asana → with custom fields
    4. Return results with success/failure tracking
    """

    def __init__(self):
        self.asana_client = AsanaClient()
        self.brief_parser = BriefParserService()
        self.field_mapper = CustomFieldMapper(self.asana_client)
        self.google_docs = GoogleDocsService()

    async def create_tasks_from_brief(
        self,
        doc_url: str,
        project_gid: str,
        section_gid: Optional[str] = None,
        resend_upcycle_section_gid: Optional[str] = None,
        ai_model: Optional[str] = None,
        assignee_gid: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Main entry point: Parse brief and create all tasks

        Args:
            doc_url: Google Doc URL
            project_gid: Asana project GID to create tasks in
            section_gid: Optional section GID to place tasks in
            resend_upcycle_section_gid: Optional section GID for RESEND/UPCYCLE tasks
            ai_model: Optional Claude model to use for parsing
            assignee_gid: Optional user GID to assign all tasks to
            dry_run: If True, parse and preview but don't create tasks

        Returns:
            Dictionary with:
                - campaign_name: Name of campaign
                - total_tasks: Number of tasks attempted
                - tasks_created: Number successfully created
                - tasks_failed: Number that failed
                - results: List of individual task results
                - errors: List of errors encountered
        """
        logger.info(f"Starting brief processing: {doc_url}")
        logger.info(f"Target: Project {project_gid}, Section {section_gid}")

        results = {
            "campaign_name": "",
            "total_tasks": 0,
            "tasks_created": 0,
            "tasks_failed": 0,
            "results": [],
            "errors": []
        }

        try:
            # Step 1: Parse the brief
            logger.info("Step 1: Parsing brief with AI")
            parsed_brief = await self.brief_parser.parse_brief(doc_url, ai_model=ai_model)

            results["campaign_name"] = parsed_brief.get("campaign_name", "Untitled Campaign")
            tasks = parsed_brief.get("tasks", [])
            results["total_tasks"] = len(tasks)

            if not tasks:
                logger.warning("No tasks found in brief")
                results["errors"].append("No tasks found in the brief document")
                return results

            logger.info(f"Parsed {len(tasks)} tasks from brief")

            # If dry run, return preview
            if dry_run:
                logger.info("Dry run mode - returning preview without creating tasks")
                return self._build_preview(parsed_brief, results)

            # Step 1.5: Extract headings from Google Doc for deep linking
            logger.info("Extracting headings from Google Doc for section links")
            headings = []
            try:
                headings = self.google_docs.get_headings(doc_url)
                logger.info(f"Found {len(headings)} headings in document")
            except Exception as e:
                logger.warning(f"Could not extract headings from document: {e}")
                # Continue without headings - will use main doc URL

            # Step 2: Create each task
            for idx, task_data in enumerate(tasks, 1):
                logger.info(f"Processing task {idx}/{len(tasks)}: {task_data.get('name')}")

                # Set assignee_gid on each task if provided
                if assignee_gid:
                    task_data["assignee_gid"] = assignee_gid

                task_result = await self._create_single_task(
                    task_data,
                    project_gid,
                    section_gid,
                    idx,
                    doc_url,
                    headings,
                    resend_upcycle_section_gid
                )

                results["results"].append(task_result)

                if task_result["success"]:
                    results["tasks_created"] += 1
                else:
                    results["tasks_failed"] += 1

            logger.info(f"Brief processing complete: {results['tasks_created']} created, {results['tasks_failed']} failed")

        except Exception as e:
            logger.error(f"Error processing brief: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            results["errors"].append(f"Fatal error: {str(e)}")

        return results

    async def _create_single_task(
        self,
        task_data: Dict[str, Any],
        project_gid: str,
        section_gid: Optional[str],
        task_number: int,
        doc_url: str,
        headings: List[Dict[str, Any]] = None,
        resend_upcycle_section_gid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a single task in Asana

        Returns task result with success status and details
        """
        # Format task name with emojis, client, date, etc.
        task_name = self._format_task_name(task_data, task_number)

        # Try to find section-specific URL if headings are available
        section_url = doc_url
        if headings:
            heading_id = self.google_docs.find_heading_for_task(task_data.get('name', ''), headings)
            if heading_id:
                section_url = self.google_docs.build_heading_url(doc_url, heading_id)
                logger.info(f"Using section-specific URL for task '{task_name}': {section_url}")
            else:
                logger.debug(f"No matching heading found for task '{task_name}', using main doc URL")

        result = {
            "task_number": task_number,
            "task_name": task_name,
            "success": False,
            "asana_task_gid": None,
            "asana_task_url": None,
            "error": None
        }

        try:
            # Step 1: Build task description/notes (including Google Doc link)
            notes = self._build_task_notes(task_data, section_url)

            # Step 2: Extract and map custom fields
            custom_fields_mapped = await self._map_custom_fields(
                project_gid,
                task_data
            )

            logger.debug(f"Mapped custom fields for '{task_name}': {custom_fields_mapped}")

            # Step 3: Determine assignee (if specified)
            assignee_gid = task_data.get("assignee_gid")

            # Step 3.5: Route RESEND/UPCYCLE tasks to custom section if specified
            task_type = task_data.get("task_type", "")
            if task_type in ["RESEND", "UPCYCLE"]:
                # Use custom section if provided, otherwise use default Coordinator Design Review
                if resend_upcycle_section_gid:
                    section_gid = resend_upcycle_section_gid
                    logger.info(f"Routing {task_type} task to custom section: {section_gid}")
                else:
                    section_gid = "1206874104264011"  # Default: Coordinator Design Review
                    logger.info(f"Routing {task_type} task to default Coordinator Design Review section")
            # Otherwise use provided section_gid (defaults to Copywriter: 1206874104264005)

            # Step 4: Create the task in Asana
            # Calculate due date as 2 business days from today
            due_date = calculate_business_days_from_today(2)

            created_task = await self.asana_client.create_task(
                name=task_name,
                project_gid=project_gid,
                section_gid=section_gid,
                notes=notes,
                custom_fields=custom_fields_mapped if custom_fields_mapped else None,
                assignee_gid=assignee_gid,
                due_date=due_date
            )

            # Success!
            result["success"] = True
            result["asana_task_gid"] = created_task.get("gid")
            result["asana_task_url"] = created_task.get("permalink_url")

            # Step 5: Attach the Google Doc (with section link if available) to the task
            task_gid = created_task.get("gid")
            if task_gid:
                await self.asana_client.attach_external_resource(
                    task_id=task_gid,
                    resource_url=section_url,
                    name="Campaign Brief"
                )
                logger.debug(f"Attached Google Doc to task {task_gid}: {section_url}")

            logger.info(f"✓ Created task {task_number}: {task_name} ({result['asana_task_gid']})")

        except Exception as e:
            logger.error(f"✗ Failed to create task {task_number} '{task_name}': {e}")
            result["error"] = str(e)

        return result

    def _build_task_notes(self, task_data: Dict[str, Any], doc_url: str) -> str:
        """Build comprehensive task notes from parsed data"""

        notes_parts = []

        # Google Doc link (at the top)
        notes_parts.append(f"**Campaign Brief:** {doc_url}")

        # Subject line (for emails) - show early
        subject = task_data.get("subject")
        if subject:
            notes_parts.append(f"**Subject Line:**\n{subject}")

        # Full email body/copy - this is the main content
        copy = task_data.get("copy")
        if copy:
            notes_parts.append(f"**Email Body:**\n{copy}")

        # Copywriter Instructions with emoji
        copywriter_instructions = task_data.get("copywriter_instructions")
        if copywriter_instructions:
            notes_parts.append(f"✍️ **Copywriter Instructions:**\n{copywriter_instructions}")

        # Designer Instructions with emoji
        designer_instructions = task_data.get("designer_instructions")
        if designer_instructions:
            notes_parts.append(f"🎨 **Designer Instructions:**\n{designer_instructions}")

        # Targeted Audiences
        targeted_audiences = task_data.get("targeted_audiences")
        if targeted_audiences:
            notes_parts.append(f"🎯 **Targeted Audiences:**\n{targeted_audiences}")

        # Excluded Audiences
        excluded_audiences = task_data.get("excluded_audiences")
        if excluded_audiences:
            notes_parts.append(f"🚫 **Excluded Audiences:**\n{excluded_audiences}")

        # Description (overview/context)
        description = task_data.get("description")
        if description:
            notes_parts.append(f"**Task Details:**\n{description}")

        # Additional notes (excluding copy since we already included it)
        additional_notes = task_data.get("notes")
        if additional_notes:
            # Remove the "**Copy:**" section if it exists since we're adding copy separately
            import re
            cleaned_notes = re.sub(r'\*\*Copy:\*\*\n.*', '', additional_notes, flags=re.DOTALL).strip()
            if cleaned_notes:
                notes_parts.append(f"**Additional Notes:**\n{cleaned_notes}")

        # Combine all parts
        full_notes = "\n\n".join(notes_parts) if notes_parts else ""

        return full_notes

    def _format_task_name(self, task_data: Dict[str, Any], task_number: int) -> str:
        """
        Format task name according to specification:
        Format: "RESEND ☕📧 Chris Bean Nov [11/25] E#7 [Plain Text] BFCM: Plan Your"

        Components:
        - Task type prefix (RESEND or UPCYCLE if applicable)
        - Client emoji (☕ for Christopher Bean Coffee)
        - Message type emoji (📧 for Email, 📱 for SMS)
        - Client short name
        - Month abbreviation
        - Send date [MM/DD]
        - Message number (E#X for email, SMS#X for SMS)
        - Original task name or subject
        """
        parts = []

        # Prepend RESEND or UPCYCLE if present
        task_type = task_data.get("task_type", "")
        if task_type in ["RESEND", "UPCYCLE"]:
            parts.append(task_type)

        # Client emoji - hardcode for now, could be made configurable
        client = task_data.get("client", "")
        if "Christopher Bean" in client or "Chris Bean" in client:
            parts.append("☕")

        # Message type emoji
        message_type = task_data.get("message_type", "").lower()
        if "email" in message_type:
            parts.append("📧")
        elif "sms" in message_type:
            parts.append("📱")

        # Client short name
        if "Christopher Bean" in client or "Chris Bean" in client:
            parts.append("Chris Bean")
        elif client:
            # Use first part of client name
            parts.append(client.split()[0] if " " in client else client)

        # Month and date from send_date
        send_date_str = task_data.get("send_date")
        if send_date_str:
            try:
                send_date = datetime.strptime(send_date_str, "%Y-%m-%d")
                month_abbrev = send_date.strftime("%b")  # Nov, Dec, etc.
                date_formatted = send_date.strftime("[%m/%d]")  # [11/25]
                parts.append(month_abbrev)
                parts.append(date_formatted)
            except:
                pass

        # Message number (E#X or SMS#X)
        if "email" in message_type:
            parts.append(f"E#{task_number}")
        elif "sms" in message_type:
            parts.append(f"SMS#{task_number}")

        # Original task name or subject
        original_name = task_data.get("name", "")
        if original_name:
            # Remove prefixes like "Email 1:" or "SMS 1:" from the name
            import re
            cleaned_name = re.sub(r'^(Email|SMS)\s+\d+:\s*', '', original_name)
            if cleaned_name:
                parts.append(cleaned_name)

        return " ".join(parts) if parts else f"Task {task_number}"

    async def _map_custom_fields(
        self,
        project_gid: str,
        task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Map task data to Asana custom field GIDs using AI

        Args:
            project_gid: Asana project GID
            task_data: Parsed task data from brief

        Returns:
            Dict mapping custom field GIDs to values
        """
        # Extract relevant fields from task_data
        brief_fields = {}

        # Calculate priority based on send date (High if within 7 days, else Low)
        priority = self._calculate_priority(task_data.get("send_date"))

        # Calculate month from send date
        month = self._extract_month(task_data.get("send_date"))

        # Standard fields that might map to custom fields
        field_mappings = {
            "message_type": "Message Type",
            "client": "Client",
            "send_date": "Send Date",
            "send_time": "Send Time",
            "coupon_code": "Coupon Code",
            "coupon_name": "Coupon Name",
            "targeted_audiences": "Targeted Audiences",
            "excluded_audiences": "Excluded Audiences"
        }

        for task_key, asana_field_name in field_mappings.items():
            value = task_data.get(task_key)
            if value:
                brief_fields[asana_field_name] = value

        # Always set Content Type to "Campaign"
        brief_fields["Content Type"] = "Campaign"

        # Set calculated priority
        if priority:
            brief_fields["Priority"] = priority

        # Set calculated month
        if month:
            brief_fields["Month"] = month

        # Add any custom_fields from the brief
        extra_fields = task_data.get("custom_fields", {})
        brief_fields.update(extra_fields)

        if not brief_fields:
            logger.debug("No custom fields to map for this task")
            return {}

        # Use AI to map fields
        try:
            mapped_fields = await self.field_mapper.map_fields_with_ai(
                project_gid=project_gid,
                brief_fields=brief_fields,
                context=f"Task: {task_data.get('name')}"
            )

            # Validate the mapped fields
            validated_fields = await self.field_mapper.validate_custom_fields(
                project_gid=project_gid,
                custom_fields=mapped_fields
            )

            return validated_fields

        except Exception as e:
            logger.error(f"Error mapping custom fields: {e}")
            # Return empty dict - task will be created without custom fields
            return {}

    def _calculate_priority(self, send_date_str: Optional[str]) -> str:
        """
        Calculate priority based on send date
        - High: if send date is within next 7 days
        - Low: otherwise
        """
        if not send_date_str:
            return "Low"

        try:
            send_date = datetime.strptime(send_date_str, "%Y-%m-%d")
            today = datetime.now()
            days_until_send = (send_date - today).days

            if 0 <= days_until_send <= 7:
                return "High"
            else:
                return "Low"
        except:
            return "Low"

    def _extract_month(self, send_date_str: Optional[str]) -> Optional[str]:
        """
        Extract month name from send date
        Returns: "January", "February", etc.
        """
        if not send_date_str:
            return None

        try:
            send_date = datetime.strptime(send_date_str, "%Y-%m-%d")
            return send_date.strftime("%B")  # Full month name
        except:
            return None

    def _build_preview(
        self,
        parsed_brief: Dict[str, Any],
        results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build preview data for dry run"""

        results["preview"] = True
        results["tasks_preview"] = []

        for idx, task in enumerate(parsed_brief.get("tasks", []), 1):
            results["tasks_preview"].append({
                "number": idx,
                "name": task.get("name"),
                "message_type": task.get("message_type"),
                "priority": task.get("priority"),
                "send_date": task.get("send_date"),
                "has_subject": bool(task.get("subject")),
                "has_copy": bool(task.get("copy")),
                "custom_fields_to_map": {
                    "Message Type": task.get("message_type"),
                    "Content Type": task.get("content_type"),
                    "Priority": task.get("priority"),
                    "Client": task.get("client"),
                    "Send Date": task.get("send_date")
                }
            })

        return results

    async def verify_project_and_section(
        self,
        project_gid: str,
        section_gid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify that project and section exist and are accessible

        Returns:
            Dict with verification results
        """
        verification = {
            "project_exists": False,
            "section_exists": False,
            "project_name": None,
            "section_name": None,
            "custom_fields_count": 0,
            "errors": []
        }

        try:
            # Verify project by fetching its custom fields
            custom_fields = await self.asana_client.get_project_custom_fields(project_gid)
            verification["project_exists"] = True
            verification["custom_fields_count"] = len(custom_fields)

            # Verify section if provided
            if section_gid:
                sections = await self.asana_client.get_project_sections(project_gid)
                for section in sections:
                    if section.get("gid") == section_gid:
                        verification["section_exists"] = True
                        verification["section_name"] = section.get("name")
                        break

                if not verification["section_exists"]:
                    verification["errors"].append(f"Section {section_gid} not found in project")

        except Exception as e:
            verification["errors"].append(f"Error verifying project/section: {str(e)}")

        return verification
