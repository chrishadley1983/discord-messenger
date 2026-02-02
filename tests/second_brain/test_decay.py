"""Tests for decay model."""

import pytest
from datetime import datetime, timedelta, timezone

from domains.second_brain.decay import (
    calculate_decay_score,
    decay_score_at_days,
    is_fading,
)
from domains.second_brain.config import DECAY_HALF_LIFE_DAYS


class TestDecayScore:
    """Test decay score calculation."""

    def test_new_item_full_score(self):
        """Item accessed now should have score near 1.0."""
        now = datetime.now(timezone.utc)
        score = calculate_decay_score(created_at=now, now=now)
        assert 0.99 <= score <= 1.0

    def test_half_life_decay(self):
        """Score should be ~0.5 after half-life period."""
        now = datetime.now(timezone.utc)
        half_life_ago = now - timedelta(days=DECAY_HALF_LIFE_DAYS)
        score = calculate_decay_score(created_at=half_life_ago, now=now)
        assert 0.45 <= score <= 0.55

    def test_double_half_life_decay(self):
        """Score should be ~0.25 after 2x half-life."""
        now = datetime.now(timezone.utc)
        double_half_life_ago = now - timedelta(days=DECAY_HALF_LIFE_DAYS * 2)
        score = calculate_decay_score(created_at=double_half_life_ago, now=now)
        assert 0.2 <= score <= 0.3

    def test_very_old_item(self):
        """Very old items should have low but non-zero score."""
        now = datetime.now(timezone.utc)
        year_ago = now - timedelta(days=365)
        score = calculate_decay_score(created_at=year_ago, now=now)
        assert 0.0 < score < 0.2


class TestPriorityScore:
    """Test priority score calculation."""

    def test_base_priority_applied(self):
        """Priority multiplier should affect score."""
        now = datetime.now(timezone.utc)

        high_priority = calculate_decay_score(
            created_at=now, access_count=0, base_priority=1.0, now=now
        )
        low_priority = calculate_decay_score(
            created_at=now, access_count=0, base_priority=0.3, now=now
        )

        assert high_priority > low_priority
        assert high_priority / low_priority == pytest.approx(1.0 / 0.3, rel=0.1)

    def test_access_boost(self):
        """More accesses should boost score."""
        now = datetime.now(timezone.utc)

        no_access = calculate_decay_score(created_at=now, access_count=0, now=now)
        some_access = calculate_decay_score(created_at=now, access_count=5, now=now)
        lots_access = calculate_decay_score(created_at=now, access_count=100, now=now)

        assert some_access > no_access
        assert lots_access > some_access

    def test_access_boost_logarithmic(self):
        """Access boost should be logarithmic (diminishing returns)."""
        now = datetime.now(timezone.utc)

        base = calculate_decay_score(created_at=now, access_count=0, now=now)
        ten = calculate_decay_score(created_at=now, access_count=10, now=now)
        hundred = calculate_decay_score(created_at=now, access_count=100, now=now)

        # Boost from 0->10 should be bigger than 10->100
        boost_0_10 = ten - base
        boost_10_100 = hundred - ten

        assert boost_0_10 > boost_10_100

    def test_combined_factors(self):
        """All factors should combine correctly."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=1)
        old = now - timedelta(days=180)

        # Recent, high access, high priority
        best = calculate_decay_score(
            created_at=recent, access_count=50, base_priority=1.0, now=now
        )

        # Old, low access, low priority
        worst = calculate_decay_score(
            created_at=old, access_count=0, base_priority=0.3, now=now
        )

        assert best > worst
        assert best / worst > 5  # Should be significantly higher


class TestHelperFunctions:
    """Test helper functions."""

    def test_decay_score_at_days(self):
        """Should predict future decay score."""
        # At day 0, score should be ~1.0
        day0 = decay_score_at_days(0)
        assert day0 == pytest.approx(1.0, rel=0.01)

        # At half-life, score should be ~0.5
        half_life = decay_score_at_days(DECAY_HALF_LIFE_DAYS)
        assert half_life == pytest.approx(0.5, rel=0.01)

    def test_is_fading(self):
        """Should detect fading items."""
        assert is_fading(0.1) is True
        assert is_fading(0.5) is False
        assert is_fading(0.3, threshold=0.3) is False
        assert is_fading(0.29, threshold=0.3) is True
