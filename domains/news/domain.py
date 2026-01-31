"""News domain implementation."""

from domains.base import Domain, ToolDefinition, ScheduledTask
from .config import CHANNEL_ID, SYSTEM_PROMPT
from .tools import TOOLS
from .schedules import SCHEDULES


class NewsDomain(Domain):
    """News and briefings domain."""

    @property
    def name(self) -> str:
        return "news"

    @property
    def channel_id(self) -> int:
        return CHANNEL_ID

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    @property
    def tools(self) -> list[ToolDefinition]:
        return TOOLS

    @property
    def schedules(self) -> list[ScheduledTask]:
        return SCHEDULES
