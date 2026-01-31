"""Base domain class and supporting types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler


@dataclass
class ToolDefinition:
    """Claude API tool definition + handler."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]

    def to_api_format(self) -> dict:
        """Convert to Claude API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }


@dataclass
class ScheduledTask:
    """Cron-style scheduled task."""

    name: str
    handler: Callable
    hour: int
    minute: int = 0
    day_of_week: str = "*"  # "*" = daily, "mon-fri" = weekdays, etc.
    timezone: str = "UTC"


class Domain(ABC):
    """Base class for all domains."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Domain identifier."""
        pass

    @property
    @abstractmethod
    def channel_id(self) -> int:
        """Discord channel this domain handles."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Claude system prompt for this domain."""
        pass

    @property
    @abstractmethod
    def tools(self) -> list[ToolDefinition]:
        """Available tools for this domain."""
        pass

    @property
    def schedules(self) -> list[ScheduledTask]:
        """Scheduled tasks (optional, default empty)."""
        return []

    def get_tool_definitions(self) -> list[dict]:
        """Format tools for Claude API."""
        return [t.to_api_format() for t in self.tools]

    def get_tool_handler(self, name: str) -> Callable | None:
        """Get handler function by tool name."""
        for tool in self.tools:
            if tool.name == name:
                return tool.handler
        return None

    def register_schedules(self, scheduler: AsyncIOScheduler, bot) -> None:
        """Register all scheduled tasks with the scheduler."""
        for task in self.schedules:
            scheduler.add_job(
                task.handler,
                'cron',
                args=[bot, self],
                hour=task.hour,
                minute=task.minute,
                day_of_week=task.day_of_week,
                timezone=task.timezone,
                id=f"{self.name}_{task.name}"
            )
