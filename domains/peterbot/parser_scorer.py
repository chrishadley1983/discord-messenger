"""Parser Scorer - 6-dimension scoring rubric for parser quality.

Scores parser output against expected output using:
1. Content Preservation (0.30) - No content loss
2. ANSI Cleanliness (0.20) - No ANSI escape sequences
3. Echo Removal (0.15) - No instruction text leakage
4. Format Integrity (0.15) - Markdown formatting intact
5. Length Compliance (0.10) - Discord limits respected
6. Noise Removal (0.10) - Spinners and tool noise stripped

Pass threshold: >= 0.90 overall score

Based on SELF_IMPROVING_PARSER.md Phase 2.
"""

import re
from dataclasses import dataclass

# ANSI escape sequence pattern
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# Spinner/noise patterns
SPINNER_PATTERNS = [
    re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'),       # Braille spinners
    re.compile(r'[\|/\-\\](?:\s|$)'),           # Classic spinners at line boundaries
    re.compile(r'\.{3,}'),                       # Loading dots (3+)
    re.compile(r'[✻✓✗⏵✶▘]'),                  # Status indicators
]

# Dimension weights
WEIGHTS = {
    'content_preservation': 0.30,
    'ansi_cleanliness': 0.20,
    'echo_removal': 0.15,
    'format_integrity': 0.15,
    'length_compliance': 0.10,
    'noise_removal': 0.10,
}

# Pass threshold
PASS_THRESHOLD = 0.90


@dataclass
class ScoreResult:
    """Result of scoring parser output."""
    content_preservation: float
    ansi_cleanliness: float
    echo_removal: float
    format_integrity: float
    length_compliance: float
    noise_removal: float

    @property
    def overall(self) -> float:
        """Weighted overall score."""
        return sum(
            getattr(self, dim) * w
            for dim, w in WEIGHTS.items()
        )

    @property
    def passed(self) -> bool:
        """Did this score pass the threshold?"""
        return self.overall >= PASS_THRESHOLD

    @property
    def failures(self) -> list[str]:
        """Which dimensions scored below 0.8?"""
        dims = list(WEIGHTS.keys())
        return [d for d in dims if getattr(self, d) < 0.8]

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'content_preservation': self.content_preservation,
            'ansi_cleanliness': self.ansi_cleanliness,
            'echo_removal': self.echo_removal,
            'format_integrity': self.format_integrity,
            'length_compliance': self.length_compliance,
            'noise_removal': self.noise_removal,
            'overall': self.overall,
            'passed': self.passed,
            'failures': self.failures,
        }


class ParserScorer:
    """Scores parser output against expected output using the rubric."""

    def score(
        self,
        raw_capture: str,
        expected_output: str,
        actual_output: str,
        screen_before: str | None = None
    ) -> ScoreResult:
        """Score parser output against expected.

        Args:
            raw_capture: Original raw tmux capture
            expected_output: What the parser should produce
            actual_output: What the parser actually produced
            screen_before: Screen state before message (for echo detection)

        Returns:
            ScoreResult with all dimension scores
        """
        return ScoreResult(
            content_preservation=self._score_content(expected_output, actual_output),
            ansi_cleanliness=self._score_ansi(actual_output),
            echo_removal=self._score_echo(screen_before, actual_output),
            format_integrity=self._score_format(expected_output, actual_output),
            length_compliance=self._score_length(actual_output),
            noise_removal=self._score_noise(actual_output),
        )

    def _score_content(self, expected: str, actual: str) -> float:
        """Measure content preservation using normalized token overlap.

        Uses F2-score (recall-weighted) because content loss is worse than extra noise.
        """
        if not expected.strip():
            # Empty expected output — actual should also be empty
            return 1.0 if not actual.strip() else 0.5

        expected_tokens = set(self._tokenize(expected))
        actual_tokens = set(self._tokenize(actual))

        if not expected_tokens:
            return 1.0

        # Recall: what fraction of expected tokens appear in actual?
        recall = len(expected_tokens & actual_tokens) / len(expected_tokens)

        # Precision: penalize lightly for extra tokens (some noise acceptable)
        precision = (
            len(expected_tokens & actual_tokens) / len(actual_tokens)
            if actual_tokens else 0.0
        )

        # F2-score (recall-weighted) - content loss is worse than noise
        if recall + precision == 0:
            return 0.0

        beta = 2.0  # Recall-weighted
        return ((1 + beta**2) * precision * recall) / (beta**2 * precision + recall)

    def _score_ansi(self, actual: str) -> float:
        """Binary: 1.0 if no ANSI, 0.0 if any present."""
        return 0.0 if ANSI_PATTERN.search(actual or "") else 1.0

    def _score_echo(self, screen_before: str | None, actual: str) -> float:
        """Check if user instruction leaked into output."""
        if not screen_before or not actual:
            return 1.0

        # Extract likely user input lines from screen_before
        lines = screen_before.strip().split('\n')
        user_lines = []

        for line in lines[-5:]:
            stripped = line.strip()
            # Look for prompt markers
            if stripped.startswith('>') or stripped.startswith('❯'):
                content = stripped.lstrip('>❯').strip()
                if len(content) > 15:
                    user_lines.append(content)

        # Check if any user input appears in the output
        for line in user_lines:
            if line in actual:
                return 0.0

        return 1.0

    def _score_format(self, expected: str, actual: str) -> float:
        """Check markdown formatting survived parsing."""
        score = 1.0
        penalties = []

        # Code block balance
        expected_fences = expected.count('```')
        actual_fences = actual.count('```')

        if expected_fences > 0 and actual_fences != expected_fences:
            penalties.append(0.3)

        # Unclosed code blocks (odd number of fences)
        if actual_fences % 2 != 0:
            penalties.append(0.4)

        # Table pipe alignment (rough check)
        expected_tables = expected.count('|')
        actual_tables = actual.count('|')

        if expected_tables > 4 and actual_tables < expected_tables * 0.5:
            penalties.append(0.3)

        # Bold/italic markers
        expected_bold = expected.count('**')
        actual_bold = actual.count('**')

        if expected_bold > 0 and actual_bold < expected_bold * 0.5:
            penalties.append(0.2)

        # List markers
        expected_lists = len(re.findall(r'^[\s]*[-*•]\s', expected, re.MULTILINE))
        actual_lists = len(re.findall(r'^[\s]*[-*•]\s', actual, re.MULTILINE))

        if expected_lists > 2 and actual_lists < expected_lists * 0.5:
            penalties.append(0.2)

        return max(0.0, score - sum(penalties))

    def _score_length(self, actual: str) -> float:
        """Check Discord message limit compliance."""
        if not actual:
            return 1.0

        if len(actual) <= 2000:
            return 1.0

        # Over limit — should have been split
        overage = len(actual) - 2000

        # Gradual penalty
        return max(0.0, 1.0 - (overage / 2000))

    def _score_noise(self, actual: str) -> float:
        """Check for spinner frames, tool noise, thinking indicators."""
        if not actual:
            return 1.0

        noise_count = 0

        for pattern in SPINNER_PATTERNS:
            noise_count += len(pattern.findall(actual))

        # Thinking block indicators
        if '<antThinking>' in actual or '</antThinking>' in actual:
            noise_count += 5

        # Tool invocation noise
        if 'tool_use' in actual and 'content_block' in actual:
            noise_count += 3

        # Claude Code specific noise
        if 'Total tokens:' in actual:
            noise_count += 2

        if noise_count == 0:
            return 1.0

        return max(0.0, 1.0 - (noise_count * 0.1))

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace tokenization with normalization."""
        # Strip ANSI codes first
        text = ANSI_PATTERN.sub('', text or '')
        text = text.lower().strip()

        # Split on whitespace, filter short tokens
        return [t for t in text.split() if len(t) > 2]


# Module-level singleton
_scorer: ParserScorer | None = None


def get_parser_scorer() -> ParserScorer:
    """Get the singleton parser scorer."""
    global _scorer
    if _scorer is None:
        _scorer = ParserScorer()
    return _scorer


def score_output(
    raw_capture: str,
    expected_output: str,
    actual_output: str,
    screen_before: str | None = None
) -> ScoreResult:
    """Convenience function to score parser output."""
    return get_parser_scorer().score(
        raw_capture=raw_capture,
        expected_output=expected_output,
        actual_output=actual_output,
        screen_before=screen_before
    )
