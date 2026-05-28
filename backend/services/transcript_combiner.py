"""
Transcript Combiner Service

Combines multiple segment transcripts into a single clean transcript.
Handles overlap deduplication at segment boundaries using fuzzy matching.

Strategy for each boundary between transcript N and N+1:
1. Take last ~200 words of transcript N
2. Take first ~200 words of transcript N+1
3. Find best fuzzy match using difflib.SequenceMatcher
4. Trim overlap from transcript N+1 (keep N's version as canonical)
5. If no good match (ratio < 0.5), concatenate with newline (safe fallback)
"""

import logging
from difflib import SequenceMatcher
from typing import List

logger = logging.getLogger(__name__)

# Number of words to check for overlap at boundaries
OVERLAP_WORD_WINDOW = 200
# Minimum match ratio to consider as overlap
MIN_MATCH_RATIO = 0.5


def combine_transcripts(
    transcripts: List[str],
    overlap_word_window: int = OVERLAP_WORD_WINDOW,
) -> str:
    """
    Combine multiple segment transcripts into a single transcript.

    Handles overlap deduplication at boundaries.

    Args:
        transcripts: List of transcript strings in order
        overlap_word_window: Number of words to check at boundaries

    Returns:
        Combined transcript string
    """
    if not transcripts:
        return ""

    if len(transcripts) == 1:
        return transcripts[0].strip()

    combined = transcripts[0].strip()

    for i in range(1, len(transcripts)):
        next_transcript = transcripts[i].strip()
        if not next_transcript:
            continue

        if not combined:
            combined = next_transcript
            continue

        # Try to find and remove overlap
        trimmed = _deduplicate_overlap(combined, next_transcript, overlap_word_window)
        combined = combined + "\n\n" + trimmed

    logger.info(
        f"[TRANSCRIPT_COMBINER] Combined {len(transcripts)} transcripts "
        f"into {len(combined)} chars"
    )
    return combined


def _deduplicate_overlap(
    transcript_a: str,
    transcript_b: str,
    word_window: int = OVERLAP_WORD_WINDOW,
) -> str:
    """
    Remove overlapping content from the beginning of transcript_b.

    Compares the tail of transcript_a with the head of transcript_b
    to find and remove duplicated content.

    Args:
        transcript_a: Previous transcript (canonical)
        transcript_b: Next transcript (to be trimmed)
        word_window: Number of words to compare

    Returns:
        transcript_b with overlapping prefix removed
    """
    words_a = transcript_a.split()
    words_b = transcript_b.split()

    if not words_a or not words_b:
        return transcript_b

    tail_a = words_a[-min(word_window, len(words_a)):]
    head_b = words_b[:min(word_window, len(words_b))]

    # Find the best overlap match
    best_overlap_len = 0
    best_ratio = 0.0

    min_overlap = 3  # Minimum words to consider as overlap
    max_overlap = min(len(tail_a), len(head_b))

    for overlap_len in range(max_overlap, min_overlap - 1, -1):
        # Compare tail of A with head of B
        tail_segment = " ".join(tail_a[-overlap_len:])
        head_segment = " ".join(head_b[:overlap_len])

        ratio = SequenceMatcher(
            None, tail_segment.lower(), head_segment.lower()
        ).ratio()

        if ratio > best_ratio and ratio >= MIN_MATCH_RATIO:
            best_ratio = ratio
            best_overlap_len = overlap_len

            # Good enough match, stop searching
            if ratio > 0.85:
                break

    if best_overlap_len > 0:
        # Trim the overlapping prefix from transcript_b
        trimmed_words = words_b[best_overlap_len:]
        result = " ".join(trimmed_words)

        logger.debug(
            f"[TRANSCRIPT_COMBINER] Found overlap: {best_overlap_len} words "
            f"(ratio={best_ratio:.2f}), trimmed from next segment"
        )
        return result
    else:
        # No overlap found - return as-is
        logger.debug("[TRANSCRIPT_COMBINER] No overlap found, concatenating directly")
        return transcript_b
