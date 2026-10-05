"""Intentionally defective teaching fixture; not shipped application code."""


def count_nonblank(lines):
    """Count strings containing at least one non-whitespace character."""
    return sum(bool(line) for line in lines)
