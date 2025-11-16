"""
AI-Powered Custom Field Mapper

Uses Claude to intelligently match field names from briefs to Asana custom field GIDs
"""
import json
from typing import Dict, Any, List, Optional
from loguru import logger
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.asana_client import AsanaClient


class CustomFieldMapper:
    """
    AI-powered service to map human-friendly field names to Asana custom field GIDs

    Uses Claude Sonnet to perform fuzzy matching and intelligent field value resolution
    """

    # Blacklist of field GIDs that cannot be set via API (despite appearing as settable)
    # These are read-only fields that behave like custom_id fields but report different types
    FIELD_BLACKLIST = {
        "1206622940734675",  # WIN field - read-only despite being "text" type
    }

    def __init__(self, asana_client: Optional[AsanaClient] = None):
        self.asana_client = asana_client or AsanaClient()
        self.anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.AI_MODEL or "claude-sonnet-4-20250514"

        # Cache for custom fields per project
        self._custom_fields_cache: Dict[str, List[Dict[str, Any]]] = {}

    async def get_custom_fields_for_project(self, project_gid: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get custom fields for a project (with caching)

        Args:
            project_gid: Asana project GID
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of custom field definitions
        """
        if not force_refresh and project_gid in self._custom_fields_cache:
            logger.info(f"Using cached custom fields for project {project_gid}")
            return self._custom_fields_cache[project_gid]

        # Fetch from Asana
        logger.info(f"Fetching custom fields for project {project_gid}")
        custom_fields = await self.asana_client.get_project_custom_fields(project_gid)

        # Cache the results
        self._custom_fields_cache[project_gid] = custom_fields

        return custom_fields

    async def map_fields_with_ai(
        self,
        project_gid: str,
        brief_fields: Dict[str, Any],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Use Claude AI to map brief field names to Asana custom field GIDs

        Args:
            project_gid: Asana project GID
            brief_fields: Dictionary of field names and values from the brief
                         Example: {"Message Type": "Email", "Priority": "High", "Client": "Buca di Beppo"}
            context: Optional context about the brief or campaign

        Returns:
            Dictionary mapping Asana field GIDs to their values
            Example: {"1203202007192951": "1203202007192986", "1201007787746652": "1201007787746653"}
        """
        # Get available custom fields for this project
        custom_fields = await self.get_custom_fields_for_project(project_gid)

        if not custom_fields:
            logger.warning(f"No custom fields found for project {project_gid}")
            return {}

        # Build the AI prompt
        prompt = self._build_mapping_prompt(custom_fields, brief_fields, context)

        # Call Claude
        logger.info(f"Using AI to map {len(brief_fields)} fields to Asana custom fields")

        try:
            response = await self.anthropic.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.0,  # Deterministic for field mapping
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract the JSON response
            response_text = response.content[0].text

            # Parse JSON from response
            mapped_fields = self._parse_ai_response(response_text)

            # Filter out blacklisted fields (safety net in case AI includes them)
            mapped_fields = self._filter_blacklisted_fields(mapped_fields)

            # Post-process: Format date fields correctly
            mapped_fields = self._format_date_fields(custom_fields, mapped_fields)

            logger.info(f"AI mapped {len(mapped_fields)} fields successfully")
            logger.debug(f"Mapped fields: {json.dumps(mapped_fields, indent=2)}")

            return mapped_fields

        except Exception as e:
            logger.error(f"Error using AI to map custom fields: {e}")
            # Fallback to exact name matching
            fallback_fields = self._fallback_exact_match(custom_fields, brief_fields)
            # Filter blacklisted fields from fallback
            fallback_fields = self._filter_blacklisted_fields(fallback_fields)
            # Also format date fields in fallback
            return self._format_date_fields(custom_fields, fallback_fields)

    def _build_mapping_prompt(
        self,
        custom_fields: List[Dict[str, Any]],
        brief_fields: Dict[str, Any],
        context: Optional[str] = None
    ) -> str:
        """Build the Claude prompt for field mapping"""

        # Format custom fields for the prompt
        fields_description = []
        for field in custom_fields:
            field_gid = field.get("gid")

            # SKIP custom_id fields - they cannot be set via API
            field_type = field.get("resource_subtype") or field.get("type")
            if field_type == "custom_id":
                logger.debug(f"Skipping custom_id field: {field.get('name')}")
                continue

            # SKIP blacklisted fields - read-only fields that behave like custom_id
            if field_gid in self.FIELD_BLACKLIST:
                logger.debug(f"Skipping blacklisted field: {field.get('name')} ({field_gid})")
                continue

            field_info = {
                "gid": field_gid,
                "name": field.get("name"),
                "type": field.get("type"),
            }

            # Add enum options if available
            if field.get("type") in ["enum", "multi_enum"] and field.get("enum_options"):
                field_info["options"] = [
                    {"gid": opt.get("gid"), "name": opt.get("name")}
                    for opt in field.get("enum_options", [])
                    if opt.get("enabled", True)
                ]

            fields_description.append(field_info)

        prompt = f"""You are a field mapping assistant for Asana task creation. Your job is to map field names and values from a brief document to the correct Asana custom field GIDs and option GIDs.

<asana_custom_fields>
{json.dumps(fields_description, indent=2)}
</asana_custom_fields>

<brief_fields>
{json.dumps(brief_fields, indent=2)}
</brief_fields>

{f'<context>{context}</context>' if context else ''}

Instructions:
1. For each field in brief_fields, find the best matching Asana custom field by name (fuzzy matching is OK)
2. For enum/multi_enum fields, also match the VALUE to the correct option GID
3. For text/number/date fields, keep the value as-is
4. For multi_enum fields, the value should be an array of option GIDs
5. Only include fields that you can confidently match (skip if uncertain)
6. For dates, ensure format is YYYY-MM-DD

Return ONLY a JSON object mapping Asana field GIDs to their values:

For enum fields:
{{"<field_gid>": "<option_gid>"}}

For multi_enum fields:
{{"<field_gid>": ["<option_gid_1>", "<option_gid_2>"]}}

For text/number/date fields:
{{"<field_gid>": "value"}}

Example response:
{{
  "1203202007192951": "1203202007192986",
  "1201007787746652": "1201007787746653",
  "1203424061746621": "2025-12-25",
  "1206622940734675": "WIN-12345"
}}

Respond with ONLY the JSON object, no explanations.
"""

        return prompt

    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from AI response"""
        try:
            # Try to find JSON in the response
            # Sometimes Claude wraps it in markdown code blocks
            if "```json" in response_text:
                # Extract JSON from code block
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            elif "```" in response_text:
                # Extract from generic code block
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                json_str = response_text[start:end].strip()
            else:
                # Assume the entire response is JSON
                json_str = response_text.strip()

            return json.loads(json_str)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"AI response was: {response_text}")
            return {}

    def _filter_blacklisted_fields(self, mapped_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out blacklisted field GIDs from mapped fields

        Args:
            mapped_fields: Dictionary of field GIDs to values

        Returns:
            Filtered dictionary with blacklisted fields removed
        """
        filtered = {}
        removed_count = 0

        for field_gid, value in mapped_fields.items():
            if field_gid in self.FIELD_BLACKLIST:
                logger.warning(f"Removing blacklisted field {field_gid} from mapped fields")
                removed_count += 1
            else:
                filtered[field_gid] = value

        if removed_count > 0:
            logger.info(f"Filtered out {removed_count} blacklisted field(s)")

        return filtered

    def _format_date_fields(
        self,
        custom_fields: List[Dict[str, Any]],
        mapped_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Format date field values correctly for Asana API

        Asana date fields require an object like:
        {"date_value": "YYYY-MM-DD"}

        Not just a plain string "YYYY-MM-DD"
        """
        # Create a GID -> field mapping for quick lookup
        field_by_gid = {field["gid"]: field for field in custom_fields}

        formatted = {}

        for field_gid, field_value in mapped_fields.items():
            field_def = field_by_gid.get(field_gid)

            if not field_def:
                # Field not found in definitions, keep as-is
                formatted[field_gid] = field_value
                continue

            field_type = field_def.get("type")

            # Format date fields as objects
            if field_type == "date" and isinstance(field_value, str):
                # Convert plain string to Asana date object format
                # Asana expects {"date": "YYYY-MM-DD"} not {"date_value": "YYYY-MM-DD"}
                formatted[field_gid] = {"date": field_value}
                logger.debug(f"Formatted date field {field_def.get('name')}: {field_value} -> {formatted[field_gid]}")
            else:
                # Keep other field types as-is
                formatted[field_gid] = field_value

        return formatted

    def _fallback_exact_match(
        self,
        custom_fields: List[Dict[str, Any]],
        brief_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback to exact name matching if AI fails

        This is less robust but better than nothing
        """
        logger.warning("Falling back to exact name matching for custom fields")

        mapped = {}

        # Create a name -> field mapping, excluding custom_id fields
        field_by_name = {}
        for field in custom_fields:
            # Skip custom_id fields
            field_type = field.get("resource_subtype") or field.get("type")
            if field_type == "custom_id":
                continue
            field_by_name[field["name"].lower()] = field

        for field_name, field_value in brief_fields.items():
            field_name_lower = field_name.lower()

            if field_name_lower in field_by_name:
                field = field_by_name[field_name_lower]
                field_gid = field["gid"]
                field_type = field["type"]

                # For enum fields, try to match option by name
                if field_type in ["enum", "multi_enum"]:
                    options = field.get("enum_options", [])
                    option_by_name = {
                        opt["name"].lower(): opt["gid"]
                        for opt in options
                    }

                    if isinstance(field_value, str):
                        value_lower = field_value.lower()
                        if value_lower in option_by_name:
                            mapped[field_gid] = option_by_name[value_lower]
                    elif isinstance(field_value, list):
                        # multi_enum
                        option_gids = []
                        for val in field_value:
                            val_lower = val.lower()
                            if val_lower in option_by_name:
                                option_gids.append(option_by_name[val_lower])
                        if option_gids:
                            mapped[field_gid] = option_gids
                else:
                    # Text, number, date fields - use value as-is
                    mapped[field_gid] = field_value

        logger.info(f"Fallback exact matching mapped {len(mapped)} fields")
        return mapped

    async def validate_custom_fields(
        self,
        project_gid: str,
        custom_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate that custom field GIDs and values are correct

        Args:
            project_gid: Asana project GID
            custom_fields: Dict mapping field GIDs to values

        Returns:
            Validated custom fields dict (invalid entries removed)
        """
        project_fields = await self.get_custom_fields_for_project(project_gid)

        # Build a lookup dict
        field_lookup = {field["gid"]: field for field in project_fields}

        validated = {}

        for field_gid, value in custom_fields.items():
            if field_gid not in field_lookup:
                logger.warning(f"Custom field GID {field_gid} not found in project {project_gid}, skipping")
                continue

            field = field_lookup[field_gid]
            field_type = field.get("type")

            # Validate enum values
            if field_type in ["enum", "multi_enum"]:
                valid_option_gids = {
                    opt["gid"] for opt in field.get("enum_options", [])
                    if opt.get("enabled", True)
                }

                if field_type == "enum":
                    # Single enum value
                    if value in valid_option_gids:
                        validated[field_gid] = value
                    else:
                        logger.warning(f"Invalid enum value {value} for field {field.get('name')}")
                else:
                    # Multi enum - array of values
                    if isinstance(value, list):
                        valid_values = [v for v in value if v in valid_option_gids]
                        if valid_values:
                            validated[field_gid] = valid_values
                    else:
                        logger.warning(f"Multi-enum field {field.get('name')} expects array, got {type(value)}")
            else:
                # For other types, just pass through (Asana will validate)
                validated[field_gid] = value

        return validated
