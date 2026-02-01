"""Peterbot Domain - Personal assistant with memory integration.

This domain handles non-technical conversations and integrates with
peterbot-mem for memory extraction and recall.
"""

import aiohttp
from domains.base import Domain, ToolDefinition
from domains.peterbot.config import CHANNEL_ID
from logger import logger

# Peterbot-mem worker endpoint
WORKER_PORT = 37777
MESSAGES_ENDPOINT = f"http://localhost:{WORKER_PORT}/api/sessions/messages"


SYSTEM_PROMPT = """You are a helpful personal assistant named Peter. You have a warm,
friendly personality and enjoy helping with everyday tasks, answering questions,
and having casual conversations.

Key traits:
- Friendly and approachable
- Good memory for past conversations (handled by the memory system)
- Helpful with personal organization, reminders, and general questions
- Can discuss a wide range of topics
- Keeps responses conversational and natural

You're chatting via Discord, so keep messages reasonably concise but still helpful.
Use markdown formatting when appropriate for readability."""


class PeterbotDomain(Domain):
    """Personal assistant domain with memory integration."""

    @property
    def name(self) -> str:
        return "peterbot"

    @property
    def channel_id(self) -> int:
        return CHANNEL_ID

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tools(self) -> list[ToolDefinition]:
        # No special tools for now - just conversation
        return []

    async def send_to_memory(
        self,
        content_session_id: str,
        user_message: str,
        assistant_response: str,
        channel: str = "peterbot"
    ) -> bool:
        """Send conversation exchange to peterbot-mem for memory extraction.

        Args:
            content_session_id: Unique session identifier (e.g., discord-user-123)
            user_message: The user's message
            assistant_response: The assistant's response
            channel: Channel name for categorization

        Returns:
            True if successfully queued, False otherwise
        """
        if not CHANNEL_ID:
            logger.warning("PETERBOT_CHANNEL_ID not set, skipping memory")
            return False

        # Discord edge case validation
        MAX_USER_MESSAGE = 10000  # Allow some buffer over Discord's 4000 char limit
        MAX_RESPONSE = 50000     # Assistant responses can be longer

        # Skip empty or whitespace-only messages
        if not user_message or not user_message.strip():
            logger.debug("Skipping empty user message for memory")
            return False

        # Truncate overly long messages to prevent API issues
        if len(user_message) > MAX_USER_MESSAGE:
            logger.warning(f"Truncating user message from {len(user_message)} to {MAX_USER_MESSAGE}")
            user_message = user_message[:MAX_USER_MESSAGE] + "... [truncated]"

        if assistant_response and len(assistant_response) > MAX_RESPONSE:
            logger.warning(f"Truncating response from {len(assistant_response)} to {MAX_RESPONSE}")
            assistant_response = assistant_response[:MAX_RESPONSE] + "... [truncated]"

        payload = {
            "contentSessionId": content_session_id,
            "source": "discord",
            "channel": channel,
            "userMessage": user_message,
            "assistantResponse": assistant_response,
            "metadata": {}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    MESSAGES_ENDPOINT,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 202:
                        logger.info(f"Memory queued for session {content_session_id}")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"Memory API error {resp.status}: {text}")
                        return False
        except aiohttp.ClientError as e:
            logger.error(f"Memory API connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Memory API unexpected error: {e}")
            return False
