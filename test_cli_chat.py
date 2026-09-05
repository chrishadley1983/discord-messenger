"""One-off live test of cli_chat against the real Hadley API + news tools."""

import asyncio

from cli_chat import chat_with_history_via_cli
from domains.news.domain import NewsDomain


async def main():
    domain = NewsDomain()
    handlers = {t.name: t.handler for t in domain.tools}
    conversation = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What are the top 2 tech headlines right now?"}
            ],
        }
    ]
    response = await chat_with_history_via_cli(
        conversation=conversation,
        system=domain.system_prompt,
        tools=domain.get_tool_definitions(),
        tool_handlers=handlers,
    )
    print("RESPONSE:", response)
    assert response, "no response from cli chat path"
    assert "tool_call" not in response, "raw tool JSON leaked to user"
    print("TEST PASS")


asyncio.run(main())
