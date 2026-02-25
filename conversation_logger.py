"""
AeroChat Conversation Logger
Async fire-and-forget logging utility for recording conversation events to Supabase via Vercel.

Usage:
    from conversation_logger import fire_log

    # Log a bot response with AI station data
    fire_log({
        "event_id": "msg_002",
        "conversation_id": "conv_001",
        "merchant_id": "merchant_breadgarden",
        "direction": "outbound",
        "source": "bot",
        "message": {"message": "Here are some chocolate cakes!", "products": [...]},
        "timestamp": "2026-02-25T10:30:04Z",
        "language": "en",
        "working_context": {"turn": 1, "topic": "chocolate_cake"},
        "memory_basket": {"customer_preference": None},
        "retrieved_docs": [...],
        "filter_response": {...},
        "model_calls": [
            {
                "step": "preprocessing_agent",
                "model": "mistral.ministral-3-14b-instruct",
                "prompt_sent": "Detect language and tag...",
                "tokens_input": 180,
                "tokens_output": 45,
                "duration_ms": 420
            },
            {
                "step": "intention_agent",
                "model": "mistral.ministral-3-14b-instruct",
                "prompt_sent": "Classify the intention...",
                "tokens_input": 245,
                "tokens_output": 12,
                "duration_ms": 380
            },
            {
                "step": "control_action_centre",
                "model": "us.meta.llama4-maverick-17b-instruct-v1:0",
                "prompt_sent": "You are a friendly shopping assistant...",
                "tokens_input": 847,
                "tokens_output": 312,
                "duration_ms": 1670
            }
        ],
        "response_time_ms": 4200
    })

Environment variables required:
    LOGGER_ENDPOINT - Vercel endpoint URL (e.g., https://your-app.vercel.app/api/log-event)
    LOGGER_API_KEY  - Shared secret for authentication
"""

import httpx
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

LOGGER_ENDPOINT = os.getenv("LOGGER_ENDPOINT")
LOGGER_API_KEY = os.getenv("LOGGER_API_KEY")


async def _log_event(event_data: dict):
    """Send event data to the logging endpoint. Internal async method."""
    if not LOGGER_ENDPOINT or not LOGGER_API_KEY:
        logger.warning("Conversation logger not configured: missing LOGGER_ENDPOINT or LOGGER_API_KEY")
        return

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                LOGGER_ENDPOINT,
                json=event_data,
                headers={"Authorization": f"Bearer {LOGGER_API_KEY}"}
            )
            if response.status_code != 200:
                logger.warning(f"Conversation logger received status {response.status_code}")
    except httpx.TimeoutException:
        logger.warning("Conversation logger timed out")
    except Exception as e:
        logger.warning(f"Conversation logger failed: {e}")


def fire_log(event_data: dict):
    """
    Non-blocking entry point for logging a conversation event.
    Call this from the main pipeline - it will never block or raise exceptions.

    Args:
        event_data: Dictionary containing event fields matching the conversation_events schema.
                    Missing fields will be stored as null in Supabase.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_log_event(event_data))
    except RuntimeError:
        # No running event loop - run in a new one
        # This path is used when called from synchronous code
        try:
            asyncio.run(_log_event(event_data))
        except Exception:
            pass
