"""Narrative text segmenter — splits long texts into coherent chunks for LLM analysis.

Strategy:
- Texts within the token budget are returned unchanged.
- Longer texts are split at semantic breakpoints (cosine similarity drops between
  adjacent paragraph embeddings) using all-MiniLM-L6-v2.
- Oversized segments that survive semantic splitting are split at paragraph
  boundaries (fixed fallback).
- Adjacent chunks overlap by ~20% to preserve anaphoric context.

The embedding model is loaded lazily — only when a file actually exceeds the budget.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from felix.config import settings
from felix.ingest.utils import estimate_tokens
_EPSILON = 1e-8
_MIN_BLOCKS = 2

DEFAULT_MAX_TOKENS: int = 2500
DEFAULT_OVERLAP_RATIO: float = 0.20
DEFAULT_THRESHOLD: float = 0.45


class TextSegmenter:
    """Splits long narrative texts into coherent, overlapping chunks.

    Usage::

        segmenter = TextSegmenter(max_tokens=2500)
        chunks = segmenter.segment(raw_text)
    """

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.max_tokens = max_tokens
        self.overlap_ratio = overlap_ratio
        self.threshold = threshold
        self._model: SentenceTransformer | None = None

    # ── embedding model ───────────────────────────────────────────────────────

    @property
    def _embedding_model(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer(settings.segmenter_embedding_model)
        return self._model

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _split_into_blocks(text: str) -> list[str]:
        """Split text into paragraph-level blocks (scene headings, action, dialogue).

        Tries double-newline splitting first (standard prose).
        Falls back to single-newline splitting for screenplay format files that use
        only ``\\n`` as line separator (e.g. classic formatted screenplays).
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n{2,}", text)
        blocks = [b.strip() for b in blocks if b.strip()]
        if len(blocks) <= 1:
            blocks = [b.strip() for b in text.split("\n") if b.strip()]
        return blocks

    def _find_semantic_breakpoints(self, blocks: list[str]) -> set[int]:
        """Return indices after which a semantic cut should occur.

        A cut is placed at index i when cosine_similarity(block[i], block[i+1])
        is below self.threshold.
        """
        if len(blocks) < _MIN_BLOCKS:
            return set()

        embeddings: np.ndarray = self._embedding_model.encode(
            blocks, show_progress_bar=False, convert_to_numpy=True
        )

        breakpoints: set[int] = set()
        for i in range(len(embeddings) - 1):
            norm_i = np.linalg.norm(embeddings[i])
            norm_j = np.linalg.norm(embeddings[i + 1])
            denom = norm_i * norm_j
            sim = float(np.dot(embeddings[i], embeddings[i + 1]) / denom) if denom > _EPSILON else 0.0
            if sim < self.threshold:
                breakpoints.add(i)

        return breakpoints

    @staticmethod
    def _group_blocks(blocks: list[str], breakpoints: set[int]) -> list[list[str]]:
        """Group consecutive blocks into segments, cutting at each breakpoint."""
        segments: list[list[str]] = []
        current: list[str] = []
        for i, block in enumerate(blocks):
            current.append(block)
            if i in breakpoints:
                segments.append(current)
                current = []
        if current:
            segments.append(current)
        return segments

    def _merge_small_segments(self, segments: list[list[str]]) -> list[list[str]]:
        """Greedily merge adjacent segments that together still fit within max_tokens.

        Semantic breakpoints are treated as *preferred* cut points, not forced ones.
        This prevents dialogue-heavy texts (many small blocks) from producing dozens
        of tiny chunks when the whole file barely exceeds the token budget.
        """
        merged: list[list[str]] = []
        current: list[str] = []
        for seg in segments:
            combined = current + seg
            if estimate_tokens("\n\n".join(combined)) <= self.max_tokens:
                current = combined
            else:
                if current:
                    merged.append(current)
                current = list(seg)
        if current:
            merged.append(current)
        return merged

    def _split_oversized(self, blocks: list[str]) -> list[list[str]]:
        """Split a block list that exceeds max_tokens at block boundaries."""
        result: list[list[str]] = []
        current: list[str] = []
        for block in blocks:
            tentative = [*current, block]
            if estimate_tokens("\n\n".join(tentative)) > self.max_tokens and current:
                result.append(current)
                current = [block]
            else:
                current = tentative
        if current:
            result.append(current)
        return result

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend the tail of chunk[n-1] to chunk[n] to preserve cross-boundary context."""
        if len(chunks) <= 1:
            return chunks
        overlap_tokens = int(self.max_tokens * self.overlap_ratio)
        overlap_words = max(1, int(overlap_tokens / 1.35))
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = " ".join(chunks[i - 1].split()[-overlap_words:])
            result.append(tail + "\n\n" + chunks[i])
        return result

    # ── public API ────────────────────────────────────────────────────────────

    def segment(self, text: str) -> list[str]:
        """Split text into coherent chunks sized for a local 7B LLM.

        Returns ``[text]`` unchanged when the text fits within ``max_tokens``.
        Otherwise returns N overlapping chunks with semantic boundaries.
        The embedding model is loaded lazily on first call.
        """
        if not text.strip():
            return [text]

        if estimate_tokens(text) <= self.max_tokens:
            return [text]

        blocks = self._split_into_blocks(text)
        if len(blocks) <= 1:
            return [text]

        breakpoints = self._find_semantic_breakpoints(blocks)
        segments = self._group_blocks(blocks, breakpoints)
        segments = self._merge_small_segments(segments)

        fine: list[list[str]] = []
        for seg in segments:
            if estimate_tokens("\n\n".join(seg)) > self.max_tokens:
                fine.extend(self._split_oversized(seg))
            else:
                fine.append(seg)

        chunks = ["\n\n".join(seg) for seg in fine if seg]
        if not chunks:
            return [text]

        return self._apply_overlap(chunks)
