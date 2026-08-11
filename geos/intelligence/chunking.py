"""Chunking (SPEC-010 §20): headings, paragraphs, token fallback. Deterministic."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..util import new_id

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class Chunk:
    chunk_id: str
    chunk_index: int
    heading: str | None
    position: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def chunk_markdown(
    text: str,
    uri: str,
    max_chars: int = 1200,
    overlap: int = 50,
    chunk_prefix: str = "chk",
) -> list[Chunk]:
    """Split markdown into chunks at heading/paragraph boundaries with a token fallback.

    - 'position' is the char offset of the chunk start within the document.
    - 'heading' is the nearest preceding heading text (or the chunk's own heading).
    """
    blocks = _split_blocks(text)
    chunks: list[Chunk] = []
    buffer: list[tuple[str, str | None]] = []  # (content, heading)
    current_heading: str | None = None
    position = 0

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        heading = buffer[-1][1] or buffer[0][1]  # most recent heading wins
        content = "\n\n".join(c for c, _ in buffer)
        _emit(content, chunks, heading=heading)
        buffer = []

    for block, start in blocks:
        m = HEADING_RE.match(block)
        if m:
            flush()
            current_heading = m.group(2).strip()
            position = start
            continue
        if len(block) > max_chars:
            flush()
            for piece_start, piece in _split_long(block, max_chars, overlap):
                _emit(piece, chunks, heading=current_heading, position=start + piece_start)
            continue
        buffer.append((block, current_heading))
        if len("\n\n".join(c for c, _ in buffer)) >= max_chars:
            flush()
    flush()

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i
    return chunks


def _split_blocks(text: str) -> list[tuple[str, int]]:
    """Return (block, start_offset) for markdown blocks (headings, paragraphs, lists, fenced)."""
    lines = text.split("\n")
    blocks: list[tuple[str, int]] = []
    buf: list[str] = []
    buf_start = 0
    in_fence: bool = False

    def flush_block(end_offset: int) -> None:
        nonlocal buf, buf_start
        if buf:
            blocks.append(("\n".join(buf), buf_start))
            buf = []
        buf_start = end_offset

    offset = 0
    for line in lines:
        line_start = offset
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            offset += len(line) + 1
            continue
        if not in_fence and not stripped:
            flush_block(offset + len(line) + 1)
            offset += len(line) + 1
            continue
        buf.append(line)
        offset += len(line) + 1
    flush_block(offset)
    return blocks


def _split_long(text: str, max_chars: int, overlap: int) -> list[tuple[int, str]]:
    pieces: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        pieces.append((start, text[start:end]))
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1  # guarantee forward progress (overlap >= max_chars)
        start = next_start
    return pieces


def _emit(content: str, chunks: list[Chunk], heading: str | None = None,
          position: int = 0) -> None:
    content = content.strip()
    if not content:
        return
    chunks.append(
        Chunk(
            chunk_id=new_id(), chunk_index=len(chunks), heading=heading,
            position=position, content=content,
        )
    )
