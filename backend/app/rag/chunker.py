"""
Text chunking — recursive character splitter.
No external dependencies.
"""

from typing import List

CHUNK_SIZE    = 800   # characters (~150-200 tokens for BGE-large)
CHUNK_OVERLAP = 100   # character overlap between consecutive chunks

# Separators tried in order; falls back to character split
_SEPARATORS = ['\n\n', '\n', '. ', ' ', '']


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into overlapping chunks of ~chunk_size characters.
    Tries to split on paragraph/sentence/word boundaries before hard-cutting.
    """
    text = text.strip()
    if not text:
        return []

    chunks = _split(text, chunk_size, overlap, _SEPARATORS)
    # Filter out chunks that are only whitespace or very short
    return [c.strip() for c in chunks if len(c.strip()) > 20]


def _split(text: str, size: int, overlap: int, separators: List[str]) -> List[str]:
    if len(text) <= size:
        return [text]

    sep = ''
    for s in separators:
        if s in text:
            sep = s
            break

    if sep == '':
        # Hard character split with overlap
        return _hard_split(text, size, overlap)

    # Split on separator, then merge small pieces
    parts = text.split(sep)
    chunks = []
    current = ''

    for part in parts:
        candidate = (current + sep + part).lstrip(sep) if current else part
        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current)
                # Start next chunk with overlap from end of current
                current = _tail(current, overlap) + sep + part
            else:
                # Single part larger than size — recurse with next separator
                idx = _SEPARATORS.index(sep)
                sub_chunks = _split(part, size, overlap, _SEPARATORS[idx + 1:])
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1] if sub_chunks else ''

    if current:
        chunks.append(current)

    return chunks


def _hard_split(text: str, size: int, overlap: int) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def _tail(text: str, n: int) -> str:
    """Return last n characters of text."""
    return text[-n:] if len(text) > n else text
