"""Generic Claude API client with tool and vision support."""

import base64
import io
import anthropic
from typing import Any, Callable

import httpx
from PIL import Image

from logger import logger

# Max image size for Claude API (5MB, but we target 4MB to be safe)
MAX_IMAGE_BYTES = 4 * 1024 * 1024


class ClaudeClient:
    """Generic Claude API client with tool and vision support."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    async def chat(
        self,
        message: str,
        system: str,
        tools: list[dict] | None = None,
        tool_handlers: dict[str, Callable] | None = None,
        max_iterations: int = 5,
        image_urls: list[str] | None = None
    ) -> str:
        """
        Send message, handle tool calls, return final response.

        Args:
            message: User message
            system: System prompt
            tools: Tool definitions for Claude API
            tool_handlers: Map of tool_name → handler function
            max_iterations: Max tool call rounds (safety limit)
            image_urls: Optional list of image URLs to include

        Returns:
            Final text response from Claude
        """
        if tool_handlers is None:
            tool_handlers = {}

        # Build message content (text + optional images)
        content = await self._build_message_content(message, image_urls)
        messages = [{"role": "user", "content": content}]

        return await self._process_conversation(messages, system, tools, tool_handlers, max_iterations)

    async def chat_with_history(
        self,
        conversation: list[dict],
        system: str,
        tools: list[dict] | None = None,
        tool_handlers: dict[str, Callable] | None = None,
        max_iterations: int = 5
    ) -> str:
        """
        Send conversation with history, handle tool calls, return final response.

        Args:
            conversation: List of message dicts with role and content
            system: System prompt
            tools: Tool definitions for Claude API
            tool_handlers: Map of tool_name → handler function
            max_iterations: Max tool call rounds (safety limit)

        Returns:
            Final text response from Claude
        """
        if tool_handlers is None:
            tool_handlers = {}

        # Build messages array from conversation history
        messages = []
        for msg in conversation:
            content = await self._build_content_from_history(msg["content"])
            messages.append({
                "role": msg["role"],
                "content": content
            })

        # Ensure conversation starts with user message
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]

        # Ensure conversation ends with user message
        if messages and messages[-1]["role"] != "user":
            messages = messages[:-1]

        if not messages:
            return "No conversation to process."

        logger.info(f"Processing conversation with {len(messages)} messages")
        return await self._process_conversation(messages, system, tools, tool_handlers, max_iterations)

    async def _build_content_from_history(self, content: list[dict]) -> list[dict] | str:
        """Build Claude-compatible content from conversation history."""
        result = []

        for item in content:
            if item["type"] == "text":
                result.append({"type": "text", "text": item["text"]})
            elif item["type"] == "image_url":
                # Fetch and encode image
                image_data = await self._fetch_image(item["url"])
                if image_data:
                    result.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_data["media_type"],
                            "data": image_data["data"]
                        }
                    })

        # If only text, simplify to string
        if len(result) == 1 and result[0]["type"] == "text":
            return result[0]["text"]

        return result if result else ""

    async def _process_conversation(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict] | None,
        tool_handlers: dict[str, Callable],
        max_iterations: int
    ) -> str:
        """Process conversation with tool call loop."""
        for iteration in range(max_iterations):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system,
                    tools=tools if tools else None,
                    messages=messages
                )
            except anthropic.APIError as e:
                logger.error(f"Claude API error: {e}")
                raise

            # Check if we have tool use
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # No tool calls - extract text and return
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)

            # Process tool calls
            logger.info(f"Iteration {iteration + 1}: Processing {len(tool_use_blocks)} tool calls")
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_use in tool_use_blocks:
                handler = tool_handlers.get(tool_use.name)
                if handler:
                    try:
                        logger.info(f"Executing tool: {tool_use.name}")
                        result = await handler(**tool_use.input)
                    except Exception as e:
                        logger.error(f"Tool {tool_use.name} failed: {e}")
                        result = {"error": str(e)}
                else:
                    logger.warning(f"Unknown tool requested: {tool_use.name}")
                    result = {"error": f"Unknown tool: {tool_use.name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(result)
                })

            messages.append({"role": "user", "content": tool_results})

        return "I've hit my processing limit. Please try a simpler request."

    async def _build_message_content(
        self,
        message: str,
        image_urls: list[str] | None = None
    ) -> list[dict] | str:
        """Build message content with optional images."""
        if not image_urls:
            return message

        content = []

        # Add images first
        for url in image_urls:
            try:
                image_data = await self._fetch_image(url)
                if image_data:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_data["media_type"],
                            "data": image_data["data"]
                        }
                    })
                    logger.info(f"Added image to message: {url[:50]}...")
            except Exception as e:
                logger.warning(f"Failed to fetch image {url}: {e}")

        # Add text message
        content.append({
            "type": "text",
            "text": message
        })

        return content

    async def _fetch_image(self, url: str) -> dict | None:
        """Fetch image from URL, compress if needed, return base64 encoded data."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30, follow_redirects=True)
                response.raise_for_status()

                image_bytes = response.content
                original_size = len(image_bytes)
                logger.info(f"Fetched image: {original_size / 1024 / 1024:.2f}MB")

                # Always compress to ensure we're under limit and in JPEG format
                image_bytes = self._compress_image(image_bytes)
                logger.info(f"Final image size: {len(image_bytes) / 1024 / 1024:.2f}MB")

                # Encode to base64
                data = base64.standard_b64encode(image_bytes).decode("utf-8")

                return {
                    "media_type": "image/jpeg",
                    "data": data
                }

        except Exception as e:
            logger.error(f"Error fetching image: {e}")
            return None

    def _compress_image(self, image_bytes: bytes, max_dimension: int = 2048) -> bytes:
        """Compress image to fit within size limits."""
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (removes alpha channel)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Resize if too large
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"Resized image to {new_size}")

        # Compress with decreasing quality until under limit
        for quality in [85, 70, 55, 40]:
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            if buffer.tell() <= MAX_IMAGE_BYTES:
                logger.info(f"Compressed with quality={quality}")
                return buffer.getvalue()
            buffer.seek(0)

        # If still too large, resize more aggressively
        ratio = 0.7
        while True:
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=40, optimize=True)
            if buffer.tell() <= MAX_IMAGE_BYTES:
                logger.info(f"Final size after aggressive resize: {new_size}")
                return buffer.getvalue()
            ratio *= 0.7
