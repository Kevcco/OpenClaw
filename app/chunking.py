"""Deterministic knowledge chunking strategies used by indexing and rebuilds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


DEFAULT_MAX_CHARS = 800
DEFAULT_OVERLAP_CHARS = 80
STRATEGY_VERSION = "1"
_HEADING_RE = re.compile(r"(?m)^(#{1,3})\s+.+?(?:\r?\n|$)")
_BREAK_CHARS = set("\n。！？!?；;。")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    start_offset: int
    end_offset: int
    offset_basis: str
    strategy: str
    strategy_version: str = STRATEGY_VERSION


def _validate_strategy(strategy: str) -> str:
    strategy = (strategy or "auto").strip().lower()
    if strategy not in {"auto", "custom", "hierarchy"}:
        raise ValueError("unsupported chunk strategy")
    return strategy


def _natural_end(text: str, start: int, limit: int) -> int:
    hard_end = min(len(text), start + limit)
    if hard_end == len(text):
        return hard_end
    floor = start + max(1, limit // 3)
    for position in range(hard_end, floor, -1):
        if text[position - 1] in _BREAK_CHARS:
            return position
    return hard_end


def _window_chunks(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
    base_offset: int = 0,
    strategy: str,
    offset_basis: str,
) -> list[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = _natural_end(text, start, max_chars)
        if end <= start:
            end = min(len(text), start + max_chars)
        chunks.append(
            Chunk(
                text=text[start:end],
                index=len(chunks),
                start_offset=base_offset + start,
                end_offset=base_offset + end,
                offset_basis=offset_basis,
                strategy=strategy,
            )
        )
        if end >= len(text):
            break
        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


def _preprocess(text: str, *, remove_urls: bool, collapse_whitespace: bool) -> tuple[str, str]:
    normalized = text
    if remove_urls:
        normalized = _EMAIL_RE.sub("", _URL_RE.sub("", normalized))
    if collapse_whitespace:
        normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized, "body_text" if normalized == text else "normalized"


def _hierarchy_chunks(text: str, *, max_chars: int, overlap_chars: int) -> list[Chunk]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return _window_chunks(
            text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            strategy="hierarchy",
            offset_basis="body_text",
        )

    sections: list[tuple[int, int]] = []
    if matches[0].start() > 0:
        sections.append((0, matches[0].start()))
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        sections.append((match.start(), end))

    chunks: list[Chunk] = []
    for section_start, section_end in sections:
        section = text[section_start:section_end]
        if len(section) <= max_chars:
            chunks.append(
                Chunk(
                    text=section,
                    index=len(chunks),
                    start_offset=section_start,
                    end_offset=section_end,
                    offset_basis="body_text",
                    strategy="hierarchy",
                )
            )
            continue
        for chunk in _window_chunks(
            section,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            base_offset=section_start,
            strategy="hierarchy",
            offset_basis="body_text",
        ):
            chunks.append(
                Chunk(
                    text=chunk.text,
                    index=len(chunks),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    offset_basis=chunk.offset_basis,
                    strategy=chunk.strategy,
                )
            )
    return chunks


def chunk_text(
    text: str,
    *,
    strategy: str = "auto",
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    separators: Iterable[str] | None = None,
    remove_urls: bool = False,
    collapse_whitespace: bool = False,
) -> list[Chunk]:
    """Split text without modifying the authoritative stored body."""

    if not isinstance(text, str) or not text.strip():
        return []
    strategy = _validate_strategy(strategy)
    if strategy == "custom":
        if not 100 <= max_chars <= 2000:
            raise ValueError("custom max_chars must be between 100 and 2000")
        if not 0 <= overlap_chars <= max_chars // 2:
            raise ValueError("custom overlap must be between 0% and 50%")
    normalized, offset_basis = _preprocess(
        text,
        remove_urls=remove_urls,
        collapse_whitespace=collapse_whitespace,
    )
    if not normalized:
        return []

    if strategy == "hierarchy":
        chunks = _hierarchy_chunks(
            normalized,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
    else:
        if strategy == "custom" and separators:
            # Prefer the requested separator when it appears before the hard window.
            chunks = _separator_chunks(
                normalized,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                separators=tuple(separators),
                strategy=strategy,
                offset_basis=offset_basis,
            )
        else:
            chunks = _window_chunks(
                normalized,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                strategy=strategy,
                offset_basis=offset_basis,
            )
    if offset_basis == "body_text":
        return chunks
    return [
        Chunk(
            text=chunk.text,
            index=chunk.index,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            offset_basis=offset_basis,
            strategy=chunk.strategy,
            strategy_version=chunk.strategy_version,
        )
        for chunk in chunks
    ]


def _separator_chunks(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
    separators: tuple[str, ...],
    strategy: str,
    offset_basis: str,
) -> list[Chunk]:
    if not separators:
        return _window_chunks(
            text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            strategy=strategy,
            offset_basis=offset_basis,
        )
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + max_chars)
        if hard_end == len(text):
            end = hard_end
        else:
            candidates = []
            for separator in separators:
                position = text.rfind(separator, start, hard_end)
                if position >= start:
                    candidates.append(position + len(separator))
            end = max((candidate for candidate in candidates if candidate > start), default=hard_end)
        chunks.append(
            Chunk(
                text=text[start:end],
                index=len(chunks),
                start_offset=start,
                end_offset=end,
                offset_basis=offset_basis,
                strategy=strategy,
            )
        )
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks
