def chunk_code(code: str, max_lines: int = 300) -> list[tuple[int, str]]:
    """Split code into segments of at most max_lines lines.

    Returns a list of (offset, chunk_text) tuples where offset is the
    1-based line number of the first line in that chunk. The offset is
    used by the orchestrator to correct line_start and line_end values
    returned by Claude (which are relative to the chunk, not the full file).

    Args:
        code: The full source code to chunk.
        max_lines: Maximum number of lines per chunk. Default 300.

    Returns:
        List of (offset, chunk_text) tuples. Always returns at least one tuple.
    """
    lines = code.splitlines()

    # Always return at least one chunk, even for empty input
    if not lines:
        return [(1, "")]

    chunks: list[tuple[int, str]] = []
    for i in range(0, len(lines), max_lines):
        segment = lines[i : i + max_lines]
        offset = i + 1  # 1-based line number of first line in this segment
        chunks.append((offset, "\n".join(segment)))

    return chunks
