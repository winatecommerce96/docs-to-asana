import re
import json
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.config import settings


class GoogleDocsService:
    """Service for interacting with Google Docs API"""

    def __init__(self):
        self.credentials = self._get_credentials()
        self.service = None
        self._current_document = None
        if self.credentials:
            self.service = build('docs', 'v1', credentials=self.credentials)

    def _get_credentials(self) -> Optional[service_account.Credentials]:
        """Get Google API credentials from settings"""
        if not settings.GOOGLE_DOCS_CREDENTIALS_PATH:
            return None

        try:
            # Check if it's a file path or JSON string
            import os
            creds_path = settings.GOOGLE_DOCS_CREDENTIALS_PATH

            if os.path.isfile(creds_path):
                # Load from file path
                creds = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=['https://www.googleapis.com/auth/documents.readonly']
                )
            else:
                # Parse as JSON string (for Cloud Run / Secret Manager)
                creds_info = json.loads(creds_path)
                creds = service_account.Credentials.from_service_account_info(
                    creds_info,
                    scopes=['https://www.googleapis.com/auth/documents.readonly']
                )
            return creds
        except Exception as e:
            print(f"Failed to load Google credentials: {e}")
            return None

    def extract_doc_id(self, url: str) -> Optional[str]:
        """Extract Google Doc ID from URL"""
        # Pattern: https://docs.google.com/document/d/{DOC_ID}/edit
        match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        return None

    def get_document_content(self, doc_url: str) -> Optional[str]:
        """Retrieve text content from a Google Doc"""
        if not self.service:
            raise ValueError("Google Docs service not initialized. Check credentials.")

        doc_id = self.extract_doc_id(doc_url)
        if not doc_id:
            raise ValueError(f"Invalid Google Doc URL: {doc_url}")

        try:
            print(f"[GOOGLE_DOCS] Fetching document {doc_id}")
            document = self.service.documents().get(documentId=doc_id).execute()

            # Store document for later heading extraction
            self._current_document = document

            # Extract content
            content = self._extract_text_from_document(document)

            # Check if content is empty or too short
            if not content or len(content.strip()) == 0:
                print(f"[GOOGLE_DOCS] WARNING: Document {doc_id} is empty")
                raise ValueError(f"Google Doc is empty or contains no text content. URL: {doc_url}")

            if len(content.strip()) < 50:
                print(f"[GOOGLE_DOCS] WARNING: Document {doc_id} has very little content ({len(content.strip())} chars)")

            print(f"[GOOGLE_DOCS] Successfully extracted {len(content)} characters from document {doc_id}")
            return content

        except HttpError as e:
            error_msg = f"Failed to retrieve Google Doc {doc_id}: {e.status_code} - {e.reason}"
            if e.status_code == 403:
                error_msg += " (Permission denied - ensure the document is shared with the service account)"
            elif e.status_code == 404:
                error_msg += " (Document not found - check URL)"
            print(f"[GOOGLE_DOCS] ERROR: {error_msg}")
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error retrieving Google Doc {doc_id}: {type(e).__name__}: {str(e)}"
            print(f"[GOOGLE_DOCS] ERROR: {error_msg}")
            raise ValueError(error_msg)

    def _extract_text_from_document(self, document: dict) -> str:
        """Extract plain text and tables from Google Doc structure, formatting tables as markdown"""
        content = document.get('body', {}).get('content', [])
        text_parts = []

        for element in content:
            if 'paragraph' in element:
                # Extract paragraph text
                paragraph = element['paragraph']
                for text_element in paragraph.get('elements', []):
                    if 'textRun' in text_element:
                        text_parts.append(text_element['textRun'].get('content', ''))

            elif 'table' in element:
                # Extract and format table as markdown
                table_markdown = self._extract_table_as_markdown(element['table'])
                if table_markdown:
                    text_parts.append('\n\n' + table_markdown + '\n\n')

        return ''.join(text_parts)

    def _extract_table_as_markdown(self, table: dict) -> str:
        """Convert a Google Docs table to markdown format for better AI parsing"""
        rows = table.get('tableRows', [])
        if not rows:
            return ""

        markdown_rows = []

        for row_index, row in enumerate(rows):
            cells = row.get('tableCells', [])
            cell_contents = []

            for cell in cells:
                # Extract text from each cell
                cell_text = []
                for content_element in cell.get('content', []):
                    if 'paragraph' in content_element:
                        para = content_element['paragraph']
                        for text_elem in para.get('elements', []):
                            if 'textRun' in text_elem:
                                cell_text.append(text_elem['textRun'].get('content', ''))

                # Clean up cell text (remove newlines within cells, strip whitespace)
                cell_content = ''.join(cell_text).replace('\n', ' ').strip()
                cell_contents.append(cell_content)

            # Add the row
            markdown_rows.append('| ' + ' | '.join(cell_contents) + ' |')

            # Add separator after header row (first row)
            if row_index == 0:
                markdown_rows.append('| ' + ' | '.join(['---'] * len(cell_contents)) + ' |')

        return '\n'.join(markdown_rows)

    def is_configured(self) -> bool:
        """Check if Google Docs integration is properly configured"""
        return self.service is not None

    def get_headings(self, doc_url: str) -> list[dict]:
        """
        Extract all headings from the document with their IDs

        Returns:
            List of dicts with 'text', 'heading_id', and 'level' keys
        """
        if not self._current_document:
            # Fetch document if not already loaded
            self.get_document_content(doc_url)

        if not self._current_document:
            return []

        headings = []
        content = self._current_document.get('body', {}).get('content', [])

        for element in content:
            if 'paragraph' in element:
                paragraph = element['paragraph']

                # Check if paragraph has a heading style
                paragraph_style = paragraph.get('paragraphStyle', {})
                named_style_type = paragraph_style.get('namedStyleType', '')

                if named_style_type and 'HEADING' in named_style_type:
                    # Extract heading level (HEADING_1, HEADING_2, etc.)
                    level = named_style_type.replace('HEADING_', '')

                    # Extract text from heading
                    text_parts = []
                    for text_element in paragraph.get('elements', []):
                        if 'textRun' in text_element:
                            text_parts.append(text_element['textRun'].get('content', ''))

                    heading_text = ''.join(text_parts).strip()

                    if heading_text:
                        # Get the heading ID from the paragraph
                        heading_id = paragraph_style.get('headingId', '')

                        headings.append({
                            'text': heading_text,
                            'heading_id': heading_id,
                            'level': level
                        })

        print(f"[GOOGLE_DOCS] Found {len(headings)} headings in document")
        for h in headings:
            print(f"  - {h['level']}: {h['text'][:50]}... (ID: {h['heading_id']})")

        return headings

    def build_heading_url(self, doc_url: str, heading_id: str) -> str:
        """
        Build a URL that links directly to a specific heading in the document

        Args:
            doc_url: Base Google Doc URL
            heading_id: The heading ID to link to

        Returns:
            URL with anchor to the specific heading
        """
        doc_id = self.extract_doc_id(doc_url)
        if not doc_id:
            return doc_url

        # Google Docs heading anchor format
        if heading_id:
            return f"https://docs.google.com/document/d/{doc_id}/edit#heading={heading_id}"
        else:
            return f"https://docs.google.com/document/d/{doc_id}/edit"

    def find_heading_for_task(self, task_name: str, headings: list[dict]) -> Optional[str]:
        """
        Find the most appropriate heading ID for a given task name

        Uses fuzzy matching to find headings that match task identifiers like:
        - "Email 1", "Email 2", etc.
        - "SMS 1", "SMS 2", etc.

        Args:
            task_name: Name of the task (e.g., "Email 1: Welcome Campaign")
            headings: List of heading dictionaries from get_headings()

        Returns:
            Heading ID if found, None otherwise
        """
        if not headings:
            return None

        # Extract task identifier (e.g., "Email 1" from "Email 1: Welcome Campaign")
        import re

        # Try to extract patterns like "Email 1", "SMS 2", etc.
        match = re.match(r'^(Email|SMS|MMS)\s+(\d+)', task_name, re.IGNORECASE)

        if match:
            message_type = match.group(1).lower()
            message_number = match.group(2)

            # Look for heading that contains this identifier
            for heading in headings:
                heading_text_lower = heading['text'].lower()

                # Check if heading contains the message type and number
                if message_type in heading_text_lower and message_number in heading_text_lower:
                    print(f"[GOOGLE_DOCS] Matched task '{task_name}' to heading '{heading['text']}'")
                    return heading['heading_id']

        # Fallback: try to match by first few words of task name
        task_words = task_name.split()[:3]  # First 3 words
        for heading in headings:
            # Check if heading starts with similar words
            heading_words = heading['text'].lower().split()

            matches = sum(1 for tw in task_words if tw.lower() in heading_words)
            if matches >= 2:  # At least 2 words match
                print(f"[GOOGLE_DOCS] Matched task '{task_name}' to heading '{heading['text']}' (word match)")
                return heading['heading_id']

        print(f"[GOOGLE_DOCS] No heading found for task '{task_name}'")
        return None
