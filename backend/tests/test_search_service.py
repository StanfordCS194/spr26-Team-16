from __future__ import annotations

from contexthub_backend.services.search import (
    MIN_RELATIVE_SCORE,
    MIN_VECTOR_ONLY_ABSOLUTE_SCORE,
    MIN_VECTOR_ONLY_SCORE,
    _candidate_limit,
    _passes_relevance_gate,
)


def test_relevance_gate_keeps_text_matches_even_with_low_vector_score() -> None:
    assert _passes_relevance_gate(
        vector_score=0.0,
        text_score=0.01,
        score=0.0035,
        best_score=1.0,
    )


def test_relevance_gate_rejects_vector_only_hits_below_similarity_floor() -> None:
    assert not _passes_relevance_gate(
        vector_score=MIN_VECTOR_ONLY_SCORE - 0.01,
        text_score=0.0,
        score=1.0,
        best_score=1.0,
    )


def test_relevance_gate_rejects_vector_only_hits_far_from_best_hit() -> None:
    assert not _passes_relevance_gate(
        vector_score=MIN_VECTOR_ONLY_SCORE + 0.05,
        text_score=0.0,
        score=(1.0 * MIN_RELATIVE_SCORE) - 0.01,
        best_score=1.0,
    )


def test_relevance_gate_keeps_strong_vector_only_hits() -> None:
    assert _passes_relevance_gate(
        vector_score=MIN_VECTOR_ONLY_SCORE + 0.05,
        text_score=0.0,
        score=max(MIN_VECTOR_ONLY_ABSOLUTE_SCORE, MIN_RELATIVE_SCORE) + 0.01,
        best_score=1.0,
    )


def test_candidate_limit_fetches_extra_rows_without_exceeding_cap() -> None:
    assert _candidate_limit(10) > 10
    assert _candidate_limit(50) == 100
