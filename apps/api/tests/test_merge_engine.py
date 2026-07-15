"""TDD: merge_engine applies line/col patches and undo snapshots."""

from app.domain.merge_engine import LineColRange, apply_replace, extract_range


def test_extract_range_single_line():
    text = "hello world\nsecond line\n"
    r = LineColRange(start_line=1, start_col=6, end_line=1, end_col=11)
    assert extract_range(text, r) == "world"


def test_apply_replace_same_line():
    merged = "aaa bbb ccc\n"
    left = LineColRange(start_line=1, start_col=4, end_line=1, end_col=7)
    result = apply_replace(merged, left, "XXX")
    assert result == "aaa XXX ccc\n"


def test_apply_replace_multiline():
    merged = "line1\nline2\nline3\n"
    left = LineColRange(start_line=1, start_col=0, end_line=2, end_col=5)
    result = apply_replace(merged, left, "NEW\nBLOCK")
    assert result == "NEW\nBLOCK\nline3\n"


def test_apply_replace_insert_empty_left():
    """Empty left range inserts right text at position (pure insertion)."""
    merged = "ab\n"
    left = LineColRange(start_line=1, start_col=1, end_line=1, end_col=1)
    result = apply_replace(merged, left, "X")
    assert result == "aXb\n"
