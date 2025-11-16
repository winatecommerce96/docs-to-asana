"""
Test script for brief creation
"""
import asyncio
from app.services.task_creation_service import TaskCreationService
from app.services.brief_parser import BriefParserService
from app.core.config import settings
from loguru import logger


async def test_parse_brief():
    """Test parsing the Google Doc brief"""

    # The test Google Doc provided by user
    doc_url = "https://docs.google.com/document/d/1-fLu0GvLsUMdWxRZDbLC1zUai73SnblQfichh6yqWaI/edit?tab=t.0"

    logger.info("=" * 80)
    logger.info("TEST 1: Parse Brief from Google Doc")
    logger.info("=" * 80)

    parser = BriefParserService()

    try:
        parsed_data = await parser.parse_brief(doc_url)

        logger.info(f"✓ Successfully parsed brief")
        logger.info(f"Campaign Name: {parsed_data.get('campaign_name')}")
        logger.info(f"Description: {parsed_data.get('campaign_description')}")
        logger.info(f"Total Tasks: {len(parsed_data.get('tasks', []))}")

        # Print task summary
        for idx, task in enumerate(parsed_data.get("tasks", []), 1):
            logger.info(f"\nTask {idx}:")
            logger.info(f"  Name: {task.get('name')}")
            logger.info(f"  Type: {task.get('message_type')}")
            logger.info(f"  Priority: {task.get('priority')}")
            logger.info(f"  Send Date: {task.get('send_date')}")
            logger.info(f"  Client: {task.get('client')}")

        return parsed_data

    except Exception as e:
        logger.error(f"✗ Failed to parse brief: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_verify_project():
    """Test verifying the Asana project and section"""

    project_gid = "1206874746809992"  # Team 4 Campaigns
    section_gid = "1206874104264005"  # ✏️ Copywriter

    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Verify Asana Project and Section")
    logger.info("=" * 80)

    service = TaskCreationService()

    try:
        verification = await service.verify_project_and_section(
            project_gid=project_gid,
            section_gid=section_gid
        )

        logger.info(f"✓ Project exists: {verification['project_exists']}")
        logger.info(f"✓ Section exists: {verification['section_exists']}")
        logger.info(f"  Section name: {verification.get('section_name')}")
        logger.info(f"  Custom fields count: {verification.get('custom_fields_count')}")

        if verification.get("errors"):
            for error in verification["errors"]:
                logger.error(f"  Error: {error}")

        return verification

    except Exception as e:
        logger.error(f"✗ Failed to verify project: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_dry_run():
    """Test dry run mode - parse but don't create tasks"""

    doc_url = "https://docs.google.com/document/d/1-fLu0GvLsUMdWxRZDbLC1zUai73SnblQfichh6yqWaI/edit?tab=t.0"
    project_gid = "1206874746809992"
    section_gid = "1206874104264005"

    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Dry Run - Preview Tasks (No Creation)")
    logger.info("=" * 80)

    service = TaskCreationService()

    try:
        results = await service.create_tasks_from_brief(
            doc_url=doc_url,
            project_gid=project_gid,
            section_gid=section_gid,
            dry_run=True  # Preview only
        )

        logger.info(f"✓ Dry run complete")
        logger.info(f"Campaign: {results.get('campaign_name')}")
        logger.info(f"Total tasks to create: {results.get('total_tasks')}")

        if results.get('tasks_preview'):
            logger.info("\nTasks Preview:")
            for task in results['tasks_preview']:
                logger.info(f"\n  Task {task['number']}: {task['name']}")
                logger.info(f"    Type: {task.get('message_type')}")
                logger.info(f"    Priority: {task.get('priority')}")
                logger.info(f"    Send Date: {task.get('send_date')}")

        return results

    except Exception as e:
        logger.error(f"✗ Dry run failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def test_create_tasks():
    """ACTUAL task creation - only run if you want to create real tasks!"""

    doc_url = "https://docs.google.com/document/d/1-fLu0GvLsUMdWxRZDbLC1zUai73SnblQfichh6yqWaI/edit?tab=t.0"
    project_gid = "1206874746809992"
    section_gid = "1206874104264005"

    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: CREATE TASKS IN ASANA (REAL)")
    logger.info("=" * 80)

    # Confirm
    logger.warning("⚠️  This will create REAL tasks in Asana!")
    logger.warning("⚠️  Comment out this test if you don't want to create tasks yet")

    service = TaskCreationService()

    try:
        results = await service.create_tasks_from_brief(
            doc_url=doc_url,
            project_gid=project_gid,
            section_gid=section_gid,
            dry_run=False  # ACTUALLY CREATE TASKS
        )

        logger.info(f"✓ Task creation complete")
        logger.info(f"Campaign: {results.get('campaign_name')}")
        logger.info(f"Tasks created: {results.get('tasks_created')}/{results.get('total_tasks')}")
        logger.info(f"Tasks failed: {results.get('tasks_failed')}")

        logger.info("\nResults:")
        for result in results.get('results', []):
            if result['success']:
                logger.info(f"  ✓ {result['task_name']}")
                logger.info(f"    Asana GID: {result['asana_task_gid']}")
                logger.info(f"    URL: {result['asana_task_url']}")
            else:
                logger.error(f"  ✗ {result['task_name']}")
                logger.error(f"    Error: {result.get('error')}")

        return results

    except Exception as e:
        logger.error(f"✗ Task creation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def main():
    """Run all tests"""

    logger.info("Starting Asana Brief Creation Tests")
    logger.info(f"AI Model: {settings.AI_MODEL}")
    logger.info(f"Workspace ID: {settings.ASANA_WORKSPACE_ID}")

    # Test 1: Parse the brief
    parsed_data = await test_parse_brief()
    if not parsed_data:
        logger.error("Brief parsing failed, stopping tests")
        return

    # Test 2: Verify project/section
    verification = await test_verify_project()
    if not verification or not verification.get('project_exists'):
        logger.error("Project verification failed, stopping tests")
        return

    # Test 3: Dry run
    dry_run_results = await test_dry_run()
    if not dry_run_results:
        logger.error("Dry run failed, stopping tests")
        return

    # Test 4: ACTUAL TASK CREATION
    # COMMENT THIS OUT if you just want to test parsing
    logger.info("\n" + "=" * 80)
    logger.info("Skipping actual task creation (uncomment to enable)")
    logger.info("To create real tasks, uncomment the test_create_tasks() call below")
    logger.info("=" * 80)

    # Uncomment below to create REAL tasks:
    await test_create_tasks()

    logger.info("\n" + "=" * 80)
    logger.info("All tests complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
