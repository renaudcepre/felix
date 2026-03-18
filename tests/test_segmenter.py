"""Unit tests for felix.ingest.segmenter.

All tests that exercise semantic splitting mock the embedding model so that no
real SentenceTransformer is loaded — keeping the suite fast and offline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest

from felix.ingest.segmenter import TextSegmenter
from felix.ingest.utils import estimate_tokens


# ── helpers ──────────────────────────────────────────────────────────────────


def _long_text(n_paragraphs: int = 20, words_per_para: int = 200) -> str:
    """Build a synthetic text guaranteed to exceed DEFAULT_MAX_TOKENS."""
    paras = [f"Scene {i}.\n" + " ".join(f"word{i}_{j}" for j in range(words_per_para)) for i in range(n_paragraphs)]
    return "\n\n".join(paras)


def _mock_model_with_breaks(n_blocks: int, break_after: list[int]) -> MagicMock:
    """Return a mock SentenceTransformer whose encode() produces embeddings
    such that cosine_similarity(e[i], e[i+1]) ≈ 0 when i in break_after,
    and ≈ 1 otherwise.
    """
    dim = n_blocks + 1
    embeddings = np.zeros((n_blocks, dim))
    group = 0
    for i in range(n_blocks):
        embeddings[i, group] = 1.0
        if i in break_after:
            group += 1

    mock = MagicMock()
    mock.encode.return_value = embeddings
    return mock


def _segmenter(
    max_tokens: int = 500,
    overlap_ratio: float = 0.20,
    threshold: float = 0.45,
) -> TextSegmenter:
    """Convenience factory with sensible test defaults."""
    return TextSegmenter(max_tokens=max_tokens, overlap_ratio=overlap_ratio, threshold=threshold)


# ── estimate_tokens ───────────────────────────────────────────────────────────


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_scales_with_word_count() -> None:
    text = "word " * 100
    assert estimate_tokens(text) == pytest.approx(135, abs=5)


# ── _split_into_blocks ────────────────────────────────────────────────────────


def test_split_into_blocks_single_paragraph() -> None:
    assert TextSegmenter._split_into_blocks("Hello world.") == ["Hello world."]


def test_split_into_blocks_double_newline() -> None:
    text = "Para one.\n\nPara two."
    blocks = TextSegmenter._split_into_blocks(text)
    assert blocks == ["Para one.", "Para two."]


def test_split_into_blocks_strips_empty() -> None:
    text = "A\n\n\n\nB\n\n   \n\nC"
    assert TextSegmenter._split_into_blocks(text) == ["A", "B", "C"]


def test_split_into_blocks_normalizes_crlf() -> None:
    text = "A\r\n\r\nB"
    assert TextSegmenter._split_into_blocks(text) == ["A", "B"]


# ── _find_semantic_breakpoints ────────────────────────────────────────────────


def test_find_breakpoints_no_break_when_similar() -> None:
    mock = _mock_model_with_breaks(3, break_after=[])
    s = _segmenter()
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        bp = s._find_semantic_breakpoints(["a", "b", "c"])
    assert bp == set()


def test_find_breakpoints_detects_orthogonal_drop() -> None:
    mock = _mock_model_with_breaks(3, break_after=[1])
    s = _segmenter()
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        bp = s._find_semantic_breakpoints(["a", "b", "c"])
    assert 1 in bp


def test_find_breakpoints_single_block() -> None:
    s = _segmenter()
    assert s._find_semantic_breakpoints(["only one"]) == set()


# ── _group_blocks ─────────────────────────────────────────────────────────────


def test_group_blocks_no_breaks() -> None:
    blocks = ["a", "b", "c"]
    groups = TextSegmenter._group_blocks(blocks, breakpoints=set())
    assert groups == [["a", "b", "c"]]


def test_group_blocks_break_in_middle() -> None:
    blocks = ["a", "b", "c", "d"]
    groups = TextSegmenter._group_blocks(blocks, breakpoints={1})
    assert groups == [["a", "b"], ["c", "d"]]


def test_group_blocks_multiple_breaks() -> None:
    blocks = ["a", "b", "c", "d"]
    groups = TextSegmenter._group_blocks(blocks, breakpoints={0, 2})
    assert groups == [["a"], ["b", "c"], ["d"]]


# ── _merge_small_segments ─────────────────────────────────────────────────────


def test_merge_small_segments_combines_tiny_segments() -> None:
    segs = [[f"word{i}"] for i in range(10)]
    merged = _segmenter(max_tokens=100)._merge_small_segments(segs)
    assert len(merged) == 1
    assert sum(len(s) for s in merged) == 10


def test_merge_small_segments_respects_budget() -> None:
    big_block = "word " * 200
    segs = [[big_block], [big_block], [big_block]]
    merged = _segmenter(max_tokens=500)._merge_small_segments(segs)
    assert len(merged) == 3


def test_merge_small_segments_preserves_all_blocks() -> None:
    segs = [[f"block{i}"] for i in range(6)]
    merged = _segmenter(max_tokens=1000)._merge_small_segments(segs)
    all_blocks = [b for seg in merged for b in seg]
    assert all_blocks == [f"block{i}" for i in range(6)]


# ── _split_oversized ──────────────────────────────────────────────────────────


def test_split_oversized_single_block_unchanged() -> None:
    big = ["word " * 3000]
    result = _segmenter(max_tokens=100)._split_oversized(big)
    assert result == [big]


def test_split_oversized_splits_at_block_boundary() -> None:
    blocks = ["word " * 300, "word " * 300, "word " * 300]
    result = _segmenter(max_tokens=500)._split_oversized(blocks)
    assert len(result) > 1
    all_blocks = [b for chunk in result for b in chunk]
    assert all_blocks == blocks


# ── _apply_overlap ────────────────────────────────────────────────────────────


def test_apply_overlap_single_chunk_unchanged() -> None:
    chunks = ["only chunk"]
    assert _segmenter()._apply_overlap(chunks) == chunks


def test_apply_overlap_tail_present_in_next_chunk() -> None:
    # overlap_tokens = 500 * 0.20 = 100 → ~74 words
    chunk_a = "alpha " * 50 + "SENTINEL_WORD"
    chunk_b = "beta " * 50
    result = _segmenter(max_tokens=500, overlap_ratio=0.20)._apply_overlap([chunk_a, chunk_b])
    assert "SENTINEL_WORD" in result[1]


def test_apply_overlap_does_not_modify_first_chunk() -> None:
    chunks = ["first chunk content", "second chunk content"]
    result = _segmenter()._apply_overlap(chunks)
    assert result[0] == chunks[0]


# ── segment (integration, mocked model) ──────────────────────────────────────


def test_segment_passthrough_short_text() -> None:
    short = "word " * 50
    assert _segmenter().segment(short) == [short]


def test_segment_passthrough_empty() -> None:
    assert _segmenter().segment("") == [""]


def test_segment_passthrough_whitespace() -> None:
    assert _segmenter().segment("   ") == ["   "]


def test_segment_single_block_over_budget() -> None:
    single_block = "word " * 3000
    result = _segmenter(max_tokens=100).segment(single_block)
    assert result == [single_block]


def test_segment_produces_multiple_chunks() -> None:
    text = _long_text(n_paragraphs=15, words_per_para=200)
    n_blocks = len(text.split("\n\n"))
    mock = _mock_model_with_breaks(n_blocks, break_after=[4, 9])
    s = _segmenter(max_tokens=500)
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        chunks = s.segment(text)
    assert len(chunks) > 1


def test_segment_no_empty_chunks() -> None:
    text = _long_text(n_paragraphs=12, words_per_para=150)
    n_blocks = len(text.split("\n\n"))
    mock = _mock_model_with_breaks(n_blocks, break_after=[3, 7])
    s = _segmenter(max_tokens=500)
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        chunks = s.segment(text)
    assert all(c.strip() for c in chunks)


def test_segment_no_mid_sentence_cut() -> None:
    text = _long_text(n_paragraphs=10, words_per_para=200)
    n_blocks = len(text.split("\n\n"))
    mock = _mock_model_with_breaks(n_blocks, break_after=[2, 6])
    s = _segmenter(max_tokens=500)
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        chunks = s.segment(text)
    reconstructed = "\n\n".join(
        c.split("\n\n", 1)[-1] if i > 0 else c
        for i, c in enumerate(chunks)
    )
    for para in text.split("\n\n"):
        assert para.strip() in reconstructed


def test_segment_overlap_bridges_chunks() -> None:
    text = _long_text(n_paragraphs=10, words_per_para=200)
    n_blocks = len(text.split("\n\n"))
    mock = _mock_model_with_breaks(n_blocks, break_after=[4])
    s = _segmenter(max_tokens=500, overlap_ratio=0.20)
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        chunks = s.segment(text)
    if len(chunks) >= 2:
        words_chunk0 = set(chunks[0].split()[-50:])
        words_chunk1 = set(chunks[1].split()[:100])
        assert words_chunk0 & words_chunk1


def test_segment_all_content_preserved() -> None:
    text = _long_text(n_paragraphs=8, words_per_para=150)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    n_blocks = len(paragraphs)
    mock = _mock_model_with_breaks(n_blocks, break_after=[2, 5])
    s = _segmenter(max_tokens=300)
    with patch.object(TextSegmenter, "_embedding_model", new_callable=PropertyMock, return_value=mock):
        chunks = s.segment(text)
    full_output = "\n\n".join(chunks)
    for para in paragraphs:
        assert para in full_output
