"""Classify conversation chunks for routing.

Routes chunks to:
- SKIP: Ephemeral content (debugging, code generation, small talk)
- PREFERENCE: Preferences, decisions, personal facts
- SECOND_BRAIN: Knowledge, research, explanations, how-to

Both PREFERENCE and SECOND_BRAIN are imported into Second Brain.
Only SKIP chunks are discarded.
"""

import re
from dataclasses import dataclass
from enum import Enum

from .chunker import ConversationChunk


class Route(Enum):
    SKIP = "skip"
    PREFERENCE = "preference"
    SECOND_BRAIN = "second_brain"


@dataclass
class ClassificationResult:
    chunk: ConversationChunk
    route: Route
    confidence: float
    reason: str


# Signals for preference/decision detection (→ Second Brain (preference))
PREFERENCE_SIGNALS = [
    r"\bi prefer\b", r"\bi always\b", r"\bi never\b", r"\bi like\b",
    r"\bi don't like\b", r"\bi want\b", r"\bmy favourite\b", r"\bmy favorite\b",
    r"\bi usually\b", r"\bmy workflow\b", r"\bmy process\b",
    r"\bmy style\b", r"\bi decided\b", r"\blet's go with\b",
    r"\bi'll use\b", r"\bmy routine\b", r"\bmy approach\b",
    r"\bmy birthday\b", r"\bmy wife\b", r"\bmy son\b", r"\bmy daughter\b",
    r"\bi live\b", r"\bmy address\b", r"\bmy name is\b",
    r"\bi'm from\b", r"\bi work at\b", r"\bmy job\b",
]

# Signals for ephemeral content (→ skip)
EPHEMERAL_SIGNALS = [
    r"\bfix this error\b", r"\bdebug\b", r"\bstack trace\b",
    r"\bsyntax error\b", r"\bbuild error\b", r"\bcompile error\b",
    r"\btraceback\b", r"\bundefined\b", r"\bnull pointer\b",
    r"\btype error\b", r"\bname error\b",
]

# Signals for knowledge content (→ second brain)
KNOWLEDGE_SIGNALS = [
    r"\bhow (?:do|does|to|can)\b", r"\bwhat is\b", r"\bexplain\b",
    r"\bresearch\b", r"\bcompare\b", r"\banalysis\b", r"\banalyz\b",
    r"\bstrategy\b", r"\bbest practice\b", r"\brecommend\b",
    r"\bguide\b", r"\btutorial\b", r"\brecipe\b",
    r"\bnutrition\b", r"\btraining plan\b", r"\bbusiness\b",
    r"\bmarketing\b", r"\bfinance\b", r"\binvest\b",
    r"\bhistory of\b", r"\bscience of\b",
]


def _count_matches(text: str, patterns: list[str]) -> int:
    """Count how many patterns match in text."""
    count = 0
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            count += 1
    return count


def classify_chunk(chunk: ConversationChunk) -> ClassificationResult:
    """Classify a conversation chunk for routing.

    Classification logic:
    1. High code-block ratio (>60%) → SKIP (code generation)
    2. Very short (<50 words) → SKIP (small talk)
    3. Preference/decision signals in human text → PREFERENCE
    4. Knowledge signals + long assistant response → SECOND_BRAIN
    5. Default: SKIP (when unsure, don't import noise)
    """
    human_text = chunk.human_text.lower()
    assistant_text = chunk.assistant_text.lower()
    all_text = f"{human_text} {assistant_text}"

    # Rule 1: High code ratio → skip
    if chunk.code_block_ratio > 0.6:
        return ClassificationResult(chunk, Route.SKIP, 0.9, "High code-block ratio (code generation)")

    # Rule 2: Very short → skip
    if chunk.word_count < 50:
        return ClassificationResult(chunk, Route.SKIP, 0.8, "Too short for meaningful content")

    # Count signals
    pref_score = _count_matches(human_text, PREFERENCE_SIGNALS)
    ephemeral_score = _count_matches(all_text, EPHEMERAL_SIGNALS)
    knowledge_score = _count_matches(all_text, KNOWLEDGE_SIGNALS)

    # Rule 3: Strong ephemeral signals → skip
    if ephemeral_score >= 2 and pref_score == 0:
        return ClassificationResult(chunk, Route.SKIP, 0.8, f"Ephemeral content ({ephemeral_score} signals)")

    # Rule 4: Preference/decision signals → Second Brain (preference)
    if pref_score >= 1:
        confidence = min(0.5 + pref_score * 0.15, 0.95)
        return ClassificationResult(chunk, Route.PREFERENCE, confidence,
                                    f"Preference/decision content ({pref_score} signals)")

    # Rule 5: Knowledge signals + substantial assistant response → second brain
    assistant_word_count = len(assistant_text.split())
    if knowledge_score >= 1 and assistant_word_count >= 100:
        confidence = min(0.5 + knowledge_score * 0.1 + (assistant_word_count / 2000), 0.95)
        return ClassificationResult(chunk, Route.SECOND_BRAIN, confidence,
                                    f"Knowledge content ({knowledge_score} signals, {assistant_word_count} words)")

    # Rule 6: Long assistant response even without explicit signals → second brain
    if assistant_word_count >= 300 and chunk.code_block_ratio < 0.4:
        return ClassificationResult(chunk, Route.SECOND_BRAIN, 0.5,
                                    f"Substantial response ({assistant_word_count} words)")

    # Default: skip
    return ClassificationResult(chunk, Route.SKIP, 0.6, "No strong routing signals")
