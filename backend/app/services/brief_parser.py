"""
Brief Parser Service

Parses Google Docs briefs and uses Claude AI to extract structured task data
"""
import json
from typing import Dict, Any, List, Optional
from loguru import logger
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.services.google_docs import GoogleDocsService


class BriefParserService:
    """
    Service to parse campaign briefs from Google Docs and extract task definitions

    Uses Claude Sonnet to intelligently parse unstructured brief content into
    structured task data with custom fields
    """

    def __init__(self):
        self.google_docs = GoogleDocsService()
        self.anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.AI_MODEL or "claude-sonnet-4-20250514"

    async def parse_brief(
        self,
        doc_url: str,
        parsing_instructions: Optional[str] = None,
        ai_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse a Google Doc brief and extract task definitions

        Args:
            doc_url: Google Doc URL
            parsing_instructions: Optional custom instructions for parsing
            ai_model: Optional Claude model to use (e.g., 'claude-haiku-4-5-20251001')

        Returns:
            Dictionary with:
                - campaign_name: Name of the campaign
                - campaign_description: Description/overview
                - tasks: List of task dictionaries
                - metadata: Additional extracted information
        """
        # Step 1: Fetch document content
        logger.info(f"Fetching Google Doc: {doc_url}")
        doc_content = self.google_docs.get_document_content(doc_url)

        if not doc_content:
            raise ValueError(f"Failed to fetch or parse Google Doc: {doc_url}")

        logger.info(f"Retrieved {len(doc_content)} characters from Google Doc")

        # Step 2: Use Claude to parse the content
        logger.info("Parsing brief content with Claude AI")
        parsed_data = await self._parse_with_ai(doc_content, parsing_instructions, ai_model)

        # Step 3: Validate and clean parsed data
        validated_data = self._validate_parsed_data(parsed_data)

        logger.info(f"Successfully parsed brief with {len(validated_data.get('tasks', []))} tasks")

        return validated_data

    async def _parse_with_ai(
        self,
        doc_content: str,
        parsing_instructions: Optional[str] = None,
        ai_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Use Claude to parse the brief content into structured task data"""

        prompt = self._build_parsing_prompt(doc_content, parsing_instructions)

        # Use provided model or fall back to default
        model = ai_model or self.model
        logger.info(f"Using AI model: {model}")

        try:
            response = await self.anthropic.messages.create(
                model=model,
                max_tokens=16000,  # Increased to handle large campaigns with many tasks
                temperature=0.1,  # Low temperature for consistent parsing
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract the response text
            response_text = response.content[0].text

            # Parse JSON from response
            parsed_data = self._extract_json_from_response(response_text)

            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing brief with AI: {e}")
            raise

    def _build_parsing_prompt(
        self,
        doc_content: str,
        parsing_instructions: Optional[str] = None
    ) -> str:
        """Build the Claude prompt for parsing the brief"""

        default_instructions = """Extract all task-related information including:
- Email campaigns (subject lines, content, send dates)
- SMS/MMS messages
- Design tasks
- Any other deliverables mentioned"""

        instructions = parsing_instructions or default_instructions

        prompt = f"""You are parsing a marketing campaign brief document to extract structured task data for Asana project management.

<brief_document>
{doc_content}
</brief_document>

<parsing_instructions>
{instructions}
</parsing_instructions>

Your task is to extract:
1. **Campaign Overview**: Name, description, goals, target audience
2. **Tasks**: Individual deliverables that should become Asana tasks

For each task, extract:
- **name**: Clear, concise task name (e.g., "Email 1: Welcome Series")
- **description**: Detailed description of what needs to be done
- **message_type**: Type of deliverable (Email, SMS, MMS, Social, Banner, etc.)
- **task_type**: Special task type if mentioned (RESEND, UPCYCLE, or empty if neither)
- **client**: Client name if mentioned
- **send_date**: Send/launch date if specified (format: YYYY-MM-DD)
- **send_time**: Send time if specified (e.g., "7:03 PM EST", "9:00 AM PST")
- **subject**: Subject line for emails
- **copy**: The actual copy/content if provided
- **copywriter_instructions**: Specific instructions for the copywriter
- **designer_instructions**: Specific instructions for the designer
- **notes**: Any additional context or requirements
- **coupon_code**: The actual coupon code if mentioned (e.g., "BFCM25", "SAVE20")
- **coupon_name**: Description of what the coupon does (e.g., "25% off Black Friday sale")
- **targeted_audiences**: Target audience segments (e.g., "WIN | US only - Combined lists", "All Active Subscribers")
- **excluded_audiences**: Audience segments to exclude if mentioned
- **custom_fields**: Any other relevant fields mentioned

Return your response as a JSON object with this structure:

{{
  "campaign_name": "Campaign name from the brief",
  "campaign_description": "Overview of the campaign",
  "campaign_goals": "Goals if mentioned",
  "target_audience": "Target audience if mentioned",
  "tasks": [
    {{
      "name": "Task name",
      "description": "What needs to be done",
      "message_type": "Email|SMS|MMS|Social|Banner|etc",
      "task_type": "RESEND|UPCYCLE|",
      "client": "Client name",
      "send_date": "YYYY-MM-DD",
      "send_time": "7:03 PM EST",
      "subject": "Email subject line",
      "copy": "The actual copy/content",
      "copywriter_instructions": "Specific instructions for the copywriter",
      "designer_instructions": "Specific instructions for the designer",
      "notes": "Additional context",
      "coupon_code": "ACTUAL_CODE",
      "coupon_name": "Description of discount",
      "targeted_audiences": "Target segments",
      "excluded_audiences": "Excluded segments",
      "custom_fields": {{
        "Other Field": "VALUE"
      }}
    }}
  ],
  "metadata": {{
    "campaign_duration": "Duration if mentioned",
    "budget": "Budget if mentioned",
    "any_other_relevant_info": "value"
  }}
}}

Guidelines:
- Be thorough - extract ALL tasks mentioned in the brief
- Use consistent naming: "Email 1: [Subject]", "SMS 1: [Topic]", etc.
- For dates, always use YYYY-MM-DD format
- Extract coupon codes and their descriptions separately
- Extract targeted and excluded audience segments if mentioned
- If content/copy is in a table, extract each row as a separate task
- Preserve all important details in the description and notes fields
- The description should contain all relevant task details from the source document

CRITICAL INSTRUCTIONS:
- You MUST extract ALL tasks from the brief - do not stop early or truncate the list
- Ensure the JSON is valid and complete - close all brackets and quotes properly
- If the brief has 20+ tasks, make sure ALL of them are in the "tasks" array
- Return ONLY the JSON object, no explanations or markdown formatting
- The JSON must be syntactically valid - check that all strings are properly closed
"""

        return prompt

    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """Extract and parse JSON from AI response with robust fallback handling"""
        try:
            # Try to find JSON in the response
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text.strip()

            parsed = json.loads(json_str)
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.warning("Attempting fallback extraction from malformed JSON...")

            # Try more aggressive fallback - extract what we can from the partial JSON
            try:
                # Find the tasks array in the malformed JSON
                tasks_extracted = self._extract_tasks_from_malformed_json(response_text)
                campaign_info = self._extract_campaign_info_from_malformed_json(response_text)

                if tasks_extracted:
                    logger.info(f"Fallback extraction successful: {len(tasks_extracted)} tasks recovered")
                    return {
                        "campaign_name": campaign_info.get("campaign_name", "Recovered Campaign"),
                        "campaign_description": campaign_info.get("campaign_description", ""),
                        "campaign_goals": campaign_info.get("campaign_goals", ""),
                        "target_audience": campaign_info.get("target_audience", ""),
                        "tasks": tasks_extracted,
                        "metadata": {"extraction_method": "fallback"}
                    }
            except Exception as fallback_error:
                logger.error(f"Fallback extraction also failed: {fallback_error}")

            # Final fallback: return minimal structure
            logger.error("All extraction attempts failed, returning empty task list")
            return {
                "campaign_name": "Untitled Campaign",
                "tasks": [],
                "error": f"Failed to parse AI response: {str(e)}"
            }

    def _extract_tasks_from_malformed_json(self, text: str) -> List[Dict[str, Any]]:
        """Extract task objects from malformed JSON by finding task boundaries"""
        import re

        tasks = []

        # Find all task-like objects in the JSON
        # Look for patterns like: {"name": "...", "description": "...", ...}
        # Start from "tasks": [ and extract individual task objects

        tasks_match = re.search(r'"tasks"\s*:\s*\[', text)
        if not tasks_match:
            return []

        # Start after "tasks": [
        start_pos = tasks_match.end()

        # Find task objects by looking for { ... } patterns
        depth = 0
        task_start = None
        i = start_pos

        while i < len(text):
            char = text[i]

            if char == '{':
                if depth == 0:
                    task_start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and task_start is not None:
                    # Found a complete task object
                    task_json = text[task_start:i+1]
                    try:
                        task_obj = json.loads(task_json)
                        if isinstance(task_obj, dict) and 'name' in task_obj:
                            tasks.append(task_obj)
                    except:
                        pass  # Skip malformed task objects
                    task_start = None
            elif char == ']' and depth == 0:
                # End of tasks array
                break

            i += 1

        return tasks

    def _extract_campaign_info_from_malformed_json(self, text: str) -> Dict[str, str]:
        """Extract campaign metadata from malformed JSON"""
        import re

        info = {}

        # Extract campaign_name
        name_match = re.search(r'"campaign_name"\s*:\s*"([^"]+)"', text)
        if name_match:
            info["campaign_name"] = name_match.group(1)

        # Extract campaign_description
        desc_match = re.search(r'"campaign_description"\s*:\s*"([^"]+)"', text)
        if desc_match:
            info["campaign_description"] = desc_match.group(1)

        # Extract campaign_goals
        goals_match = re.search(r'"campaign_goals"\s*:\s*"([^"]+)"', text)
        if goals_match:
            info["campaign_goals"] = goals_match.group(1)

        # Extract target_audience
        audience_match = re.search(r'"target_audience"\s*:\s*"([^"]+)"', text)
        if audience_match:
            info["target_audience"] = audience_match.group(1)

        return info

    def _validate_parsed_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and clean the parsed data

        Ensures required fields are present and data is well-formatted
        """
        # Ensure top-level fields exist
        validated = {
            "campaign_name": parsed_data.get("campaign_name", "Untitled Campaign"),
            "campaign_description": parsed_data.get("campaign_description", ""),
            "campaign_goals": parsed_data.get("campaign_goals", ""),
            "target_audience": parsed_data.get("target_audience", ""),
            "tasks": [],
            "metadata": parsed_data.get("metadata", {})
        }

        # Validate each task
        for idx, task in enumerate(parsed_data.get("tasks", []), 1):
            validated_task = self._validate_task(task, idx)
            if validated_task:
                validated["tasks"].append(validated_task)

        return validated

    def _validate_task(self, task: Dict[str, Any], task_number: int) -> Optional[Dict[str, Any]]:
        """Validate a single task and ensure required fields"""

        # Must have a name
        if not task.get("name"):
            logger.warning(f"Task {task_number} has no name, skipping")
            return None

        # Build validated task
        validated = {
            "name": task.get("name", f"Task {task_number}"),
            "description": task.get("description", ""),
            "message_type": task.get("message_type", ""),
            "task_type": task.get("task_type", ""),  # RESEND, UPCYCLE, or empty
            "client": task.get("client", ""),
            "send_date": self._validate_date(task.get("send_date")),
            "send_time": task.get("send_time", ""),
            "subject": task.get("subject", ""),
            "copy": task.get("copy", ""),
            "copywriter_instructions": task.get("copywriter_instructions", ""),
            "designer_instructions": task.get("designer_instructions", ""),
            "notes": task.get("notes", ""),
            "coupon_code": task.get("coupon_code", ""),
            "coupon_name": task.get("coupon_name", ""),
            "targeted_audiences": task.get("targeted_audiences", ""),
            "excluded_audiences": task.get("excluded_audiences", ""),
            "custom_fields": task.get("custom_fields", {})
        }

        # Combine copy into notes if both exist
        if validated["copy"]:
            if validated["notes"]:
                validated["notes"] += f"\n\n**Copy:**\n{validated['copy']}"
            else:
                validated["notes"] = f"**Copy:**\n{validated['copy']}"

        return validated

    def _validate_date(self, date_str: Optional[str]) -> Optional[str]:
        """Validate date format (YYYY-MM-DD)"""
        if not date_str:
            return None

        # Very basic validation - just check format
        import re
        if re.match(r'\d{4}-\d{2}-\d{2}', str(date_str)):
            return str(date_str)

        logger.warning(f"Invalid date format: {date_str}, expected YYYY-MM-DD")
        return None

    async def preview_brief(self, doc_url: str) -> Dict[str, Any]:
        """
        Preview what tasks would be created from a brief without actually creating them

        Args:
            doc_url: Google Doc URL

        Returns:
            Preview data with tasks and summary
        """
        parsed_data = await self.parse_brief(doc_url)

        preview = {
            "campaign_name": parsed_data.get("campaign_name"),
            "campaign_description": parsed_data.get("campaign_description"),
            "total_tasks": len(parsed_data.get("tasks", [])),
            "tasks_summary": []
        }

        for task in parsed_data.get("tasks", []):
            preview["tasks_summary"].append({
                "name": task.get("name"),
                "message_type": task.get("message_type"),
                "send_date": task.get("send_date"),
                "has_copy": bool(task.get("copy"))
            })

        return preview
