"""Tests for connection discovery."""

import pytest
from domains.second_brain.types import ConnectionType
from domains.second_brain.connections import (
    DOMAIN_GROUPS,
    _get_item_domains,
    _determine_connection_type,
)


class MockKnowledgeItem:
    """Mock knowledge item for testing."""

    def __init__(self, topics: list[str] = None, title: str = "Test"):
        self.topics = topics or []
        self.title = title
        self.id = "test-id"


class TestDomainGroups:
    """Test domain grouping logic."""

    def test_domain_groups_defined(self):
        """Should have domain groups defined."""
        assert len(DOMAIN_GROUPS) > 0

    def test_tech_group_exists(self):
        """Should have a tech domain group."""
        assert "tech" in DOMAIN_GROUPS
        assert len(DOMAIN_GROUPS["tech"]) > 0

    def test_fitness_group_exists(self):
        """Should have a fitness domain group."""
        assert "fitness" in DOMAIN_GROUPS
        assert "running" in DOMAIN_GROUPS["fitness"]

    def test_business_group_exists(self):
        """Should have a business domain group."""
        assert "business" in DOMAIN_GROUPS
        assert "hadley-bricks" in DOMAIN_GROUPS["business"]


class TestGetItemDomains:
    """Test domain detection from topics."""

    def test_tech_topics(self):
        """Should detect tech domain."""
        topics = {"python", "development"}
        # development is in tech domain
        domains = _get_item_domains(topics)
        assert "tech" in domains

    def test_fitness_topics(self):
        """Should detect fitness domain."""
        topics = {"running", "marathon"}
        domains = _get_item_domains(topics)
        assert "fitness" in domains

    def test_multiple_domains(self):
        """Should detect multiple domains."""
        topics = {"running", "hadley-bricks"}
        domains = _get_item_domains(topics)
        assert "fitness" in domains
        assert "business" in domains

    def test_unknown_topics(self):
        """Should return empty for unknown topics."""
        topics = {"unknown", "random"}
        domains = _get_item_domains(topics)
        assert len(domains) == 0


class TestDetermineConnectionType:
    """Test connection type determination."""

    def test_cross_domain_detected(self):
        """Should detect cross-domain connections."""
        item_a = MockKnowledgeItem(topics=["running", "marathon"])
        item_b = MockKnowledgeItem(topics=["hadley-bricks", "ebay"])

        conn_type = _determine_connection_type(item_a, item_b)
        assert conn_type == ConnectionType.CROSS_DOMAIN

    def test_topic_overlap_detected(self):
        """Should detect topic overlap."""
        item_a = MockKnowledgeItem(topics=["running", "garmin"])
        item_b = MockKnowledgeItem(topics=["marathon", "garmin"])

        conn_type = _determine_connection_type(item_a, item_b)
        assert conn_type == ConnectionType.TOPIC_OVERLAP

    def test_semantic_fallback(self):
        """Should fall back to semantic when no special connection."""
        item_a = MockKnowledgeItem(topics=["random1"])
        item_b = MockKnowledgeItem(topics=["random2"])

        conn_type = _determine_connection_type(item_a, item_b)
        assert conn_type == ConnectionType.SEMANTIC


class TestConnectionTypes:
    """Test connection type enum."""

    def test_semantic_type_exists(self):
        """Should have semantic connection type."""
        assert ConnectionType.SEMANTIC

    def test_topic_overlap_exists(self):
        """Should have topic overlap type."""
        assert ConnectionType.TOPIC_OVERLAP

    def test_cross_domain_exists(self):
        """Should have cross-domain type."""
        assert ConnectionType.CROSS_DOMAIN
