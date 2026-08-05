"""LangGraph checkpointer factory.

Provides a DynamoDB-backed checkpointer for production (ECS Fargate) and
gracefully falls back to in-memory storage for local development when no
DynamoDB table is configured.
"""

import logging

from src.config import settings

logger = logging.getLogger(__name__)


def create_checkpointer():
    """
    Return a LangGraph checkpointer instance.

    - Production (DYNAMODB_TABLE is set): DynamoDBSaver for persistent state
      across ECS task restarts/redeployments.
    - Local dev (DYNAMODB_TABLE is empty or unset): MemorySaver for zero-config
      local testing.
    """
    if settings.DYNAMODB_TABLE:
        return _create_dynamodb_checkpointer()
    else:
        return _create_memory_checkpointer()


def _create_dynamodb_checkpointer():
    """Create a DynamoDBSaver pointed at the configured table."""
    logger.info(
        "Initializing DynamoDBSaver for table '%s' in region '%s'",
        settings.DYNAMODB_TABLE,
        settings.AWS_REGION,
    )
    try:
        from langgraph.checkpoint.dynamodb import DynamoDBSaver

        return DynamoDBSaver(
            table_name=settings.DYNAMODB_TABLE,
            region_name=settings.AWS_REGION,
        )
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-dynamodb not installed; "
            "falling back to in-memory MemorySaver."
        )
        return _create_memory_checkpointer()
    except Exception as exc:
        logger.error(
            "Failed to initialize DynamoDBSaver: %s. Falling back to MemorySaver.",
            exc,
        )
        return _create_memory_checkpointer()


def _create_memory_checkpointer():
    """Create the default in-memory checkpointer for local development."""
    logger.info("Using in-memory MemorySaver (no DYNAMODB_TABLE configured).")
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
