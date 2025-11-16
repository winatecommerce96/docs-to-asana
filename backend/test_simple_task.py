"""
Simple test to verify Asana task creation works
"""
import asyncio
from app.core.asana_client import AsanaClient
from app.core.config import settings
from loguru import logger


async def test_basic_task():
    """Test 1: Create a basic task with no custom fields"""
    logger.info("=" * 80)
    logger.info("TEST 1: Create basic task (no custom fields)")
    logger.info("=" * 80)

    client = AsanaClient()

    try:
        task = await client.create_task(
            name="Test Task - Basic",
            project_gid=settings.ASANA_TARGET_PROJECT_GID,
            section_gid=settings.ASANA_TARGET_SECTION_GID,
            notes="This is a basic test task with no custom fields"
        )

        logger.info(f"✓ SUCCESS: Created basic task")
        logger.info(f"  Task GID: {task.get('gid')}")
        logger.info(f"  Task URL: https://app.asana.com/0/{settings.ASANA_TARGET_PROJECT_GID}/{task.get('gid')}")
        return task

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_task_with_one_enum_field():
    """Test 2: Create task with one enum custom field (Priority)"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Create task with Priority custom field")
    logger.info("=" * 80)

    client = AsanaClient()

    # Get custom fields to find Priority field
    custom_fields = await client.get_project_custom_fields(settings.ASANA_TARGET_PROJECT_GID)

    priority_field = None
    for field in custom_fields:
        if field.get("name") == "Priority":
            priority_field = field
            break

    if not priority_field:
        logger.error("✗ Priority field not found")
        return None

    # Find "High" option
    high_option = None
    for option in priority_field.get("enum_options", []):
        if option.get("name") == "High":
            high_option = option
            break

    if not high_option:
        logger.error("✗ High priority option not found")
        return None

    logger.info(f"Priority field GID: {priority_field['gid']}")
    logger.info(f"High option GID: {high_option['gid']}")

    try:
        task = await client.create_task(
            name="Test Task - With Priority",
            project_gid=settings.ASANA_TARGET_PROJECT_GID,
            section_gid=settings.ASANA_TARGET_SECTION_GID,
            notes="This task has Priority = High",
            custom_fields={
                priority_field['gid']: high_option['gid']
            }
        )

        logger.info(f"✓ SUCCESS: Created task with Priority field")
        logger.info(f"  Task GID: {task.get('gid')}")
        logger.info(f"  Task URL: https://app.asana.com/0/{settings.ASANA_TARGET_PROJECT_GID}/{task.get('gid')}")
        return task

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_task_with_date_field():
    """Test 3: Create task with a date custom field"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Create task with Send Date custom field")
    logger.info("=" * 80)

    client = AsanaClient()

    # Get custom fields to find Send Date field
    custom_fields = await client.get_project_custom_fields(settings.ASANA_TARGET_PROJECT_GID)

    send_date_field = None
    for field in custom_fields:
        if field.get("name") == "Send Date":
            send_date_field = field
            break

    if not send_date_field:
        logger.error("✗ Send Date field not found")
        return None

    logger.info(f"Send Date field GID: {send_date_field['gid']}")
    logger.info(f"Send Date field type: {send_date_field['type']}")

    try:
        task = await client.create_task(
            name="Test Task - With Send Date",
            project_gid=settings.ASANA_TARGET_PROJECT_GID,
            section_gid=settings.ASANA_TARGET_SECTION_GID,
            notes="This task has Send Date = 2025-12-25",
            custom_fields={
                send_date_field['gid']: {"date": "2025-12-25"}
            }
        )

        logger.info(f"✓ SUCCESS: Created task with Send Date field")
        logger.info(f"  Task GID: {task.get('gid')}")
        logger.info(f"  Task URL: https://app.asana.com/0/{settings.ASANA_TARGET_PROJECT_GID}/{task.get('gid')}")
        return task

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_task_with_multiple_fields():
    """Test 4: Create task with multiple custom fields"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Create task with multiple custom fields")
    logger.info("=" * 80)

    client = AsanaClient()

    # Get all custom fields
    all_fields = await client.get_project_custom_fields(settings.ASANA_TARGET_PROJECT_GID)

    # Find the fields we want
    priority_field = None
    message_type_field = None
    send_date_field = None
    client_field = None

    for field in all_fields:
        field_type = field.get("resource_subtype") or field.get("type")

        # Skip custom_id fields
        if field_type == "custom_id":
            logger.info(f"Skipping custom_id field: {field.get('name')}")
            continue

        if field.get("name") == "Priority":
            priority_field = field
        elif field.get("name") == "Message Type":
            message_type_field = field
        elif field.get("name") == "Send Date":
            send_date_field = field
        elif field.get("name") == "Client":
            client_field = field

    custom_fields_to_set = {}

    # Add Priority = High
    if priority_field:
        for option in priority_field.get("enum_options", []):
            if option.get("name") == "High":
                custom_fields_to_set[priority_field['gid']] = option['gid']
                logger.info(f"Adding Priority = High")
                break

    # Add Message Type = Email (multi_enum)
    if message_type_field:
        for option in message_type_field.get("enum_options", []):
            if option.get("name") == "Email":
                custom_fields_to_set[message_type_field['gid']] = [option['gid']]
                logger.info(f"Adding Message Type = [Email]")
                break

    # Add Send Date
    if send_date_field:
        custom_fields_to_set[send_date_field['gid']] = {"date": "2025-12-25"}
        logger.info(f"Adding Send Date = 2025-12-25")

    # Add Client = Christopher Bean Coffee
    if client_field:
        for option in client_field.get("enum_options", []):
            if option.get("name") == "Christopher Bean Coffee":
                custom_fields_to_set[client_field['gid']] = option['gid']
                logger.info(f"Adding Client = Christopher Bean Coffee")
                break

    logger.info(f"\nTotal custom fields to set: {len(custom_fields_to_set)}")

    try:
        task = await client.create_task(
            name="Test Task - Multiple Fields",
            project_gid=settings.ASANA_TARGET_PROJECT_GID,
            section_gid=settings.ASANA_TARGET_SECTION_GID,
            notes="This task has Priority, Message Type, Send Date, and Client",
            custom_fields=custom_fields_to_set
        )

        logger.info(f"✓ SUCCESS: Created task with multiple custom fields")
        logger.info(f"  Task GID: {task.get('gid')}")
        logger.info(f"  Task URL: https://app.asana.com/0/{settings.ASANA_TARGET_PROJECT_GID}/{task.get('gid')}")
        return task

    except Exception as e:
        logger.error(f"✗ FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def main():
    """Run all tests"""
    logger.info("Starting Simple Task Creation Tests")
    logger.info(f"Project GID: {settings.ASANA_TARGET_PROJECT_GID}")
    logger.info(f"Section GID: {settings.ASANA_TARGET_SECTION_GID}")

    # Test 1: Basic task
    result1 = await test_basic_task()
    if not result1:
        logger.error("Basic task creation failed - stopping tests")
        return

    # Test 2: Task with Priority enum field
    result2 = await test_task_with_one_enum_field()
    if not result2:
        logger.error("Task with Priority field failed")

    # Test 3: Task with date field
    result3 = await test_task_with_date_field()
    if not result3:
        logger.error("Task with Send Date field failed")

    # Test 4: Task with multiple fields
    result4 = await test_task_with_multiple_fields()
    if not result4:
        logger.error("Task with multiple fields failed")

    logger.info("\n" + "=" * 80)
    logger.info("All tests complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
