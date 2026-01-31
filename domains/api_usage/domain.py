"""API Usage domain implementation."""

from domains.base import Domain, ToolDefinition, ScheduledTask
from .config import CHANNEL_ID, SYSTEM_PROMPT
from .tools import TOOLS
from .schedules import SCHEDULES


class ApiUsageDomain(Domain):
    """API usage tracking domain."""

    @property
    def name(self) -> str:
        return "api_usage"

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
