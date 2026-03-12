import pytest
from app.pipeline.chunker import chunk_code


def test_chunk_code_single_chunk():
    """PIPE-01: code under 300 lines returns one chunk."""
    code = "\n".join(f"line {i}" for i in range(1, 11))
    chunks = chunk_code(code, max_lines=300)
    assert len(chunks) == 1
    offset, text = chunks[0]
    assert offset == 1


def test_chunk_code_multiple_chunks():
    """PIPE-01: 600-line code produces 2 chunks of <=300 lines."""
    code = "\n".join(f"line {i}" for i in range(1, 601))
    chunks = chunk_code(code, max_lines=300)
    assert len(chunks) == 2


def test_chunk_code_offset_is_one_based():
    """PIPE-01: first chunk offset == 1; second chunk offset == 301 for 300-line chunks."""
    code = "\n".join(f"line {i}" for i in range(1, 601))
    chunks = chunk_code(code, max_lines=300)
    assert chunks[0][0] == 1
    assert chunks[1][0] == 301


def test_chunk_code_large_file():
    """PIPE-07: 1000-line file produces at least 4 chunks."""
    code = "\n".join(f"line {i}" for i in range(1, 1001))
    chunks = chunk_code(code, max_lines=300)
    assert len(chunks) >= 4


def test_chunk_code_preserves_content():
    """PIPE-01: chunk text contains the actual lines (no lines dropped)."""
    lines = [f"line {i}" for i in range(1, 11)]
    code = "\n".join(lines)
    chunks = chunk_code(code, max_lines=5)
    all_lines = []
    for _, text in chunks:
        all_lines.extend(text.splitlines())
    assert all_lines == lines
