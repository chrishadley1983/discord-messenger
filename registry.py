"""Domain registry for channel-based routing."""

from domains.base import Domain


class DomainRegistry:
    """Central registry for all domains."""

    def __init__(self):
        self._domains: dict[int, Domain] = {}  # channel_id → domain
        self._by_name: dict[str, Domain] = {}  # name → domain

    def register(self, domain: Domain) -> None:
        """Register a domain."""
        self._domains[domain.channel_id] = domain
        self._by_name[domain.name] = domain

    def get_by_channel(self, channel_id: int) -> Domain | None:
        """Get domain for a channel."""
        return self._domains.get(channel_id)

    def get_by_name(self, name: str) -> Domain | None:
        """Get domain by name."""
        return self._by_name.get(name)

    def all_domains(self) -> list[Domain]:
        """Get all registered domains."""
        return list(self._by_name.values())


# Global registry instance
registry = DomainRegistry()
